import httpx

from deadair.doctor import run


async def test_offline_doctor(tmp_path, monkeypatch):
    for k in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ELEVENLABS_API_KEY",
        "DEEPGRAM_API_KEY",
        "TWILIO_AUTH_TOKEN",
        "PUBLIC_URL",
        "ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(k, raising=False)
    checks = {c.name: c for c in await run(str(tmp_path / "d.db"))}
    assert checks["Claude"].status == "OFF" and checks["ElevenLabs"].status == "OFF"
    assert checks["Feed"].status == "WARN" and checks["Admin"].status == "WARN"
    assert not any(c.status == "FAIL" for c in checks.values())


async def test_doctor_checks_keys_and_voice_ids(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "bad")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "t")
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.host)
        return httpx.Response(401 if "deepgram" in req.url.host else 200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    checks = {c.name: c for c in await run(str(tmp_path / "d.db"), http)}
    assert checks["voice max"].status == "FAIL"  # repo personas still have TBD placeholders
    assert checks["Deepgram"].status == "FAIL"
    assert checks["Twilio"].status == "FAIL"  # token without PUBLIC_URL
    assert "api.elevenlabs.io" not in seen  # placeholders are caught before any request
