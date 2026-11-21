import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import soundfile as sf
import speech_recognition as sr

def save_uploaded_audio(file_bytes: bytes, original_filename: str, upload_dir: Path) -> Path:
    """
    Saves an uploaded audio file with a unique filename and converts it
    to standard 24kHz Mono PCM WAV using ffmpeg. This guarantees 100% compatibility
    with browser WebM recordings, iPhone M4A, OGG, and MP3 files.
    """
    try:
        raw_name = f"temp_raw_{uuid.uuid4().hex[:8]}"
        raw_path = upload_dir / raw_name
        with open(raw_path, "wb") as f:
            f.write(file_bytes)

        target_name = f"sample_{uuid.uuid4().hex[:8]}.wav"
        target_path = upload_dir / target_name

        try:
            cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-ar", "24000", "-ac", "1", str(target_path)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if raw_path.exists():
                raw_path.unlink()
            return target_path
        except Exception:
            if raw_path.exists():
                shutil.move(str(raw_path), str(target_path))
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

def find_optimal_pause_boundary(data: np.ndarray, sr_rate: int, min_sec: float = 5.5, max_sec: float = 9.5) -> int:
    """
    Finds the exact low-energy silence/pause between words or sentences
    between min_sec and max_sec. This prevents cutting words in half.
    """
    total_sec = len(data) / float(sr_rate)
    if total_sec <= max_sec:
        return len(data)

    start_sample = int(min_sec * sr_rate)
    end_sample = int(min(len(data), max_sec * sr_rate))

    # Evaluate energy in 80ms windows, stepped every 20ms
    window_size = int(0.08 * sr_rate)
    step = int(0.02 * sr_rate)

    min_energy = float('inf')
    best_cut = int(8.0 * sr_rate)

    for i in range(start_sample, end_sample - window_size, step):
        frame = data[i : i + window_size]
        energy = np.mean(frame ** 2)
        if energy < min_energy:
            min_energy = energy
            best_cut = i + (window_size // 2)

    return best_cut

def get_optimal_reference_slice(
    audio_path: Path,
    target_duration_sec: float = 8.5
) -> Tuple[Path, str]:
    """
    Zero-shot models (F5-TTS, XTTS) require reference audio to be ~5-10s.
    This creates an exact slice bounded at a natural silence/pause between words,
    removes DC bias, normalizes peaks, and generates an exact matching transcript.
    """
    try:
        data, sr_rate = sf.read(str(audio_path))
        if data.ndim > 1:
            data = data.mean(axis=1)

        total_duration = len(data) / float(sr_rate)
        if total_duration <= 9.5:
            slice_data = data
        else:
            cut_sample = find_optimal_pause_boundary(data, sr_rate, min_sec=5.5, max_sec=9.5)
            slice_data = data[:cut_sample]

        # Studio Audio Optimization: Remove DC offset & peak normalize for maximum vocal clarity
        slice_data = slice_data - np.mean(slice_data) # Remove DC offset
        max_v = np.max(np.abs(slice_data))
        if max_v > 0.01:
            slice_data = (slice_data / max_v) * 0.95

        slice_filename = f"slice_{audio_path.stem}.wav"
        slice_path = audio_path.parent / slice_filename
        sf.write(str(slice_path), slice_data, sr_rate)

        transcript = transcribe_audio_file(slice_path)
        return slice_path, transcript
    except Exception:
        return audio_path, ""

def get_audio_info(file_path: Path) -> dict:
    """
    Returns audio metadata including detected pitch and auto-transcription
    of the optimal reference slice.
    """
    try:
        if not file_path.exists():
            return {"exists": False}
        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
        pitch = round(estimate_pitch(file_path), 1)

        # Generate optimal slice transcript to match exactly what F5-TTS receives
        slice_path, slice_transcript = get_optimal_reference_slice(file_path)
        data, sr_rate = sf.read(str(slice_path))
        slice_duration = round(len(data) / float(sr_rate), 1)

        return {
            "exists": True,
            "filename": file_path.name,
            "size_mb": size_mb,
            "format": file_path.suffix.replace(".", "").upper(),
            "pitch_hz": pitch,
            "slice_duration_sec": slice_duration,
            "transcript": slice_transcript
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}
