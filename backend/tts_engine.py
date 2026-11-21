import asyncio
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Tuple
import edge_tts
import numpy as np
import soundfile as sf
from gradio_client import Client, handle_file

from .config import DEFAULT_HF_SPACE, OUTPUT_DIR, get_hf_token

def split_text_into_chunks(text: str, max_chunk_len: int = 150) -> List[str]:
    """
    Splits long paragraphs into natural sentence chunks to ensure consistent 1.0x pacing.
    """
    text = text.strip()
    if len(text) <= max_chunk_len:
        return [text]

    raw_sentences = re.split(r'([.?!।|;\n]+[\s]*)', text)
    chunks = []
    current_chunk = ""

    for part in raw_sentences:
        current_chunk += part
        if re.search(r'[.?!।|;\n]', part) or len(current_chunk) >= max_chunk_len:
            cleaned = current_chunk.strip()
            if cleaned:
                chunks.append(cleaned)
            current_chunk = ""

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]

def get_optimal_reference_slice(audio_path: Path, max_duration_sec: float = 10.0) -> Path:
    """
    F5-TTS requires reference audio to be between 3s and 12s.
    If reference audio is longer than 12s (e.g. 60s), this extracts a clean 10s slice
    to prevent F5-TTS from crashing, hallucinating, or truncating to 2s.
    """
    try:
        info = sf.info(str(audio_path))
        if info.duration <= max_duration_sec:
            return audio_path

        data, sr = sf.read(str(audio_path))
        if data.ndim > 1:
            data = data.mean(axis=1)

        trimmed_len = int(sr * max_duration_sec)
        slice_data = data[:trimmed_len]

        trimmed_path = audio_path.parent / f"ref_trimmed_{audio_path.stem}.wav"
        sf.write(str(trimmed_path), slice_data, sr)
        return trimmed_path
    except Exception:
        return audio_path

class TTSEngine:
    def __init__(self):
        self._hf_client: Optional[Client] = None
        self._cached_token: Optional[str] = None
        self.space_name: str = DEFAULT_HF_SPACE

    def _get_hf_client(self) -> Client:
        current_token = get_hf_token()
        if self._hf_client is None or self._cached_token != current_token:
            token = current_token if current_token else None
            self._hf_client = Client(self.space_name, token=token)
            self._cached_token = current_token
        return self._hf_client

    async def _synthesize_single_chunk(
        self,
        reference_audio_path: Path,
        reference_text: str,
        target_chunk: str,
        remove_silence: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Synthesizes an individual sentence chunk via F5-TTS cloud."""
        try:
            loop = asyncio.get_event_loop()

            # Ensure reference audio is sliced to optimal 10s
            optimal_ref = get_optimal_reference_slice(reference_audio_path, max_duration_sec=10.0)

            def _call_hf():
                client = self._get_hf_client()
                audio_file = handle_file(str(optimal_ref))
                return client.predict(
                    ref_audio=audio_file,
                    ref_text=reference_text if reference_text else "",
                    gen_text=target_chunk,
                    remove_silence=remove_silence,
                    api_name="/predict"
                )

            result_path = await loop.run_in_executor(None, _call_hf)

            if isinstance(result_path, (list, tuple)):
                generated_src = result_path[0]
            else:
                generated_src = result_path

            if generated_src and os.path.exists(str(generated_src)):
                return True, str(generated_src)
            return False, None
        except Exception as e:
            return False, str(e)

    async def clone_voice_cloud(
        self,
        reference_audio_path: Path,
        reference_text: str,
        target_text: str,
        remove_silence: bool = False,
        style: str = "natural"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Clones voice with multi-paragraph sentence chunking,
        ensuring natural 1.0x pacing without rushing or truncation.
        """
        try:
            chunks = split_text_into_chunks(target_text)
            
            pause_ms = 220
            if style == "aggressive":
                pause_ms = 140
            elif style == "calm":
                pause_ms = 350

            chunk_audio_arrays = []
            target_sr = 24000

            for idx, chunk in enumerate(chunks):
                success, chunk_file_path = await self._synthesize_single_chunk(
                    reference_audio_path=reference_audio_path,
                    reference_text=reference_text,
                    target_chunk=chunk,
                    remove_silence=remove_silence
                )

                if not success or not chunk_file_path:
                    err_msg = chunk_file_path or "Cloud generation failed on chunk."
                    return False, f"{err_msg}", None

                data, sr_rate = sf.read(chunk_file_path)
                if data.ndim > 1:
                    data = data.mean(axis=1)
                target_sr = sr_rate
                chunk_audio_arrays.append(data)

                # Add natural pause between sentences
                if idx < len(chunks) - 1:
                    silence_samples = int(target_sr * (pause_ms / 1000.0))
                    chunk_audio_arrays.append(np.zeros(silence_samples, dtype=np.float32))

            combined_audio = np.concatenate(chunk_audio_arrays)

            out_filename = f"cloned_{uuid.uuid4().hex[:8]}.wav"
            final_path = OUTPUT_DIR / out_filename
            sf.write(str(final_path), combined_audio, target_sr)

            return True, str(final_path), f"F5-TTS Multi-Sentence ({len(chunks)} Chunks)"
        except Exception as e:
            return False, f"Cloud voice cloning error: {str(e)}", None

    async def generate_neural_tts(
        self,
        text: str,
        voice: str = "en-US-ChristopherNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz"
    ) -> Tuple[bool, str, str]:
        """
        Generates high-definition neural speech using Edge Neural TTS.
        Native support for Telugu, Hindi, and English with zero quota limits.
        """
        try:
            out_filename = f"neural_{uuid.uuid4().hex[:8]}.mp3"
            final_path = OUTPUT_DIR / out_filename

            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch
            )
            await communicate.save(str(final_path))
            return True, str(final_path), f"Neural ({voice})"
        except Exception as e:
            return False, f"Neural TTS generation error: {str(e)}", "Neural"

tts_engine = TTSEngine()
