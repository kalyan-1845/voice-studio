import os
from pathlib import Path

# Base directories
BASE_DIR: Path = Path(__file__).resolve().parent.parent
UPLOAD_DIR: Path = BASE_DIR / "uploads"
OUTPUT_DIR: Path = BASE_DIR / "outputs"
STATIC_DIR: Path = BASE_DIR / "static"
ENV_FILE: Path = BASE_DIR / ".env"

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_hf_token() -> str:
    """Reads HF token from environment or .env file dynamically."""
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("HF_TOKEN="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        return val
    return os.getenv("HF_TOKEN", "")

def set_hf_token(new_token: str) -> None:
    """Updates HF token in .env file and environment."""
    os.environ["HF_TOKEN"] = new_token.strip()
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    token_updated = False
    new_lines = []
    for line in lines:
        if line.startswith("HF_TOKEN="):
            new_lines.append(f"HF_TOKEN={new_token.strip()}\n")
            token_updated = True
        else:
            new_lines.append(line)
            
    if not token_updated:
        new_lines.append(f"HF_TOKEN={new_token.strip()}\n")
        
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

DEFAULT_HF_SPACE: str = os.getenv("HF_SPACE", "mrfakename/E2-F5-TTS")
PORT: int = int(os.getenv("PORT", "7860"))
HOST: str = os.getenv("HOST", "127.0.0.1")
