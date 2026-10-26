"""`python -m deadair doctor`: which providers are live, and does each key actually work?

Only free, read-only calls: Claude model lookup, ElevenLabs voice lookup, Deepgram project list.
"""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from deadair.audio.broadcast import dir_size_mb
from deadair.config import Config, load_config
from deadair.db import connect


@dataclass
class Check:
    name: str
    status: str  # OK | OFF | WARN | FAIL
    detail: str


async def check_claude(cfg: Config) -> list[Check]:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return [Check("Claude", "OFF", "no key: template hosts, rule-only gate, default planner")]
    import anthropic

    client = anthropic.AsyncAnthropic(timeout=15, max_retries=0)
    out = []
    for model in dict.fromkeys([cfg.llm.host_model, cfg.llm.fast_model]):
        try:
            await client.models.retrieve(model)
            out.append(Check(f"Claude {model}", "OK", "key works, model available"))
        except anthropic.AuthenticationError:
            out.append(Check(f"Claude {model}", "FAIL", "key rejected"))
        except anthropic.NotFoundError:
            out.append(Check(f"Claude {model}", "FAIL", "model not available to this key"))
        except anthropic.APIError as e:
            out.append(Check(f"Claude {model}", "WARN", f"could not check: {e}"))
    return out


async def check_elevenlabs(cfg: Config, http: httpx.AsyncClient) -> list[Check]:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return [Check("ElevenLabs", "OFF", "no key: synthetic voices")]
    out = []
    voices = {pid: p.voice_id for pid, p in cfg.personas.items()} | {"caller": cfg.caller_voice_id}
    for pid, voice_id in voices.items():
        if voice_id.startswith("TBD"):
            out.append(Check(f"voice {pid}", "FAIL", "placeholder voice id in config"))
            continue
        try:
            r = await http.get(
                f"https://api.elevenlabs.io/v1/voices/{voice_id}", headers={"xi-api-key": key}
            )
            status = {200: "OK", 401: "FAIL", 404: "FAIL"}.get(r.status_code, "WARN")
            out.append(Check(f"voice {pid}", status, f"{voice_id}: HTTP {r.status_code}"))
        except httpx.HTTPError as e:
            out.append(Check(f"voice {pid}", "WARN", f"could not check: {e}"))
    return out


async def check_deepgram(http: httpx.AsyncClient) -> list[Check]:
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        return [Check("Deepgram", "OFF", "no key: phone line answers closed, text call-in works")]
    try:
        r = await http.get(
            "https://api.deepgram.com/v1/projects", headers={"Authorization": f"Token {key}"}
        )
    except httpx.HTTPError as e:
        return [Check("Deepgram", "WARN", f"could not check: {e}")]
    return [Check("Deepgram", "OK" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")]


def check_local(cfg: Config, db_path: str) -> list[Check]:
    db = connect(db_path)
    n, newest = db.execute("SELECT COUNT(*), MAX(published_at) FROM feed_items").fetchone()
    out = [
        Check("Config", "OK", f"{len(cfg.stations)} stations, {len(cfg.personas)} personas"),
        Check(
            "Feed",
            "OK" if n else "WARN",
            f"{n} items, newest {newest}" if n else "empty: run python -m deadair.feed --once",
        ),
        Check(
            "Admin",
            "OK" if os.environ.get("ADMIN_PASSWORD") else "WARN",
            "password set"
            if os.environ.get("ADMIN_PASSWORD")
            else "ADMIN_PASSWORD unset: /admin locked",
        ),
    ]
    size = dir_size_mb(Path("recordings"))
    out.append(
        Check(
            "Recordings", "OK", f"{size:.0f} MB on disk, kept {cfg.recording_retention_days} days"
        )
    )
    twilio = os.environ.get("TWILIO_AUTH_TOKEN"), os.environ.get("PUBLIC_URL")
    if not any(twilio):
        out.append(Check("Twilio", "OFF", "no token: text call-in only"))
    elif not all(twilio):
        out.append(Check("Twilio", "FAIL", "needs both TWILIO_AUTH_TOKEN and PUBLIC_URL"))
    else:
        out.append(Check("Twilio", "OK", f"webhook: {twilio[1].rstrip('/')}/twilio/voice/deadair"))
    return out


async def run(db_path: str, http: httpx.AsyncClient | None = None) -> list[Check]:
    cfg = load_config()
    async with http or httpx.AsyncClient(timeout=15) as client:
        remote = await asyncio.gather(
            check_claude(cfg), check_elevenlabs(cfg, client), check_deepgram(client)
        )
    return check_local(cfg, db_path) + [c for group in remote for c in group]


def render(checks: list[Check]) -> str:
    width = max(len(c.name) for c in checks)
    return "\n".join(f"{c.status:<5} {c.name:<{width}}  {c.detail}" for c in checks)
