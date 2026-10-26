"""Barge-in (FR-6.5, NFR-2): caller speech while the host talks cuts playback at once.

A local energy VAD decides, so detection does not wait on the STT round trip.
"""

import time

import numpy as np

from deadair.calls.audio import PHONE_SR, rms, up_to_station
from deadair.calls.manager import Caller, CallManager

VOICE_RMS = 0.02  # tuned for 8 kHz mu-law phone audio
MIN_VOICED_MS = 60  # ignore clicks and single noisy packets


class BargeIn:
    def __init__(self, station, caster, calls: CallManager):
        self.station, self.caster, self.calls = station, caster, calls
        self.voiced_ms = 0.0

    def feed(self, caller: Caller, pcm8k: np.ndarray) -> bool:
        """Handle one packet of caller audio. Returns True if it triggered a barge-in."""
        if caller is not self.calls.on_air:
            return False  # queued callers are not on air
        self.caster.add_caller_audio(up_to_station(pcm8k))  # FR-6.4 mixed on air
        if rms(pcm8k) < VOICE_RMS:
            self.voiced_ms = 0.0
            return False
        self.voiced_ms += 1000 * len(pcm8k) / PHONE_SR
        if self.voiced_ms < MIN_VOICED_MS or not self.caster.host_speaking():
            return False
        detected = time.monotonic()
        self.caster.cut()
        self.station.interrupt.set()
        caller.barge_in.set()
        self.caster.stop_marks.append(detected)  # the clock reports when playback really stopped
        self.voiced_ms = 0.0
        return True
