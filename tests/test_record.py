from pathlib import Path

from deadair.record import record_episode


async def test_render_short_episode(tmp_path, monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    out = await record_episode(
        2.0, tmp_path / "rec", str(tmp_path / "r.db"), call_at=0.3, vote_at=0.6
    )
    hosts = {"deadair": "max:", "rival": "dex:"}
    for sid, path in out["files"].items():
        mp3 = Path(path)
        assert mp3.stat().st_size > 2 * 60 * 64_000 / 8 * 0.9  # ~2 minutes at 64 kbps
        text = mp3.with_suffix(".txt").read_text(encoding="utf-8")
        assert "[news]" in text and hosts[sid] in text
    main = Path(out["files"]["deadair"]).with_suffix(".txt").read_text(encoding="utf-8")
    assert "[caller]" in main  # the scripted caller made it on air
    assert len(list((tmp_path / "rec" / "deadair").glob("*.mp3"))) == 1  # one file per episode
