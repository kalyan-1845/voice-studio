# VoiceStudio - AI Voice Cloning & Studio Voiceover Platform

VoiceStudio is a modern desktop voiceover suite that lets you clone your voice with just 20 seconds to 2–3 minutes of sample audio using free cloud-accelerated zero-shot models (F5-TTS/E2-TTS) and high-fidelity neural speech engines.

---

## Features
- **Zero-Shot Voice Cloning:** Provide a 20s–3min audio sample of your voice; the cloud AI clones your timbre, pitch, and accent.
- **In-Browser Recording & Uploads:** Drop your WAV/MP3 voice files or record directly using your microphone.
- **Fast Neural Studio Voices:** Built-in high-definition voices for instant narration without queueing.
- **Production Controls:** Adjust speech rate, auto-trim silences, and choose quick script presets.
- **Waveform & Master Export:** Preview audio in the browser and download `.wav` or `.mp3` master files with one click.
- **Production History:** Review and download your generated clips anytime.

---

## Architecture
```
voice-studio/
├── backend/
│   ├── app.py           # FastAPI server with audio endpoints
│   ├── config.py        # Environment settings & directory paths
│   ├── audio_utils.py   # File validation & metadata extraction
│   └── tts_engine.py    # F5-TTS Hugging Face client & Edge Neural TTS
├── static/
│   ├── index.html       # Modern dark-mode UI with glassmorphism
│   ├── css/style.css    # Premium custom design system
│   └── js/app.js        # Recording, audio player, & API client
├── uploads/             # Reference voice clips
├── outputs/             # Generated master audio
├── .env.example         # Environment template
├── requirements.txt     # Python dependencies
└── run_studio.bat       # 1-click Windows launcher
```

---

## Quick Start (Windows)

### Option 1: One-Click Run
Double-click `run_studio.bat`. It will activate the virtual environment and open your browser automatically at `http://localhost:7860`.

### Option 2: Command Line
```powershell
cd C:\Users\prsnl\.gemini\antigravity\scratch\voice-studio
.venv\Scripts\activate
python -m uvicorn backend.app:app --host 127.0.0.1 --port 7860 --reload
```

---

## Configuration (`.env`)
By default, VoiceStudio runs out of the box with zero setup. To avoid rate limits on public Hugging Face spaces:
1. Create a free account at [huggingface.co](https://huggingface.co).
2. Get your free User Access Token from `Settings -> Access Tokens`.
3. Paste it in `.env`:
   ```env
   HF_TOKEN=your_free_token_here
   ```
