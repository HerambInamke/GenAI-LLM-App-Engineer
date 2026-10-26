import asyncio

import numpy as np

from deadair.audio.broadcast import FRAME, Broadcaster
from deadair.audio.mixer import DUCK, BedPlayer, make_bed
from deadair.audio.tts import SR, SynthTTS
from deadair.config import load_config
from deadair.station import Event, Station


def rms(x):
    return float(np.sqrt(np.mean(x**2)))


def test_ducking_is_about_12_db():
    bed = make_bed("lo-fi synth")
    p = BedPlayer(bed)
    open_frames = [p.frame(FRAME, False) for _ in range(40)]
    p.frame(FRAME, True)  # ramp frame
    ducked = [p.frame(FRAME, True) for _ in range(40)]
    db = 20 * np.log10(rms(np.concatenate(ducked)) / rms(np.concatenate(open_frames)))
    assert abs(db - 20 * np.log10(DUCK)) < 1.5, db


async def test_synth_voices_are_distinct_and_stream():
    tts = SynthTTS()
    a = [c async for c in tts.synth("hello there radio", "voice-a")]
    assert len(a) == 3 and all(c.dtype == np.float32 for c in a)  # one chunk per word
    assert tts._f0("voice-a") != tts._f0("voice-b")


async def test_line_plays_records_and_barge_in_cuts(tmp_path):
    b = Broadcaster("deadair", "lo-fi synth", tmp_path, SynthTTS(), realtime=False)
    b.rotate("blk1")
    await b.emit(Event("line", "deadair", "max", "Testing one two three", "v1"))
    assert b.ahead > 0.5
    q = b.subscribe()
    for _ in range(5):
        b.tick()
    assert b.speaking_since is not None and not q.empty()
    b.cut()  # barge-in: speech must be gone by the very next frame (<= 50 ms)
    assert b.ahead == 0
    b.tick()
    assert b.speaking_since is None
    b.rotate("blk2")
    mp3 = next((tmp_path / "deadair").glob("*_blk1.mp3"))
    assert mp3.stat().st_size > 0
    assert "Testing one two three" in mp3.with_suffix(".txt").read_text()


async def test_tts_failure_falls_back(tmp_path):
    class DeadTTS:
        async def synth(self, text, voice_id):
            raise RuntimeError("tts down")
            yield  # pragma: no cover

    b = Broadcaster("deadair", "lo-fi synth", tmp_path, DeadTTS(), "Dead Air", realtime=False)
    await b.fallback()  # warm the station ID so the size check below is exact
    b.queue.clear()
    queued = []
    b.enqueue = lambda pcm, ducked: queued.append(len(pcm))  # observe instead of playing
    await b.emit(Event("line", "deadair", "max", "Hello", "v1"))
    assert b.tts_failures == 1 and sum(queued) / SR > 5  # sting + station ID + music bed


async def test_thirty_minute_stream_has_no_dropouts(db, tmp_path):
    """Step 5 test (simulated clock): 30 minutes of continuous MP3 while the station runs."""
    cfg = load_config()
    st = Station(cfg, "deadair", db, rival_id="rival", seed=5)
    b = Broadcaster("deadair", "lo-fi synth", tmp_path, SynthTTS(), realtime=False)
    frames_needed = int(30 * 60 * SR / FRAME)
    produced, silent = 0, 0

    async def station_loop():
        while True:
            await st.run_block(b.emit)

    task = asyncio.create_task(station_loop())
    total = 0
    while produced < frames_needed:
        await asyncio.sleep(0)  # let the station generate between frames
        frame = b.next_frame()
        produced += 1
        silent += rms(frame) < 1e-4
        total += len(b.encoder.encode((frame * 32767).astype("<i2").tobytes()))
    task.cancel()
    assert silent == 0  # the bed always plays, so there is never dead air
    assert total > 30 * 60 * 64_000 / 8 * 0.9  # ~64 kbps for the whole half hour
    assert db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] >= 2
