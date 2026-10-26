"""Streaming STT via Deepgram (FR-6.2). Telephone mu-law in, final utterances out."""

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)
URL = (
    "wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&channels=1"
    "&interim_results=true&endpointing=300&smart_format=true&model=nova-3"
)

OnUtterance = Callable[[str, float], Awaitable[None] | None]


class DeepgramSTT:
    """One websocket per call. `send()` raw mu-law; `on_utterance(text, ended_at)` per sentence."""

    def __init__(self, api_key: str, on_utterance: OnUtterance):
        self.key, self.on_utterance = api_key, on_utterance
        self.ws = None
        self.reader: asyncio.Task | None = None
        self.parts: list[str] = []

    async def __aenter__(self):
        import websockets

        self.ws = await websockets.connect(
            URL, additional_headers={"Authorization": f"Token {self.key}"}
        )
        self.reader = asyncio.create_task(self._read())
        return self

    async def __aexit__(self, *exc):
        if self.ws:
            await self.ws.send(json.dumps({"type": "CloseStream"}))
            await self.ws.close()
        if self.reader:
            self.reader.cancel()

    async def send(self, mulaw: bytes) -> None:
        await self.ws.send(mulaw)

    async def _read(self) -> None:
        async for msg in self.ws:
            data = json.loads(msg)
            if data.get("type") != "Results":
                continue
            alt = data["channel"]["alternatives"][0]
            if data.get("is_final") and alt.get("transcript"):
                self.parts.append(alt["transcript"])
            if data.get("speech_final") and self.parts:
                text, self.parts = " ".join(self.parts), []
                result = self.on_utterance(text, time.monotonic())
                if asyncio.iscoroutine(result):
                    await result


def stt_available() -> bool:
    return bool(os.environ.get("DEEPGRAM_API_KEY"))
