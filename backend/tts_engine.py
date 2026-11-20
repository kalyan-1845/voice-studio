import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Tuple
import edge_tts
from gradio_client import Client, handle_file

from .config import DEFAULT_HF_SPACE, OUTPUT_DIR, get_hf_token

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

    async def clone_voice_cloud(
        self,
        reference_audio_path: Path,
        reference_text: str,
        target_text: str,
        remove_silence: bool = True
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Clones voice using cloud-hosted F5-TTS / E2-TTS via Hugging Face.
        Returns: (success, result_filepath_or_error, engine_used)
        """
        try:
            loop = asyncio.get_event_loop()
            
            def _call_hf():
                client = self._get_hf_client()
                audio_file = handle_file(str(reference_audio_path))
                
                # Call named endpoint /predict
                return client.predict(
                    ref_audio=audio_file,
                    ref_text=reference_text if reference_text else "",
                    gen_text=target_text,
                    remove_silence=remove_silence,
                    api_name="/predict"
                )

            result_path = await loop.run_in_executor(None, _call_hf)

            if isinstance(result_path, (list, tuple)):
                generated_src = result_path[0]
            else:
                generated_src = result_path

            if not generated_src or not os.path.exists(str(generated_src)):
                return False, "Cloud generation produced no audio file.", None

            # Copy to outputs directory with unique name
            out_filename = f"cloned_{uuid.uuid4().hex[:8]}.wav"
            final_path = OUTPUT_DIR / out_filename
            shutil.copy(str(generated_src), str(final_path))

            return True, str(final_path), "F5-TTS (Cloud)"
        except Exception as e:
            return False, f"Cloud voice cloning error: {str(e)}", None

    async def generate_neural_tts(
        self,
        text: str,
        voice: str = "te-IN-MohanNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz"
    ) -> Tuple[bool, str, str]:
        """
        Generates high-definition neural speech using Edge Neural TTS.
        Native support for Telugu, Hindi, and English.
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
