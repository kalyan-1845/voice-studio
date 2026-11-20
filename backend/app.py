import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import HOST, OUTPUT_DIR, PORT, STATIC_DIR, UPLOAD_DIR
from .audio_utils import get_audio_info, save_uploaded_audio
from .tts_engine import tts_engine

app = FastAPI(
    title="AI Voice Studio",
    description="Zero-shot voice cloning & studio voiceover platform",
    version="1.0.0"
)

# CORS support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class GenerateRequest(BaseModel):
    mode: str = "clone"  # "clone" or "neural"
    sample_filename: Optional[str] = None
    sample_transcript: Optional[str] = ""
    script_text: str
    speed: float = 1.0
    neural_voice: Optional[str] = "en-US-ChristopherNeural"
    remove_silence: bool = True

@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Index page not found")
    return FileResponse(str(index_file))

@app.get("/api/health")
async def health_check():
    return {"status": "online", "engine": "Voice Studio Active"}

@app.post("/api/upload-sample")
async def upload_sample(file: UploadFile = File(...)):
    """
    Receives user voice recording or file (WAV/MP3/M4A/OGG).
    """
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        
        saved_path = save_uploaded_audio(content, file.filename or "voice_sample.wav", UPLOAD_DIR)
        info = get_audio_info(saved_path)
        info["url"] = f"/api/audio/uploads/{saved_path.name}"
        return JSONResponse(content={"status": "success", "file": info})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/samples")
async def list_samples():
    """
    Lists uploaded voice samples sorted by newest first.
    """
    try:
        files = []
        for file_path in sorted(UPLOAD_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
            if file_path.suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a", ".flac"]:
                files.append({
                    "filename": file_path.name,
                    "url": f"/api/audio/uploads/{file_path.name}",
                    "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2),
                    "created_at": file_path.stat().st_mtime
                })
        return {"samples": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/neural-voices")
async def list_neural_voices():
    """
    Available high-fidelity neural voices.
    """
    return {
        "voices": [
            {"id": "hi-IN-MadhurNeural", "name": "Madhur (Hindi Male - Natural & Fluent)", "gender": "Male"},
            {"id": "hi-IN-SwaraNeural", "name": "Swara (Hindi Female - Expressive)", "gender": "Female"},
            {"id": "en-US-ChristopherNeural", "name": "Christopher (US Male - Warm & Studio)", "gender": "Male"},
            {"id": "en-US-JennyNeural", "name": "Jenny (US Female - Natural & Clear)", "gender": "Female"},
            {"id": "en-US-GuyNeural", "name": "Guy (US Male - Casual)", "gender": "Male"},
            {"id": "en-US-AriaNeural", "name": "Aria (US Female - Expressive)", "gender": "Female"},
            {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Indian English Male - Fluent)", "gender": "Male"},
            {"id": "en-IN-NeerjaNeural", "name": "Neerja (Indian English Female - Expressive)", "gender": "Female"},
            {"id": "en-GB-RyanNeural", "name": "Ryan (British Male - Articulate)", "gender": "Male"},
            {"id": "en-GB-SoniaNeural", "name": "Sonia (British Female - Calm)", "gender": "Female"},
            {"id": "en-AU-WilliamNeural", "name": "William (Australian Male)", "gender": "Male"}
        ]
    }

@app.post("/api/generate")
async def generate_speech(req: GenerateRequest):
    """
    Generates speech using either cloned voice (F5-TTS cloud) or neural fallback.
    """
    if not req.script_text.strip():
        raise HTTPException(status_code=400, detail="Script text cannot be empty.")

    rate_percent = int((req.speed - 1.0) * 100)
    rate_str = f"{'+' if rate_percent >= 0 else ''}{rate_percent}%"

    if req.mode == "clone":
        if not req.sample_filename:
            raise HTTPException(status_code=400, detail="Voice sample is required for voice cloning.")
        
        sample_path = UPLOAD_DIR / req.sample_filename
        if not sample_path.exists():
            raise HTTPException(status_code=404, detail="Selected voice sample was not found.")

        # Attempt cloud voice clone
        success, result_path_or_msg, engine = await tts_engine.clone_voice_cloud(
            reference_audio_path=sample_path,
            reference_text=req.sample_transcript or "",
            target_text=req.script_text,
            remove_silence=req.remove_silence
        )

        if not success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "warning",
                    "message": f"Cloud cloning space reported: {result_path_or_msg}. Try again or switch to Neural studio voice.",
                    "can_fallback": True
                }
            )

        output_file = Path(result_path_or_msg)
        return {
            "status": "success",
            "url": f"/api/audio/outputs/{output_file.name}",
            "filename": output_file.name,
            "engine": engine
        }
    else:
        # Neural mode
        voice_id = req.neural_voice or "en-US-ChristopherNeural"
        success, result_path_or_msg, engine = await tts_engine.generate_neural_tts(
            text=req.script_text,
            voice=voice_id,
            rate=rate_str
        )
        if not success:
            raise HTTPException(status_code=500, detail=result_path_or_msg)

        output_file = Path(result_path_or_msg)
        return {
            "status": "success",
            "url": f"/api/audio/outputs/{output_file.name}",
            "filename": output_file.name,
            "engine": engine
        }

@app.get("/api/audio/{folder}/{filename}")
async def get_audio_file(folder: str, filename: str):
    """
    Safely serves audio files.
    """
    if folder not in ["uploads", "outputs"]:
        raise HTTPException(status_code=400, detail="Invalid folder.")
    
    target_dir = UPLOAD_DIR if folder == "uploads" else OUTPUT_DIR
    target_path = target_dir / filename
    
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found.")
    
    media_type = "audio/wav" if target_path.suffix.lower() == ".wav" else "audio/mpeg"
    return FileResponse(str(target_path), media_type=media_type)

@app.get("/api/history")
async def get_history():
    """
    Returns list of recently generated voiceovers.
    """
    try:
        items = []
        for file_path in sorted(OUTPUT_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
            if file_path.suffix.lower() in [".wav", ".mp3", ".ogg"]:
                items.append({
                    "filename": file_path.name,
                    "url": f"/api/audio/outputs/{file_path.name}",
                    "created_at": file_path.stat().st_mtime,
                    "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2)
                })
        return {"history": items[:20]}
    except Exception as e:
        return {"history": [], "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=True)
