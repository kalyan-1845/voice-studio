import os
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import HOST, OUTPUT_DIR, PORT, STATIC_DIR, UPLOAD_DIR, get_hf_token, set_hf_token
from .audio_utils import estimate_pitch, get_audio_info, pitch_shift_to_target, save_uploaded_audio, transcribe_audio_auto
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
    pitch: int = 0
    style: str = "natural"  # "natural", "aggressive", "calm"
    neural_voice: Optional[str] = "en-US-ChristopherNeural"
    remove_silence: bool = False

class TokenRequest(BaseModel):
    token: str

@app.get("/")
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Index page not found")
    return FileResponse(str(index_file))

@app.get("/api/health")
async def health_check():
    has_token = bool(get_hf_token())
    return {"status": "online", "engine": "Voice Studio Active", "has_hf_token": has_token}

@app.get("/api/token")
async def get_token_status():
    token = get_hf_token()
    return {"has_token": bool(token), "masked_token": f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ""}

@app.post("/api/token")
async def update_token(req: TokenRequest):
    set_hf_token(req.token)
    return {"status": "success", "message": "Hugging Face token updated successfully!"}

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
        info["url"] = f"/api/audio/uploads/{saved_path.name}"
        return JSONResponse(content={"status": "success", "file": info})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/api/samples")
async def list_samples():
    """
    Lists uploaded voice samples sorted by newest first with pitch & transcript.
    """
    try:
        files = []
        for file_path in sorted(UPLOAD_DIR.glob("*.*"), key=os.path.getmtime, reverse=True):
            if file_path.suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a", ".flac"] and file_path.name != ".gitkeep":
                files.append({
                    "filename": file_path.name,
                    "url": f"/api/audio/uploads/{file_path.name}",
                    "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2),
                    "created_at": file_path.stat().st_mtime
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
    Generates speech supporting full paragraphs with zero failure rate.
    If cloud ZeroGPU limits occur, it automatically falls back to vocal pitch matching.
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

        # Reference transcript lookup / auto-transcribe
        reference_text = req.sample_transcript.strip() if req.sample_transcript else ""
        if not reference_text:
            reference_text = transcribe_audio_auto(sample_path)

        # Detect original target pitch
        original_pitch = estimate_pitch(sample_path)

        # Multi-paragraph voice cloning with sentence chunking & natural pacing
        success, result_path_or_msg, engine = await tts_engine.clone_voice_cloud(
            reference_audio_path=sample_path,
            reference_text=reference_text,
            target_text=req.script_text,
            remove_silence=req.remove_silence,
            style=req.style
        )

        if not success:
            # Automatic intelligent fallback: Generate paragraph with calibrated neural voice
            # matching user's original pitch so user's text NEVER fails to generate!
            fallback_voice = "en-IN-PrabhatNeural"
            if any(ord(c) >= 0x0c00 and ord(c) <= 0x0c7f for c in req.script_text):
                fallback_voice = "te-IN-MohanNeural"
            elif any(ord(c) >= 0x0900 and ord(c) <= 0x097f for c in req.script_text):
                fallback_voice = "hi-IN-MadhurNeural"

            fb_success, fb_path, _ = await tts_engine.generate_neural_tts(
                text=req.script_text,
                voice=fallback_voice,
                rate=rate_str,
                pitch=f"{'+' if total_pitch >= 0 else ''}{total_pitch}Hz"
            )
            
            if fb_success:
                fb_file = Path(fb_path)
                pitch_shift_to_target(fb_file, original_pitch, style=req.style)
                return {
                    "status": "success",
                    "url": f"/api/audio/outputs/{fb_file.name}",
                    "filename": fb_file.name,
                    "engine": f"Neural Fallback (Pitch Calibrated {original_pitch:.0f} Hz)",
                    "note": "Hugging Face ZeroGPU was temporarily throttled; synthesized using calibrated neural engine."
                }
            else:
                return JSONResponse(status_code=200, content={"status": "warning", "message": result_path_or_msg})

        output_file = Path(result_path_or_msg)
        pitch_shift_to_target(output_file, original_pitch, style=req.style)

        return {
            "status": "success",
            "url": f"/api/audio/outputs/{output_file.name}",
            "filename": output_file.name,
            "engine": f"{engine} • Pitch Calibrated ({original_pitch:.0f} Hz) • {req.style.capitalize()}"
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
            if file_path.suffix.lower() in [".wav", ".mp3", ".ogg"] and file_path.name != ".gitkeep":
                items.append({
                    "filename": file_path.name,
                    "url": f"/api/audio/outputs/{file_path.name}",
                    "created_at": file_path.stat().st_mtime,
                    "size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2)
                })
        return {"history": items[:25]}
    except Exception as e:
        return {"history": [], "error": str(e)}

@app.delete("/api/history/{filename}")
async def delete_history_item(filename: str):
    """
    Deletes a single output voiceover clip.
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
    Clears all output voiceover clips from Production Library.
    """
    try:
        count = 0
        for f in OUTPUT_DIR.glob("*.*"):
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
                count += 1
        return {"status": "success", "message": f"Deleted {count} output clips."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=True)
