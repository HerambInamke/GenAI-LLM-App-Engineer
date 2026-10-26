"""Twilio Voice + Media Streams (FR-6.1, FR-6.2, FR-6.6, FR-7.2) and a text call-in for demos.

The phone number (`From`) is never read: callers become a random id at the webhook.
"""

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import time
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel, Field, StringConstraints
from starlette.websockets import WebSocketDisconnect

from deadair.calls.audio import down_to_phone, mulaw_decode, mulaw_encode
from deadair.calls.bargein import BargeIn
from deadair.calls.stt import DeepgramSTT, stt_available
from deadair.web.ratelimit import RateLimit

log = logging.getLogger(__name__)
PACKET = 160  # 20 ms of 8 kHz mu-law


def valid_signature(url: str, params: dict[str, str], signature: str, token: str) -> bool:
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def twiml(body: str) -> Response:
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
        media_type="application/xml",
    )


class TextCall(BaseModel):
    lines: list[Annotated[str, StringConstraints(min_length=1, max_length=300)]] = Field(
        min_length=1, max_length=4
    )


def call_router(rt) -> APIRouter:
    router = APIRouter()

    def calls_for(sid: str):
        if sid not in rt.calls:
            raise HTTPException(404, "unknown station")
        return rt.calls[sid]

    # ---------- phone ----------
    @router.post("/twilio/voice/{sid}")
    async def voice(sid: str, request: Request) -> Response:
        calls_for(sid)
        token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        form = {k: str(v) for k, v in (await request.form()).items()}
        public = os.environ.get("PUBLIC_URL", "").rstrip("/")
        url = (public + request.url.path) if public else str(request.url)
        if not token or not valid_signature(
            url, form, request.headers.get("X-Twilio-Signature", ""), token
        ):
            raise HTTPException(403, "bad Twilio signature")
        name = escape(next(s.name for s in rt.cfg.stations if s.id == sid))
        if not stt_available():
            return twiml(
                f"<Say>Thanks for calling {name}. The phone line is closed right now.</Say>"
            )
        host = (public or str(request.base_url).rstrip("/")).split("://", 1)[1]
        return twiml(
            f"<Say>You are calling {name}. Stay on the line.</Say>"
            f'<Connect><Stream url="wss://{host}/twilio/media/{sid}"/></Connect>'
        )

    @router.websocket("/twilio/media/{sid}")
    async def media(ws: WebSocket, sid: str) -> None:
        cm = calls_for(sid)
        station, caster = rt.stations[sid], rt.casters[sid]
        await ws.accept()
        caller, stream_sid, sender = None, None, None
        barge = BargeIn(station, caster, cm)
        tap: asyncio.Queue = asyncio.Queue(maxsize=100)

        async def send_station_audio():
            while True:
                phone = mulaw_encode(down_to_phone(await tap.get()))
                for i in range(0, len(phone), PACKET):
                    payload = base64.b64encode(phone[i : i + PACKET]).decode()
                    await ws.send_text(
                        json.dumps(
                            {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": payload},
                            }
                        )
                    )

        stt = DeepgramSTT(
            os.environ["DEEPGRAM_API_KEY"],
            lambda text, t: caller and cm.hear(caller.id, text, t),
        )
        try:
            async with stt:
                while True:
                    msg = json.loads(await ws.receive_text())
                    event = msg.get("event")
                    if event == "start":
                        stream_sid = msg["start"]["streamSid"]
                        caller, decision = cm.new_call()
                        if decision == "rejected":
                            break
                        caster.phone_taps.add(tap)
                        sender = asyncio.create_task(send_station_audio())
                    elif event == "media" and caller:
                        raw = base64.b64decode(msg["media"]["payload"])
                        barge.feed(caller, mulaw_decode(raw))
                        await stt.send(raw)
                    elif event == "dtmf" and caller:  # keypad vote (FR-7.2)
                        if vote := station.votes.active(sid):
                            station.votes.cast(vote.id, f"call-{caller.id}", msg["dtmf"]["digit"])
                    elif event == "stop":
                        break
        except WebSocketDisconnect:
            pass
        finally:
            station.meter.add_usd(stt.minutes * rt.cfg.pricing.stt_usd_per_minute)  # NFR-6
            caster.phone_taps.discard(tap)
            if sender:
                sender.cancel()
            if caller:
                cm.hang_up(caller.id)

    # ---------- text call-in (works with no telephony keys) ----------
    @router.post("/api/call/{sid}", dependencies=[Depends(RateLimit(3, 60))])
    async def text_call(sid: str, body: TextCall) -> dict:
        cm = calls_for(sid)
        caller, decision = cm.new_call()
        if decision == "queued":
            rt.spawn(feed_text_call(cm, caller, body.lines))
        return {"call_id": caller.id, "status": decision, "waiting": len(cm.waiting)}

    @router.get("/api/call/{sid}/{call_id}")
    def call_status(sid: str, call_id: str) -> dict:
        cm = calls_for(sid)
        c = cm.callers.get(call_id)
        if not c:
            raise HTTPException(404, "unknown call")
        return {"on_air": c is cm.on_air, "hung_up": c.hung_up, "transcript": c.transcript}

    return router


async def feed_text_call(
    cm, caller, lines: list[str], gap: float = 1.0, timeout: float = 900
) -> None:
    """Deliver scripted lines one at a time, each after the host answered the previous one."""
    deadline = time.monotonic() + timeout

    def greeted() -> bool:
        return any(t.startswith("host:") for t in caller.transcript)

    while not (cm.on_air is caller and greeted()) and not caller.hung_up:
        if time.monotonic() > deadline:
            return
        await asyncio.sleep(0.1)
    for line in lines:
        if caller.hung_up:
            return
        await asyncio.sleep(gap)
        heard = len(caller.transcript)
        if not cm.hear(caller.id, line):
            return
        while len(caller.transcript) <= heard + 1 and not caller.hung_up:
            if time.monotonic() > deadline:
                return
            await asyncio.sleep(0.05)  # wait for the host's reply
    await asyncio.sleep(gap)
    with contextlib.suppress(KeyError):
        cm.hang_up(caller.id)
