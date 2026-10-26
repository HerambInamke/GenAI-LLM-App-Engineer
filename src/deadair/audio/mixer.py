"""Music bed, ducking and stingers (FR-5.3, FR-5.4). All audio is float32 mono at SR.

shortcut: beds and stingers are generated procedurally; drop royalty-free 24 kHz mono WAVs in
assets/music/<station>/ to use real tracks instead.
"""

import os
import wave
from pathlib import Path

import numpy as np

from deadair.audio.tts import SR

DUCK_DB = -12.0
DUCK = 10 ** (DUCK_DB / 20)  # ~0.25 linear
BED_LEVEL = 0.22
ASSETS = Path(os.environ.get("DEADAIR_ASSETS", "assets")) / "music"

STYLES = {  # (root Hz per chord, seconds per chord)
    "lo-fi synth": ([220.0, 174.6, 196.0, 164.8], 4.0),
    "brash rock": ([146.8, 196.0, 174.6, 220.0], 2.0),
}


def _load_wavs(station: str) -> np.ndarray | None:
    tracks = []
    for p in sorted((ASSETS / station).glob("*.wav")):
        with wave.open(str(p)) as w:
            if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
                continue  # only 24 kHz mono 16-bit, so no resampling dependency is needed
            tracks.append(np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768)
    return np.concatenate(tracks).astype(np.float32) if tracks else None


def make_bed(style: str, station: str = "") -> np.ndarray:
    """A seamless loop: real tracks if present, else a soft chord pad."""
    real = _load_wavs(station)
    if real is not None:
        return real
    roots, secs = STYLES.get(style, STYLES["lo-fi synth"])
    n = int(SR * secs)
    t = np.arange(n) / SR
    env = np.minimum(1, np.minimum(t, secs - t) / 0.3)
    chords = []
    for r in roots:
        tone = sum(np.sin(2 * np.pi * r * k * t) / k for k in (1, 1.25, 1.5, 2))
        if "rock" in style:  # a soft pulse on every beat
            tone *= 0.7 + 0.3 * (np.sin(2 * np.pi * 2 * t) > 0)
        chords.append(tone * env)
    bed = np.concatenate(chords)
    return (bed / np.abs(bed).max()).astype(np.float32)


def stinger(style: str = "") -> np.ndarray:
    t = np.arange(int(SR * 0.6)) / SR
    notes = [880, 1318.5] if "rock" not in style else [587.3, 784]
    out = np.zeros_like(t)
    for i, f in enumerate(notes):
        start = i * 0.15
        seg = t >= start
        out[seg] += np.sin(2 * np.pi * f * (t[seg] - start)) * np.exp(-6 * (t[seg] - start))
    return (out * 0.35).astype(np.float32)


class BedPlayer:
    """Loops the bed and applies a smooth gain ramp toward the duck target each frame."""

    def __init__(self, bed: np.ndarray):
        self.bed, self.pos, self.gain = bed, 0, 1.0

    def frame(self, n: int, ducked: bool) -> np.ndarray:
        idx = (self.pos + np.arange(n)) % len(self.bed)
        self.pos = (self.pos + n) % len(self.bed)
        target = DUCK if ducked else 1.0
        # ramp over the frame (~50 ms) so ducking never clicks
        ramp = np.linspace(self.gain, target, n, dtype=np.float32)
        self.gain = target
        return self.bed[idx] * ramp * BED_LEVEL


def to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
