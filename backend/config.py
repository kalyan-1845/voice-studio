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

def read_env_var(key: str, default: str = "") -> str:
    """Reads a variable dynamically from the .env file or os.environ."""
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return os.getenv(key, default)

def write_env_var(key: str, value: str) -> None:
    """Safely updates or adds a key=value line in the local .env file."""
    os.environ[key] = value.strip()
    lines = []
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = []

    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value.strip()}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value.strip()}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def get_hf_token() -> str:
    return read_env_var("HF_TOKEN", "")

def set_hf_token(new_token: str) -> None:
    write_env_var("HF_TOKEN", new_token)

def get_cloud_gpu_url() -> str:
    return read_env_var("CLOUD_GPU_URL", "")

def set_cloud_gpu_url(url: str) -> None:
    write_env_var("CLOUD_GPU_URL", url)

# Cloud spaces failover list
HF_SPACES_POOL = [
    "mrfakename/E2-F5-TTS",
    "abidlabs/E2-F5-TTS",
    "Gregniuki/f5-tts_Polish_English_German"
]

DEFAULT_HF_SPACE: str = os.getenv("HF_SPACE", "mrfakename/E2-F5-TTS")
PORT: int = int(os.getenv("PORT", "7860"))
HOST: str = os.getenv("HOST", "127.0.0.1")
