"""Text to speech (FR-5.1). ElevenLabs streaming when keyed; a synthetic babble voice offline.

Both yield float32 mono numpy chunks at SR, so playback can start on the first chunk (FR-5.2).
"""

import hashlib
import os
from collections.abc import AsyncIterator

import httpx
import numpy as np

SR = 24_000


class SynthTTS:
    """Offline stand-in: a pitched, syllable-timed babble, distinct per voice id."""

    billable = False

    def _f0(self, voice_id: str) -> float:
        return 95 + int(hashlib.md5(voice_id.encode()).hexdigest(), 16) % 130

    async def synth(self, text: str, voice_id: str) -> AsyncIterator[np.ndarray]:
        f0 = self._f0(voice_id)
        rng = np.random.default_rng(len(text))
        for word in text.split():
            syllables = max(1, round(len(word) / 3))
            parts = []
            for _ in range(syllables):
                dur = rng.uniform(0.09, 0.16)
                t = np.arange(int(SR * dur)) / SR
                pitch = f0 * (1 + 0.08 * rng.standard_normal()) * (1 - 0.15 * t / dur)
                phase = 2 * np.pi * np.cumsum(pitch) / SR
                formant = rng.uniform(1.5, 3.5)
                tone = np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.3 * np.sin(formant * phase)
                parts.append(tone * np.hanning(len(t)) * 0.3)
            parts.append(np.zeros(int(SR * 0.05)))
            yield np.concatenate(parts).astype(np.float32)


class ElevenLabsTTS:
    """Streams 24 kHz 16-bit PCM from ElevenLabs."""

    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format=pcm_24000"
    billable = True

    def __init__(self, api_key: str, model: str = "eleven_flash_v2_5"):
        self.key, self.model = api_key, model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(15, read=30))
        self.chars = 0  # for cost logging (NFR-6)

    async def synth(self, text: str, voice_id: str) -> AsyncIterator[np.ndarray]:
        self.chars += len(text)
        body = {"text": text, "model_id": self.model}
        async with self.client.stream(
            "POST", self.URL.format(voice=voice_id), headers={"xi-api-key": self.key}, json=body
        ) as resp:
            resp.raise_for_status()
            carry = b""
            async for data in resp.aiter_bytes():
                data = carry + data
                cut = len(data) - len(data) % 2  # keep whole 16-bit samples
                carry = data[cut:]
                if cut:
                    yield np.frombuffer(data[:cut], "<i2").astype(np.float32) / 32768


def get_tts():
    key = os.environ.get("ELEVENLABS_API_KEY")
    return ElevenLabsTTS(key) if key else SynthTTS()
