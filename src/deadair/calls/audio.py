"""Telephone audio helpers: G.711 mu-law and 8 kHz <-> 24 kHz resampling (Twilio Media Streams)."""

import numpy as np

from deadair.audio.tts import SR

PHONE_SR = 8000
_BIAS, _CLIP = 0x84, 32635


def mulaw_decode(data: bytes) -> np.ndarray:
    u = ~np.frombuffer(data, np.uint8)
    sign, exp, mant = u & 0x80, (u >> 4) & 0x07, u & 0x0F
    mag = ((mant.astype(np.int32) << 3) + _BIAS) << exp
    pcm = np.where(sign, _BIAS - mag, mag - _BIAS)
    return (pcm / 32768).astype(np.float32)


def mulaw_encode(x: np.ndarray) -> bytes:
    pcm = np.clip(x * 32768, -_CLIP, _CLIP).astype(np.int32)
    sign = np.where(pcm < 0, 0x80, 0)
    mag = np.abs(pcm) + _BIAS
    exp = np.clip(np.floor(np.log2(np.maximum(mag, 1))).astype(np.int32) - 7, 0, 7)
    mant = (mag >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mant) & 0xFF).astype(np.uint8).tobytes()


def up_to_station(x: np.ndarray) -> np.ndarray:
    """8 kHz -> 24 kHz by linear interpolation."""
    n = len(x) * (SR // PHONE_SR)
    return np.interp(np.arange(n) / (SR // PHONE_SR), np.arange(len(x)), x).astype(np.float32)


def down_to_phone(x: np.ndarray) -> np.ndarray:
    """24 kHz -> 8 kHz: 3-tap average as a cheap low-pass, then decimate."""
    k = SR // PHONE_SR
    usable = len(x) - len(x) % k
    return x[:usable].reshape(-1, k).mean(axis=1).astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0
