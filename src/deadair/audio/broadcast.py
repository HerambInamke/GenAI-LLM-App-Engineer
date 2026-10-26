"""Per-station audio clock: mixes speech over the bed, encodes MP3, fans out to listeners, records.

The clock never waits for the LLM: when no speech is queued, the bed plays (TRD T-6). Station
emits block on `emit` only while more than MAX_AHEAD seconds are queued, so generation runs just
ahead of playback.
"""

import asyncio
import contextlib
import logging
import os
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import lameenc
import numpy as np

from deadair.audio.mixer import BedPlayer, make_bed, stinger, to_pcm16
from deadair.audio.tts import SR, SynthTTS
from deadair.station import Event

log = logging.getLogger(__name__)
FRAME_S = 0.05
FRAME = int(SR * FRAME_S)
MAX_AHEAD = 2.0


class Broadcaster:
    def __init__(
        self,
        station_id: str,
        style: str,
        recordings: Path,
        tts,
        station_name: str = "",
        realtime: bool = True,
    ):
        self.id, self.style, self.tts, self.realtime = station_id, style, tts, realtime
        self.dir = recordings / station_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bed = BedPlayer(make_bed(style, station_id))
        self.sting = stinger(style)
        self.queue: deque[tuple[np.ndarray, bool]] = deque()  # (samples, ducked)
        self.caller = np.zeros(0, np.float32)  # live caller audio mixed on air (FR-6.4)
        self.listeners: set[asyncio.Queue] = set()
        self.phone_taps: set[asyncio.Queue] = set()  # station audio, without callers, for phones
        self.encoder = self._encoder()
        # NFR-8: the archive copy is encoded without caller audio unless explicitly enabled
        self.store_call_audio = os.environ.get("DEADAIR_STORE_CALL_AUDIO") == "1"
        self.record_encoder = self._encoder()
        self.line_started_at = 0.0  # monotonic time the latest line's first audio was queued
        self.stop_marks: list[float] = []  # barge-in detection times awaiting a silent frame
        self.stop_ms: list[float] = []  # NFR-2 samples: detection -> playback stopped
        self.record_mp3 = self.record_txt = None
        self.station_name = station_name or station_id
        self.station_id_audio: np.ndarray | None = None
        self.speaking_since: float | None = None
        self.frames = 0
        self.tts_failures = 0

    @staticmethod
    def _encoder() -> lameenc.Encoder:
        e = lameenc.Encoder()
        e.set_bit_rate(64)
        e.set_in_sample_rate(SR)
        e.set_channels(1)
        e.set_quality(5)
        return e

    # ---------- queue ----------
    @property
    def ahead(self) -> float:
        return sum(len(x) for x, _ in self.queue) / SR

    def enqueue(self, pcm: np.ndarray, ducked: bool) -> None:
        if len(pcm):
            self.queue.append((pcm.astype(np.float32), ducked))

    def add_caller_audio(self, pcm: np.ndarray) -> None:
        self.caller = np.concatenate([self.caller[-SR * 2 :], pcm])  # keep at most ~2 s queued

    def host_speaking(self) -> bool:
        return any(ducked for _, ducked in self.queue)

    def cut(self) -> float:
        """Barge-in / skip: drop queued speech now. Returns the monotonic time of the cut."""
        self.queue.clear()
        self.speaking_since = None
        return time.monotonic()

    def _take(self, n: int) -> tuple[np.ndarray, bool]:
        out, ducked, got = np.zeros(n, np.float32), False, 0
        while got < n and self.queue:
            pcm, d = self.queue[0]
            k = min(n - got, len(pcm))
            out[got : got + k] = pcm[:k]
            ducked |= d
            if k == len(pcm):
                self.queue.popleft()
            else:
                self.queue[0] = (pcm[k:], d)
            got += k
        return out, ducked

    def next_frame(self) -> np.ndarray:
        return self.next_frames()[0]

    def next_frames(self) -> tuple[np.ndarray, np.ndarray]:
        """(on-air mix, the same mix without caller audio)."""
        speech, ducked = self._take(FRAME)
        if self.stop_marks and not ducked:
            now = time.monotonic()
            self.stop_ms += [1000 * (now - t) for t in self.stop_marks]
            self.stop_marks.clear()
        caller = np.zeros(FRAME, np.float32)
        if len(self.caller):
            c, self.caller = self.caller[:FRAME], self.caller[FRAME:]
            caller[: len(c)] = c
            ducked = True
        self.speaking_since = (self.speaking_since or time.monotonic()) if ducked else None
        dry = self.bed.frame(FRAME, ducked) + speech
        return dry + caller, dry

    # ---------- station emitter ----------
    async def _wait_room(self) -> None:
        while self.ahead > MAX_AHEAD:
            await asyncio.sleep(FRAME_S if self.realtime else 0)

    async def _speak(self, text: str, voice_id: str) -> None:
        first = True
        async for pcm in self.tts.synth(text, voice_id):
            self.enqueue(pcm * 0.9, True)
            if first:
                self.line_started_at, first = time.monotonic(), False
            await self._wait_room()

    async def emit(self, ev: Event) -> None:
        if ev.kind == "block":
            self.rotate(ev.data.get("block_id", "block"))
        elif ev.kind == "line":
            self._transcript(f"{ev.host}: {ev.text}")
            try:
                await self._speak(ev.text, ev.voice_id)
            except Exception as e:  # noqa: BLE001 - NFR-4: bed plus station ID, keep going
                self.tts_failures += 1
                log.warning("[%s] TTS failed, falling back: %s", self.id, e)
                await self.fallback()
            self.enqueue(np.zeros(int(SR * 0.25)), True)  # breath between lines
        elif ev.kind == "music":
            self.enqueue(np.zeros(int(SR * ev.seconds)), False)
        elif ev.kind == "sting":
            self.enqueue(self.sting, False)
        await self._wait_room()

    async def fallback(self) -> None:
        if self.station_id_audio is None:
            parts = [p async for p in SynthTTS().synth(f"This is {self.station_name}", "station")]
            self.station_id_audio = np.concatenate(parts)
        self.enqueue(self.sting, False)
        self.enqueue(self.station_id_audio, True)
        self.enqueue(np.zeros(SR * 5), False)

    # ---------- recorder (FR-5.6) ----------
    def rotate(self, block_id: str) -> None:
        for f in (self.record_mp3, self.record_txt):
            if f:
                f.close()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        base = self.dir / f"{stamp}_{block_id}"
        self.record_mp3 = open(base.with_suffix(".mp3"), "wb")  # noqa: SIM115 - held open per block
        self.record_txt = open(base.with_suffix(".txt"), "w", encoding="utf-8")  # noqa: SIM115

    def close(self) -> None:
        for f in (self.record_mp3, self.record_txt):
            if f:
                f.close()
        self.record_mp3 = self.record_txt = None

    def _transcript(self, line: str) -> None:
        if self.record_txt:
            self.record_txt.write(line + "\n")
            self.record_txt.flush()

    # ---------- clock ----------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=400)
        self.listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.listeners.discard(q)

    def tick(self) -> bytes:
        live, dry = self.next_frames()
        mp3 = bytes(self.encoder.encode(to_pcm16(live)))
        archive = mp3 if self.store_call_audio else bytes(self.record_encoder.encode(to_pcm16(dry)))
        self.frames += 1
        if archive and self.record_mp3:
            self.record_mp3.write(archive)
        for q in list(self.phone_taps):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(dry)
        if mp3:
            for q in list(self.listeners):
                try:
                    q.put_nowait(mp3)
                except asyncio.QueueFull:
                    pass  # slow listener drops audio; the station never waits for listeners
        return mp3

    async def run(self) -> None:
        start = time.monotonic()
        while True:
            self.tick()
            if self.realtime:
                await asyncio.sleep(max(0.0, start + self.frames * FRAME_S - time.monotonic()))
            else:
                await asyncio.sleep(0)
