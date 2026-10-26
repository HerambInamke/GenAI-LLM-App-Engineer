"""Evaluation harness (Step 10) and soak test (Step 12).

  python -m deadair.eval report [--live]     one Markdown report with every NFR number
  python -m deadair.eval soak --hours 6      accelerated soak; kills TTS part-way (NFR-4)

`--live` measures latency and the gate with the configured Claude/ElevenLabs keys in real time;
without it the offline providers run, which measures the pipeline but not provider speed.
"""

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from deadair.audio.broadcast import FRAME_S
from deadair.audio.tts import SynthTTS, get_tts
from deadair.config import load_config
from deadair.db import connect
from deadair.eval.measure import bargein_stop, call_latency, gate_accuracy
from deadair.eval.planted import fixture_items
from deadair.feed.store import FeedStore
from deadair.gate.claims import strip_citations
from deadair.hosts.memory import repetition_violations
from deadair.providers.llm import get_llm

REPORTS = Path("reports")


def pct(xs: list[float], p: float) -> float:
    return sorted(xs)[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")


def station_stats(db_path: str) -> dict:
    """Numbers read from a real station run's database (gate log, repetition, cost, ratings)."""
    if not Path(db_path).exists():
        return {}
    db = connect(db_path)
    since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    results = dict(db.execute("SELECT gate_result, COUNT(*) FROM chunks GROUP BY gate_result"))
    unsourced = 0
    for (claims,) in db.execute("SELECT claims_json FROM chunks WHERE gate_result != 'fallback'"):
        for c in json.loads(claims):
            unsourced += (
                c.get("ok", False)
                and bool(c.get("numbers") or c.get("entities"))
                and not c.get("citations")
            )
    jokey = db.execute(
        "SELECT c.host, c.text FROM chunks c JOIN segments s ON c.segment_id = s.id "
        "WHERE s.type IN ('banter','feud') AND c.gate_result IN ('pass','regen_pass') "
        "AND c.created_at >= ? ORDER BY c.created_at",
        (since,),
    ).fetchall()
    cfg = load_config()
    catch = {h: p.catchphrases for h, p in cfg.personas.items()}
    reps = repetition_violations([(h, strip_citations(t)) for h, t in jokey], catch)
    blocks = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cost_usd),0), MIN(planned_at), MAX(planned_at) "
        "FROM blocks WHERE planned_at >= ?",
        (since,),
    ).fetchone()
    hours = 0.0
    if blocks[2]:
        span = datetime.fromisoformat(blocks[3]) - datetime.fromisoformat(blocks[2])
        hours = max(span.total_seconds() / 3600, 10 / 60)
    ratings = db.execute("SELECT COUNT(*), AVG(score) FROM ratings").fetchone()
    return {
        "gate_results": results,
        "unsourced_aired": unsourced,
        "jokey_lines_24h": len(jokey),
        "repetition_violations": reps,
        "blocks_24h": blocks[0],
        "cost_usd_24h": blocks[1],
        "cost_per_hour": blocks[1] / hours if hours else 0.0,
        "ratings": {"count": ratings[0], "mean": ratings[1]},
    }


async def report(db_path: str, live: bool, out: Path) -> str:
    cfg = load_config()
    llm = get_llm() if live else None
    tts = get_tts() if live else SynthTTS()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        lat_db = connect(":memory:")
        FeedStore(lat_db).add(fixture_items())
        lat = await call_latency(lat_db, tmp / "lat", 30, llm, tts, realtime=live)
        stops = await bargein_stop(connect(":memory:"), tmp / "barge", 20)
        gate = await gate_accuracy(connect(":memory:"), fixture_items(), llm)
    st = station_stats(db_path)
    soak = (
        json.loads((REPORTS / "soak.json").read_text())
        if (REPORTS / "soak.json").exists()
        else None
    )

    def ok(b: bool) -> str:
        return "PASS" if b else "FAIL"

    caught = gate["false_caught"] / gate["false_total"]
    fp = gate["true_blocked"] / gate["true_total"]
    within = sum(ms < 300 for ms in stops) / len(stops)
    mode = "live providers, real time" if live else "offline providers (pipeline only)"
    rows = [
        (
            "NFR-1 caller latency (median, 30 turns)",
            f"{statistics.median(lat):.0f} ms (p95 {pct(lat, 0.95):.0f} ms)",
            "< 1500 ms",
            ok(statistics.median(lat) < 1500),
        ),
        (
            "NFR-2 barge-in stop < 300 ms",
            f"{within:.0%} of {len(stops)} (p95 {pct(stops, 0.95):.0f} ms)",
            ">= 95%",
            ok(within >= 0.95),
        ),
        (
            "NFR-3 planted false claims caught",
            f"{gate['false_caught']}/{gate['false_total']}",
            ">= 90%",
            ok(caught >= 0.9),
        ),
        (
            "NFR-3 true claims blocked",
            f"{gate['true_blocked']}/{gate['true_total']}",
            "< 10%",
            ok(fp < 0.1),
        ),
    ]
    if st:
        rows += [
            (
                "NFR-5 repetition (24 h, banter/feud)",
                f"{len(st['repetition_violations'])} violations in {st['jokey_lines_24h']} lines",
                "0",
                ok(not st["repetition_violations"]),
            ),
            (
                "Unsourced claims aired (gate log)",
                str(st["unsourced_aired"]),
                "0",
                ok(st["unsourced_aired"] == 0),
            ),
            (
                "NFR-6 cost per hour",
                f"${st['cost_per_hour']:.3f} ({st['blocks_24h']} blocks)",
                f"< ${cfg.budget_usd_per_hour:.2f}",
                ok(st["cost_per_hour"] < cfg.budget_usd_per_hour),
            ),
            (
                "Listener rating",
                f"{st['ratings']['mean'] or 0:.2f}/5 from {st['ratings']['count']} raters",
                "10 raters",
                ok(st["ratings"]["count"] >= 10),
            ),
        ]
    if soak:
        rows.append(
            (
                "NFR-4 soak",
                f"{soak['hours']} h ({soak['mode']}), {soak['unhandled']} unhandled, "
                f"{soak['tts_fallbacks']} TTS fallbacks",
                "0 unhandled, fallback works",
                ok(soak["unhandled"] == 0 and soak["tts_fallbacks"] > 0),
            )
        )
    lines = [
        "# Dead Air evaluation report",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · measurements: {mode}",
        "",
        "| Metric | Result | Target | Status |",
        "|---|---|---|---|",
        *[f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows],
        "",
    ]
    if st:
        lines += [f"Gate decisions in the station log: {st['gate_results']}", ""]
    if not live:
        lines += [
            "NFR-1 here times the pipeline with offline providers. "
            "Run `python -m deadair.eval report --live` with API keys for real provider latency.",
            "",
        ]
    lines += [
        "The NFR-3 claim set is generated from fixture headlines (`deadair/eval/planted.py`), "
        "so it is a regression check, not an independent benchmark.",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return "\n".join(lines)


class _Errors(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.count = 0

    def emit(self, record):
        self.count += 1


async def soak(hours: float, kill_at: float, kill_for_h: float) -> dict:
    """Accelerated soak: both stations, offline providers, simulated clock. TTS dies part-way."""
    from deadair.web.app import Runtime

    errors = _Errors()
    logging.getLogger().addHandler(errors)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ELEVENLABS_API_KEY", None)
        rt = Runtime(str(Path(tmp) / "soak.db"), Path(tmp) / "rec", realtime=False)
        FeedStore(rt.db).add(fixture_items())
        tasks = [asyncio.create_task(rt.casters[s].run()) for s in rt.stations]
        tasks += [asyncio.create_task(rt.run_station(s)) for s in rt.stations]
        target = hours * 3600 / FRAME_S
        caster = rt.casters["deadair"]
        healthy, started = caster.tts, time.monotonic()

        class DeadTTS:
            async def synth(self, text, voice_id):
                raise RuntimeError("TTS provider down (soak kill switch)")
                yield  # pragma: no cover

        import psutil  # dev dependency; only the soak needs it

        proc = psutil.Process()
        mem_mb: list[float] = []
        killed = restored = False
        while caster.frames < target and all(not t.done() for t in tasks):
            sim_h = caster.frames * FRAME_S / 3600
            if len(mem_mb) <= sim_h * 4:  # a sample every simulated 15 minutes
                mem_mb.append(proc.memory_info().rss / 2**20)
            if not killed and sim_h >= kill_at:
                caster.tts, killed = DeadTTS(), True
            if killed and not restored and sim_h >= kill_at + kill_for_h:
                caster.tts, restored = healthy, True
            await asyncio.sleep(0.05)
        crashed = [t for t in tasks if t.done() and not t.cancelled()]
        rt.tasks = tasks
        await rt.stop()
        blocks = rt.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
        rt.db.close()
    logging.getLogger().removeHandler(errors)
    return {
        "hours": hours,
        "mode": "accelerated, offline providers",
        "wall_seconds": round(time.monotonic() - started),
        "blocks": blocks,
        "unhandled": errors.count + len(crashed),
        "tts_fallbacks": caster.tts_failures,
        "rss_mb": {
            "start": round(mem_mb[0]),
            "peak": round(max(mem_mb)),
            "end": round(mem_mb[-1]),
            "samples": [round(m) for m in mem_mb],
        },
        "finished": datetime.now(UTC).isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="deadair.eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--db", default=os.environ.get("DEADAIR_DB", "data/deadair.db"))
    r.add_argument("--live", action="store_true")
    r.add_argument("--out", type=Path, default=REPORTS / "eval-report.md")
    s = sub.add_parser("soak")
    s.add_argument("--hours", type=float, default=6)
    s.add_argument("--kill-at", type=float, default=1.0, help="simulated hour to kill TTS")
    s.add_argument("--kill-for", type=float, default=0.25, help="simulated hours TTS stays down")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    if args.cmd == "report":
        print(asyncio.run(report(args.db, args.live, args.out)))
    else:
        result = asyncio.run(soak(args.hours, args.kill_at, args.kill_for))
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "soak.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
