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

from .config import (
    DEFAULT_HF_SPACE,
    HF_SPACES_POOL,
    OUTPUT_DIR,
    get_cloud_gpu_url,
    get_hf_token
)
from .audio_utils import get_optimal_reference_slice

def split_text_into_chunks(text: str, max_chunk_words: int = 30) -> List[str]:
    """
    Splits long voiceover paragraphs into natural sentences/chunks (~25-30 words each).
    This ensures steady 1.0x cadence without rushing or model attention degradation.
    """
    text = text.strip()
    if not text:
        return []

    # Split by sentence-ending punctuation (., ?, !, ।, ;, newline)
    sentences = re.split(r'([.?!।|;\n]+[\s]*)', text)
    chunks = []
    current_chunk = ""

    for part in sentences:
        current_chunk += part
        words_in_current = len(current_chunk.strip().split())
        
        # If we reached punctuation and have a decent size, or exceeded max words
        if re.search(r'[.?!।|;\n]', part) and words_in_current >= 10:
            cleaned = current_chunk.strip()
            if cleaned:
                chunks.append(cleaned)
            current_chunk = ""
        elif words_in_current >= max_chunk_words:
            cleaned = current_chunk.strip()
            if cleaned:
                chunks.append(cleaned)
            current_chunk = ""

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]

class TTSEngine:
    def __init__(self):
        self._custom_client: Optional[Client] = None
        self._cached_custom_url: Optional[str] = None
        self._clients: dict = {}

    def _get_hf_client(self, space_name: str, token: Optional[str]) -> Client:
        cache_key = f"{space_name}::{token or 'guest'}"
        if cache_key not in self._clients:
            self._clients[cache_key] = Client(space_name, token=token)
        return self._clients[cache_key]

    def _get_custom_gpu_client(self) -> Optional[Client]:
        url = get_cloud_gpu_url()
        if not url:
            return None
        if self._custom_client is None or self._cached_custom_url != url:
            try:
                self._custom_client = Client(url)
                self._cached_custom_url = url
            except Exception:
                self._custom_client = None
        return self._custom_client

    async def _call_custom_gpu_infer(
        self,
        ref_audio_path: Path,
        ref_text: str,
        target_text: str,
        remove_silence: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Calls user's dedicated Cloud GPU (Google Colab / RunPod / custom Gradio endpoint)."""
        try:
            client = self._get_custom_gpu_client()
            if not client:
                return False, "Custom Cloud GPU client not available"

            loop = asyncio.get_event_loop()
            audio_handle = handle_file(str(ref_audio_path))

            def _run():
                return client.predict(
                    audio_handle,
                    ref_text or "",
                    target_text,
                    remove_silence
                )

            res = await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=30.0)
            out_file = res[0] if isinstance(res, (list, tuple)) else res
            if out_file and os.path.exists(str(out_file)):
                return True, str(out_file)
            return False, "Custom GPU returned no audio output"
        except Exception as e:
            return False, str(e)

    async def _call_hf_pool_infer(
        self,
        ref_audio_path: Path,
        ref_text: str,
        target_text: str,
        remove_silence: bool = False
    ) -> Tuple[bool, Optional[str], str]:
        """
        Attempts inference across cloud space pool with smart token/guest fallback.
        """
        user_token = get_hf_token()
        loop = asyncio.get_event_loop()

        # Try spaces in the pool
        spaces_to_try = list(HF_SPACES_POOL)
        
        last_error = ""
        for space_name in spaces_to_try:
            # Try guest first (clean quota), then token if needed
            attempts = [None]
            if user_token:
                attempts.append(user_token)

            for token_attempt in attempts:
                try:
                    def _call():
                        c = self._get_hf_client(space_name, token_attempt)
                        audio_handle = handle_file(str(ref_audio_path))
                        
                        if "abidlabs" in space_name:
                            return c.predict(
                                ref_audio_orig=audio_handle,
                                ref_text=ref_text or "",
                                gen_text=target_text,
                                exp_name="F5-TTS",
                                remove_silence=remove_silence,
                                cross_fade_duration=0.15,
                                api_name="/infer"
                            )
                        else:
                            return c.predict(
                                ref_audio=audio_handle,
                                ref_text=ref_text or "",
                                gen_text=target_text,
                                remove_silence=remove_silence,
                                api_name="/predict"
                            )

                    # Maximum 45s wait per space to avoid long public queues
                    res = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=45.0)
                    out_file = res[0] if isinstance(res, (list, tuple)) else res
                    if out_file and os.path.exists(str(out_file)):
                        engine_name = f"Cloud F5-TTS ({space_name.split('/')[0]})"
                        return True, str(out_file), engine_name
                except asyncio.TimeoutError:
                    last_error = f"Public queue on {space_name} timed out after 45s."
                    continue
                except Exception as e:
                    err_msg = str(e)
                    last_error = err_msg
                    continue

        return False, None, last_error or "Cloud voice cloning failed across all pool spaces"

    async def clone_voice_cloud(
        self,
        reference_audio_path: Path,
        reference_text: str,
        target_text: str,
        remove_silence: bool = False,
        style: str = "natural"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Clones voice with multi-sentence chunking for full paragraphs.
        Produces pristine studio output with no phase vocoder distortion.
        """
        try:
            # 1. Slice reference audio to optimal 8.5s + auto-transcribe slice if empty
            optimal_ref, auto_slice_transcript = get_optimal_reference_slice(reference_audio_path, target_duration_sec=8.5)
            effective_ref_text = reference_text.strip() if reference_text.strip() else auto_slice_transcript

            # 2. Split target script into natural paragraph chunks
            chunks = split_text_into_chunks(target_text, max_chunk_words=30)
            if not chunks:
                return False, "Target script is empty.", None

            # 3. Inter-sentence breathing pause
            pause_ms = 240
            if style == "aggressive":
                pause_ms = 150
            elif style == "calm":
                pause_ms = 350

            chunk_audio_arrays = []
            target_sr = 24000
            active_engine = "Cloud F5-TTS"

            # Check if Custom Cloud GPU (Colab/RunPod) is active
            custom_gpu_url = get_cloud_gpu_url()

            for idx, chunk in enumerate(chunks):
                chunk_file = None
                success = False

                if custom_gpu_url:
                    success, chunk_file = await self._call_custom_gpu_infer(
                        ref_audio_path=optimal_ref,
                        ref_text=effective_ref_text,
                        target_text=chunk,
                        remove_silence=remove_silence
                    )
                    active_engine = "Dedicated NVIDIA Cloud GPU (Colab)"

                if not success or not chunk_file:
                    success, chunk_file, eng = await self._call_hf_pool_infer(
                        ref_audio_path=optimal_ref,
                        ref_text=effective_ref_text,
                        target_text=chunk,
                        remove_silence=remove_silence
                    )
                    active_engine = eng

                if not success or not chunk_file:
                    err_msg = chunk_file or "Voice cloning failed on sentence chunk."
                    return False, err_msg, None

                # Read chunk audio data
                data, sr_rate = sf.read(chunk_file)
                if data.ndim > 1:
                    data = data.mean(axis=1)
                target_sr = sr_rate
                chunk_audio_arrays.append(data)

                # Add natural breathing pause between sentences
                if idx < len(chunks) - 1:
                    pause_samples = int(target_sr * (pause_ms / 1000.0))
                    chunk_audio_arrays.append(np.zeros(pause_samples, dtype=np.float32))

            # Concatenate chunks
            combined_audio = np.concatenate(chunk_audio_arrays)

            # Peak normalize cleanly without pitch warping
            max_val = np.max(np.abs(combined_audio))
            if max_val > 0.01:
                combined_audio = (combined_audio / max_val) * 0.94

            out_filename = f"cloned_{uuid.uuid4().hex[:8]}.wav"
            final_path = OUTPUT_DIR / out_filename
            sf.write(str(final_path), combined_audio, target_sr)

            return True, str(final_path), f"{active_engine} • ({len(chunks)} Chunks)"
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
        Generates high-definition neural speech using Microsoft Edge Neural TTS.
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
            return True, str(final_path), f"Studio Neural ({voice})"
        except Exception as e:
            return False, f"Neural TTS generation error: {str(e)}", "Neural"

tts_engine = TTSEngine()
