import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import soundfile as sf
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
    Estimates the median fundamental frequency (F0) of speech in Hz using autocorrelation.
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

def transcribe_audio_file(file_path: Path) -> str:
    """
    Transcribes audio speech in Indian English, Hindi, or Telugu.
    """
    try:
        temp_wav = file_path.parent / f"temp_rec_{uuid.uuid4().hex[:6]}.wav"
        data, sr_rate = sf.read(str(file_path))
        if data.ndim > 1:
            data = data.mean(axis=1)
        sf.write(str(temp_wav), data, sr_rate)

        r = sr.Recognizer()
        with sr.AudioFile(str(temp_wav)) as source:
            audio = r.record(source)

        transcription = ""
        for lang in ['en-IN', 'hi-IN', 'te-IN', 'en-US']:
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

def get_optimal_reference_slice(
    audio_path: Path,
    target_duration_sec: float = 8.5
) -> Tuple[Path, str]:
    """
    Zero-shot models (F5-TTS, XTTS) require reference audio to be 5-10s.
    This creates an exact 8.5s slice and transcribes that exact slice,
    preventing any hallucination, cross-attention mismatch, or 2s truncations.
    """
    try:
        data, sr_rate = sf.read(str(audio_path))
        if data.ndim > 1:
            data = data.mean(axis=1)

        total_duration = len(data) / float(sr_rate)
        if total_duration <= target_duration_sec:
            slice_path = audio_path
        else:
            slice_samples = int(sr_rate * target_duration_sec)
            slice_data = data[:slice_samples]
            slice_filename = f"slice_{audio_path.stem}.wav"
            slice_path = audio_path.parent / slice_filename
            sf.write(str(slice_path), slice_data, sr_rate)

        transcript = transcribe_audio_file(slice_path)
        return slice_path, transcript
    except Exception:
        return audio_path, ""

def get_audio_info(file_path: Path) -> dict:
    """
    Returns audio metadata including detected pitch and auto-transcription.
    """
    try:
        if not file_path.exists():
            return {"exists": False}
        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        pitch = round(estimate_pitch(file_path), 1)
        transcript = transcribe_audio_file(file_path)

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
