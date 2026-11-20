import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

def save_uploaded_audio(file_bytes: bytes, original_filename: str, upload_dir: Path) -> Path:
    """
    Saves an uploaded audio file with a unique filename.
    """
    try:
        suffix = Path(original_filename).suffix.lower()
        if not suffix:
            suffix = ".wav"
        unique_name = f"sample_{uuid.uuid4().hex[:8]}{suffix}"
        target_path = upload_dir / unique_name
        with open(target_path, "wb") as f:
            f.write(file_bytes)
        return target_path
    except Exception as e:
        raise RuntimeError(f"Failed to save audio file: {str(e)}")

def get_audio_info(file_path: Path) -> dict:
    """
    Returns basic audio metadata like file size and extension.
    """
    try:
        if not file_path.exists():
            return {"exists": False}
        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        return {
            "exists": True,
            "filename": file_path.name,
            "size_mb": size_mb,
            "format": file_path.suffix.replace(".", "").upper()
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}
