import os
from pathlib import Path

# Base directories
BASE_DIR: Path = Path(__file__).resolve().parent.parent
UPLOAD_DIR: Path = BASE_DIR / "uploads"
OUTPUT_DIR: Path = BASE_DIR / "outputs"
STATIC_DIR: Path = BASE_DIR / "static"

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Settings & Credentials
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
DEFAULT_HF_SPACE: str = os.getenv("HF_SPACE", "mrfakename/E2-F5-TTS")
PORT: int = int(os.getenv("PORT", "7860"))
HOST: str = os.getenv("HOST", "127.0.0.1")
