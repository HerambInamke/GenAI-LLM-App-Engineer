"""Web app: player, live MP3 stream, votes, admin, archive (FR-9, docs/api-architecture.md)."""

import asyncio
import json
import logging
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from deadair.audio.broadcast import Broadcaster, prune_recordings
from deadair.audio.tts import get_tts
from deadair.calls.manager import CallManager
from deadair.calls.twilio import call_router
from deadair.config import load_config
from deadair.db import connect
from deadair.feed.pollers import poll_all
from deadair.feed.store import FeedStore
from deadair.providers.llm import get_llm
from deadair.station import Station
from deadair.web.ratelimit import RateLimit

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
SAFE_FILE = re.compile(r"^[\w.-]+\.(mp3|txt)$")
basic = HTTPBasic(auto_error=True)


class Runtime:
    """Everything the station needs, built once per app."""

    def __init__(self, db_path: str, recordings: Path, realtime: bool = True):
        self.cfg = load_config()
        self.db = connect(db_path)
        self.llm = get_llm()
        self.tts = get_tts()
        self.recordings = recordings
        ids = [s.id for s in self.cfg.stations]
        self.stations = {
            sid: Station(
                self.cfg, sid, self.db, self.llm, rival_id=next((o for o in ids if o != sid), "")
            )
            for sid in ids
        }
        self.casters = {
            s.id: Broadcaster(s.id, s.music_style, recordings, self.tts, s.name, realtime)
            for s in self.cfg.stations
        }
        self.calls = {sid: CallManager(self.db, sid, recordings) for sid in self.stations}
        for sid, st in self.stations.items():
            st.calls, st.caster = self.calls[sid], self.casters[sid]
            self.casters[sid].meter = st.meter
            self.casters[sid].tts_usd_per_1k_chars = self.cfg.pricing.tts_usd_per_1k_chars
        self.tasks: list[asyncio.Task] = []

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    def spent_last_hour(self, sid: str) -> float:
        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        row = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM blocks WHERE station = ? AND planned_at >= ?",
            (sid, since),
        ).fetchone()
        return row[0]

    async def poll_feed(self) -> None:
        store = FeedStore(self.db)
        while True:
            try:
                store.add(await poll_all(self.cfg.feeds.sources, self.llm, self.cfg.llm.fast_model))
            except Exception:  # noqa: BLE001 - keep reading the stored pool
                log.exception("feed poll failed")
            await asyncio.sleep(self.cfg.feeds.poll_minutes * 60)

    async def run_station(self, sid: str) -> None:
        station, caster = self.stations[sid], self.casters[sid]
        while True:
            try:
                if self.spent_last_hour(sid) >= self.cfg.budget_usd_per_hour:  # NFR-6 cap
                    log.warning("[%s] hourly budget reached, music only", sid)
                    await caster.fallback()
                    await asyncio.sleep(60)
                    continue
                await station.run_block(caster.emit)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - NFR-4: never let one block take the station down
                log.exception("[%s] block crashed, playing fallback", sid)
                await caster.fallback()
                await asyncio.sleep(1)

    async def prune_loop(self) -> None:
        while True:
            removed = prune_recordings(self.recordings, self.cfg.recording_retention_days)
            if removed:
                log.info("retention: removed %d old recordings", removed)
            await asyncio.sleep(3600)

    def start(self) -> None:
        self.tasks = [asyncio.create_task(self.poll_feed()), asyncio.create_task(self.prune_loop())]
        for sid in self.stations:
            self.tasks += [
                asyncio.create_task(self.casters[sid].run()),
                asyncio.create_task(self.run_station(sid)),
            ]

    async def stop(self) -> None:
        for t in self.tasks:
            t.cancel()
        for t in self.tasks:
            with suppress(asyncio.CancelledError):
                await t
        for c in self.casters.values():
            c.close()


class VoteIn(BaseModel):
    option: str


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str = Field("", max_length=500)


def create_app(
    db_path: str = "data/deadair.db",
    recordings: str | Path = "recordings",
    start: bool = True,
    realtime: bool = True,
) -> FastAPI:
    rt = Runtime(db_path, Path(recordings), realtime)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start:
            rt.start()
        yield
        await rt.stop()

    app = FastAPI(title="Dead Air", lifespan=lifespan)
    app.state.rt = rt
    app.include_router(call_router(rt))

    def station(sid: str) -> Station:
        if sid not in rt.stations:
            raise HTTPException(404, "unknown station")
        return rt.stations[sid]

    def admin(creds: HTTPBasicCredentials = Depends(basic)) -> None:
        pw = os.environ.get("ADMIN_PASSWORD", "")
        if not pw or not secrets.compare_digest(creds.password.encode(), pw.encode()):
            raise HTTPException(401, "admin password required", {"WWW-Authenticate": "Basic"})

    def now_payload(sid: str) -> dict:
        st = station(sid)
        vote = st.votes.active(sid)
        hosts = [rt.cfg.personas[h].name for h in st.now.get("hosts", []) if h]
        return {
            **st.now,
            "hosts": hosts,
            "vote": vote.model_dump() | {"tally": st.votes.tally(vote.id)} if vote else None,
        }

    # ---------- public ----------
    @app.get("/", response_class=HTMLResponse)
    def player() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "stations": {s: rt.casters[s].frames for s in rt.casters}}

    @app.get("/stream/{sid}.mp3")
    async def stream(sid: str, request: Request) -> StreamingResponse:
        station(sid)
        q = rt.casters[sid].subscribe()

        async def body():
            try:
                while not await request.is_disconnected():
                    try:
                        yield await asyncio.wait_for(q.get(), timeout=5)
                    except TimeoutError:
                        continue
            finally:
                rt.casters[sid].unsubscribe(q)

        return StreamingResponse(
            body(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"}
        )

    @app.get("/api/now/{sid}")
    def now(sid: str) -> dict:
        return now_payload(sid)

    @app.websocket("/ws/now/{sid}")
    async def ws_now(ws: WebSocket, sid: str) -> None:
        await ws.accept()
        last = None
        try:
            while True:
                payload = json.dumps(now_payload(sid))
                if payload != last:
                    await ws.send_text(payload)
                    last = payload
                await asyncio.sleep(1)
        except (WebSocketDisconnect, HTTPException):
            pass

    @app.post("/api/vote/{sid}", dependencies=[Depends(RateLimit(10, 60))])
    def vote(sid: str, body: VoteIn, request: Request, response: Response) -> dict:
        st = station(sid)
        v = st.votes.active(sid)
        if not v:
            raise HTTPException(409, "no open vote")
        voter = request.cookies.get("voter") or uuid.uuid4().hex
        response.set_cookie("voter", voter, httponly=True, samesite="lax", max_age=86400 * 30)
        ok = st.votes.cast(v.id, f"web-{voter}", body.option)
        if not ok:
            raise HTTPException(409, "already voted or invalid option")
        return {"ok": True, "tally": st.votes.tally(v.id)}

    @app.post("/api/rating", dependencies=[Depends(RateLimit(5, 60))])
    def rate(body: RatingIn, request: Request, response: Response) -> dict:
        """Listener rating form (Step 10). One rating per browser; a new one replaces it."""
        rater = request.cookies.get("voter") or uuid.uuid4().hex
        response.set_cookie("voter", rater, httponly=True, samesite="lax", max_age=86400 * 30)
        rt.db.execute(
            "INSERT OR REPLACE INTO ratings VALUES (?, ?, ?, ?)",
            (rater, body.score, body.comment, datetime.now(UTC).isoformat()),
        )
        rt.db.commit()
        return {"ok": True}

    @app.get("/archive", response_class=HTMLResponse)
    def archive_page() -> str:
        return (STATIC / "archive.html").read_text(encoding="utf-8")

    @app.get("/api/archive")
    def archive() -> list[dict]:
        out = []
        for sid in rt.stations:
            for p in sorted((rt.recordings / sid).glob("*.mp3"), reverse=True):
                if p.stat().st_size:
                    out.append(
                        {
                            "station": sid,
                            "file": p.name,
                            "bytes": p.stat().st_size,
                            "transcript": p.with_suffix(".txt").name,
                        }
                    )
        return out

    @app.get("/archive/{sid}/{name}")
    def archive_file(sid: str, name: str) -> FileResponse:
        station(sid)
        if not SAFE_FILE.match(name):
            raise HTTPException(400, "bad file name")
        path = rt.recordings / sid / name
        if not path.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(path, filename=name)

    # ---------- admin (FR-9.3) ----------
    @app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(admin)])
    def admin_page() -> str:
        return (STATIC / "admin.html").read_text(encoding="utf-8")

    @app.get("/api/admin/{sid}", dependencies=[Depends(admin)])
    def admin_state(sid: str) -> dict:
        st = station(sid)
        gate = rt.db.execute(
            "SELECT c.created_at, c.host, c.text, c.gate_result, c.claims_json FROM chunks c "
            "JOIN segments s ON c.segment_id = s.id JOIN blocks b ON s.block_id = b.id "
            "WHERE b.station = ? ORDER BY c.created_at DESC LIMIT 40",
            (sid,),
        ).fetchall()
        calls = rt.db.execute(
            "SELECT id, status, started_at FROM calls WHERE station = ? AND status IN "
            "('queued','on_air','held') ORDER BY started_at",
            (sid,),
        ).fetchall()
        return {
            "now": now_payload(sid),
            "plan": st.current_plan.model_dump() if st.current_plan else None,
            "storylines": [s.model_dump() for s in st.storylines.list(sid, status=None)],
            "gate_log": [dict(r) | {"claims": json.loads(r["claims_json"])} for r in gate],
            "calls": [dict(r) for r in calls],
            "spent_last_hour": rt.spent_last_hour(sid),
            "budget": rt.cfg.budget_usd_per_hour,
        }

    @app.post("/api/admin/{sid}/skip", dependencies=[Depends(admin)])
    def skip(sid: str) -> dict:
        station(sid).skip.set()
        rt.casters[sid].cut()
        return {"ok": True}

    @app.post("/api/admin/{sid}/vote/close", dependencies=[Depends(admin)])
    def close_vote(sid: str) -> dict:
        winner = station(sid).force_close_vote()
        if winner is None:
            raise HTTPException(409, "no open vote")
        # counting stops now; the result is applied and announced at the next block boundary
        return {"ok": True, "winner": winner}

    return app
