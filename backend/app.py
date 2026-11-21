import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import (
    HOST,
    OUTPUT_DIR,
    PORT,
    STATIC_DIR,
    UPLOAD_DIR,
    get_cloud_gpu_url,
    get_hf_token,
    set_cloud_gpu_url,
    set_hf_token
)
from .audio_utils import (
    estimate_pitch,
    get_audio_info,
    save_uploaded_audio,
    transcribe_audio_file
)
from .tts_engine import tts_engine

app = FastAPI(
    title="AI Voice Studio",
    description="Zero-shot voice cloning & studio voiceover platform",
    version="2.0.0"
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
    pitch: int = 0
    style: str = "natural"  # "natural", "aggressive", "calm"
    neural_voice: Optional[str] = "en-US-ChristopherNeural"
    remove_silence: bool = False

class TokenRequest(BaseModel):
    token: str

class CloudGpuRequest(BaseModel):
    url: str

@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Index page not found")
    return FileResponse(str(index_file))

@app.get("/api/health")
async def health_check():
    has_token = bool(get_hf_token())
    cloud_url = get_cloud_gpu_url()
    return {
        "status": "online",
        "engine": "Voice Studio Active",
        "has_hf_token": has_token,
        "has_cloud_gpu": bool(cloud_url),
        "cloud_gpu_url": cloud_url
    }

@app.get("/api/token")
async def get_token_status():
    token = get_hf_token()
    return {
        "has_token": bool(token),
        "masked_token": f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ""
    }

@app.post("/api/token")
async def update_token(req: TokenRequest):
    set_hf_token(req.token)
    return {"status": "success", "message": "Hugging Face token updated successfully!"}

@app.get("/api/cloud-gpu")
async def get_cloud_gpu():
    url = get_cloud_gpu_url()
    return {
        "connected": bool(url),
        "url": url
    }

@app.post("/api/cloud-gpu")
async def set_cloud_gpu(req: CloudGpuRequest):
    set_cloud_gpu_url(req.url.strip())
    return {
        "status": "success",
        "message": "Cloud GPU URL updated successfully!",
        "connected": bool(req.url.strip()),
        "url": req.url.strip()
    }

@app.post("/api/upload-sample")
async def upload_sample(file: UploadFile = File(...)):
    """
    Receives user voice recording or file (WAV/MP3/M4A/OGG),
    saves it, and automatically transcribes speech and detects vocal pitch.
    """
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        
        saved_path = save_uploaded_audio(content, file.filename or "voice_sample.wav", UPLOAD_DIR)
        info = get_audio_info(saved_path)

        return {
            "status": "success",
            "filename": saved_path.name,
            "url": f"/api/audio/uploads/{saved_path.name}",
            "info": info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/samples")
async def list_samples():
    """
    Lists all saved voice samples in uploads directory.
    """
    try:
        files = []
        for f in sorted(UPLOAD_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
            if f.is_file() and f.name != ".gitkeep" and not f.name.startswith("temp_") and not f.name.startswith("slice_"):
                files.append({
                    "filename": f.name,
                    "url": f"/api/audio/uploads/{f.name}",
                    "size_mb": round(os.path.getsize(f) / (1024 * 1024), 2),
                    "created_at": os.path.getmtime(f)
                })
        return {"samples": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/samples/{filename}")
async def delete_sample(filename: str):
    """
    Deletes a single uploaded voice profile.
    """
    try:
        target = UPLOAD_DIR / filename
        if target.exists() and target.is_file() and target.name != ".gitkeep":
            target.unlink()
            # Also clean up any associated slice
            slice_path = UPLOAD_DIR / f"slice_{target.stem}.wav"
            if slice_path.exists():
                slice_path.unlink()
            return {"status": "success", "message": f"Deleted {filename}"}
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/samples")
async def clear_all_samples():
    """
    Clears all uploaded voice profiles.
    """
    try:
        count = 0
        for f in UPLOAD_DIR.glob("*.*"):
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
                count += 1
        return {"status": "success", "message": f"Deleted {count} voice profiles."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/neural-voices")
async def list_neural_voices():
    """
    Available high-fidelity neural voices supporting Telugu, Hindi, and English.
    """
    return {
        "voices": [
            {"id": "en-US-ChristopherNeural", "name": "Christopher (US Male - Warm Studio)", "gender": "Male", "lang": "English (US)"},
            {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Indian English Male - Fluent)", "gender": "Male", "lang": "English (IN)"},
            {"id": "en-IN-NeerjaNeural", "name": "Neerja (Indian English Female)", "gender": "Female", "lang": "English (IN)"},
            {"id": "te-IN-MohanNeural", "name": "Mohan (Telugu Male - Natural & Deep)", "gender": "Male", "lang": "Telugu"},
            {"id": "te-IN-ShrutiNeural", "name": "Shruti (Telugu Female - Expressive)", "gender": "Female", "lang": "Telugu"},
            {"id": "hi-IN-MadhurNeural", "name": "Madhur (Hindi Male - Fluent & Natural)", "gender": "Male", "lang": "Hindi"},
            {"id": "hi-IN-SwaraNeural", "name": "Swara (Hindi Female - Expressive)", "gender": "Female", "lang": "Hindi"},
            {"id": "en-US-JennyNeural", "name": "Jenny (US Female - Clear)", "gender": "Female", "lang": "English (US)"},
            {"id": "en-GB-RyanNeural", "name": "Ryan (British Male - Articulate)", "gender": "Male", "lang": "English (UK)"}
        ]
    }

@app.post("/api/generate")
async def generate_speech(req: GenerateRequest):
    """
    Generates speech supporting full paragraphs.
    Produces pristine voice cloning with zero artificial pitch-vocoder degradation.
    """
    if not req.script_text.strip():
        raise HTTPException(status_code=400, detail="Script text cannot be empty.")

    rate_percent = int((req.speed - 1.0) * 100)
    style_pitch_offset = 0
    if req.style == "aggressive":
        rate_percent += 5
        style_pitch_offset = 6
    elif req.style == "calm":
        rate_percent -= 5
        style_pitch_offset = -6

    rate_str = f"{'+' if rate_percent >= 0 else ''}{rate_percent}%"
    total_pitch = req.pitch + style_pitch_offset
    pitch_str = f"{'+' if total_pitch >= 0 else ''}{total_pitch}Hz"

    if req.mode == "clone":
        if not req.sample_filename:
            raise HTTPException(status_code=400, detail="Voice sample is required for voice cloning.")
        
        sample_path = UPLOAD_DIR / req.sample_filename
        if not sample_path.exists():
            raise HTTPException(status_code=404, detail="Selected voice sample was not found.")

        # Multi-paragraph zero-shot voice cloning with sentence chunking
        success, result_path_or_msg, engine = await tts_engine.clone_voice_cloud(
            reference_audio_path=sample_path,
            reference_text=req.sample_transcript or "",
            target_text=req.script_text,
            remove_silence=req.remove_silence,
            style=req.style
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": result_path_or_msg,
                    "tip": "Tip: You can connect your free Google Colab NVIDIA GPU in 1 click for instant unlimited cloning!"
                }
            )

        output_file = Path(result_path_or_msg)
        return {
            "status": "success",
            "url": f"/api/audio/outputs/{output_file.name}",
            "filename": output_file.name,
            "engine": f"{engine} • {req.style.capitalize()}"
        }
    else:
        # Neural mode
        voice_id = req.neural_voice or "en-US-ChristopherNeural"
        success, result_path_or_msg, engine = await tts_engine.generate_neural_tts(
            text=req.script_text,
            voice=voice_id,
            rate=rate_str,
            pitch=pitch_str
        )
        if not success:
            raise HTTPException(status_code=500, detail=result_path_or_msg)

        output_file = Path(result_path_or_msg)
        return {
            "status": "success",
            "url": f"/api/audio/outputs/{output_file.name}",
            "filename": output_file.name,
            "engine": f"{engine} • {req.style.capitalize()}"
        }

@app.get("/api/audio/{folder}/{filename}")
async def get_audio_file(folder: str, filename: str):
    """
    Streams audio files securely from uploads or outputs.
    """
    if folder == "uploads":
        file_path = UPLOAD_DIR / filename
    elif folder == "outputs":
        file_path = OUTPUT_DIR / filename
    else:
        raise HTTPException(status_code=400, detail="Invalid folder specified.")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found.")

    suffix = file_path.suffix.lower()
    media_type = "audio/wav"
    if suffix == ".mp3":
        media_type = "audio/mpeg"
    elif suffix in [".m4a", ".mp4"]:
        media_type = "audio/mp4"
    elif suffix == ".ogg":
        media_type = "audio/ogg"

    return FileResponse(str(file_path), media_type=media_type)

@app.get("/api/history")
async def get_history():
    """
    Returns list of generated voiceover files.
    """
    try:
        items = []
        for f in sorted(OUTPUT_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
            if f.is_file() and f.name != ".gitkeep":
                items.append({
                    "filename": f.name,
                    "url": f"/api/audio/outputs/{f.name}",
                    "size_mb": round(os.path.getsize(f) / (1024 * 1024), 2),
                    "created_at": os.path.getmtime(f)
                })
        return {"history": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history/{filename}")
async def delete_history_item(filename: str):
    """
    Deletes an individual generated audio file from the production library.
    """
    try:
        target = OUTPUT_DIR / filename
        if target.exists() and target.is_file() and target.name != ".gitkeep":
            target.unlink()
            return {"status": "success", "message": f"Deleted {filename}"}
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/history")
async def clear_all_history():
    """
    Clears all generated audio files from the production library.
    """
    try:
        count = 0
        for f in OUTPUT_DIR.glob("*.*"):
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
                count += 1
        return {"status": "success", "message": f"Deleted {count} generated files."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
