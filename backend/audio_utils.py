import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import soundfile as sf
import librosa
import speech_recognition as sr

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

def estimate_pitch(file_path: Path) -> float:
    """
    Estimates the median fundamental frequency (F0) of speech in Hz.
    """
    try:
        data, sr_rate = sf.read(str(file_path))
        if data.ndim > 1:
            data = data.mean(axis=1)

        frame_size = int(sr_rate * 0.04)
        hop = int(sr_rate * 0.02)
        pitches = []
        min_lag = int(sr_rate / 400) # 400 Hz max
        max_lag = int(sr_rate / 75)  # 75 Hz min

        for i in range(0, len(data) - frame_size, hop):
            frame = data[i:i+frame_size]
            if np.std(frame) < 0.02:
                continue
            corr = np.correlate(frame, frame, mode='full')[len(frame)-1:]
            lag = np.argmax(corr[min_lag:max_lag]) + min_lag
            p = sr_rate / lag
            if 80 <= p <= 350:
                pitches.append(p)

        return float(np.median(pitches)) if pitches else 180.0
    except Exception:
        return 180.0

def transcribe_audio_auto(file_path: Path) -> str:
    """
    Automatically detects and transcribes speech in Hindi, Telugu, or English.
    """
    try:
        temp_wav = file_path.parent / f"temp_{uuid.uuid4().hex[:6]}.wav"
        data, sr_rate = sf.read(str(file_path))
        if data.ndim > 1:
            data = data.mean(axis=1)
        sf.write(str(temp_wav), data, sr_rate)

        r = sr.Recognizer()
        with sr.AudioFile(str(temp_wav)) as source:
            audio = r.record(source)

        transcription = ""
        # Try Indian languages in order
        for lang in ['hi-IN', 'te-IN', 'en-IN', 'en-US']:
            try:
                transcription = r.recognize_google(audio, language=lang)
                if transcription:
                    break
            except Exception:
                continue

        if temp_wav.exists():
            temp_wav.unlink()

        return transcription
    except Exception:
        return ""

def pitch_shift_to_target(audio_path: Path, target_pitch: float) -> Path:
    """
    Pitch-shifts the generated audio so its F0 matches the original speaker's target pitch.
    """
    try:
        current_pitch = estimate_pitch(audio_path)
        if current_pitch <= 0 or target_pitch <= 0:
            return audio_path

        # If difference is more than 15 Hz, pitch shift to match
        diff = abs(target_pitch - current_pitch)
        if diff > 15:
            y, sr_rate = sf.read(str(audio_path))
            n_steps = float(12 * np.log2(target_pitch / current_pitch))
            
            # Bound n_steps to avoid extreme distortion
            n_steps = max(min(n_steps, 8.0), -8.0)
            y_shifted = librosa.effects.pitch_shift(y, sr=sr_rate, n_steps=n_steps)
            
            sf.write(str(audio_path), y_shifted, sr_rate)
        return audio_path
    except Exception as e:
        print(f"Pitch shift warning: {e}")
        return audio_path

def get_audio_info(file_path: Path) -> dict:
    """
    Returns audio metadata including detected pitch and auto-transcription.
    """
    try:
        if not file_path.exists():
            return {"exists": False}
        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        pitch = round(estimate_pitch(file_path), 1)
        transcript = transcribe_audio_auto(file_path)

        return {
            "exists": True,
            "filename": file_path.name,
            "size_mb": size_mb,
            "format": file_path.suffix.replace(".", "").upper(),
            "pitch_hz": pitch,
            "transcript": transcript
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}
