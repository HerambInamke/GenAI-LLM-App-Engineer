# Architecture

## Components

```
                ┌──────────────┐
  RSS / API ──▶ │ Feed service │──▶ SQLite (feed_items)
                └──────┬───────┘
                       ▼
 votes ──▶ ┌──────────────────┐  plan   ┌─────────────┐ chunk ┌───────────┐
 calls ──▶ │   Showrunner     │───────▶ │ Host runtime│──────▶│ Fact gate │
           │ planner·storyline│         │ persona·mem │◀──────│ claims·cit│
           │ votes·scheduler  │◀─┐      └─────────────┘ regen └─────┬─────┘
           └──────────────────┘  │                                   │ pass
                 ▲   barge-in    │                                   ▼
 phone ─▶ Call handler ─ STT ────┘     ┌──────────────────────────────────┐
           (queue, blocklist)          │ Audio pipeline                   │
                 │ caller audio ──────▶│ TTS · bed+ducking · stingers ·   │
                                       │ encoder · stream server          │
                                       └──────┬─────────────┬─────────────┘
                                              ▼             ▼
                                        Web player     Recorder (MP3 per block)
```

Two stations (`deadair`, `rival`) are two instances of Showrunner + Host runtime + Audio pipeline. They share the feed service, the fact gate and the DB.

## Module map (`src/deadair/`)

| Package | Responsibility | Req |
|---|---|---|
| `config.py` | Load and validate YAML (stations, personas, feeds, budget) | NFR-10 |
| `feed/` | `models` (FeedItem), `normalize`, `tone`, `store` (SQLite), `pollers`, `service` | FR-1 |
| `showrunner/` | `planner` (LLM → BlockPlan JSON), `storylines`, `votes`, `rules` (tone, feud caps) | FR-2, 7, 8.3 |
| `hosts/` | `persona`, `writer` (streams chunks), `memory` (sqlite-vec), `repetition` | FR-3 |
| `gate/` | `extract` (LLM claims), `verify` (deterministic), `policy` (regen/fallback), `log` | FR-4 |
| `audio/` | `tts`, `mixer` (ducking), `stingers`, `encoder`, `stream` | FR-5 |
| `calls/` | `twilio_ws`, `stt`, `queue`, `bargein`, `blocklist` | FR-6 |
| `web/` | FastAPI app, player, admin, archive | FR-9 |
| `providers/` | Thin interfaces + real and fake implementations of LLM, TTS, STT | T-1 |
| `eval/` | Planted claims, repetition, latency, report | Step 10 |

## Key design rules

1. **Code enforces, LLM proposes.** The planner proposes a block; `showrunner/rules.py` rejects tone or feud violations. The extractor proposes claims; `gate/verify.py` decides.
2. **One clock per station.** The audio loop owns time. It pulls the next gated chunk; if none is ready, it plays the bed. Generation runs ahead in a bounded queue.
3. **Everything citable has an id.** Feed items, storyline facts and transcripts are rows; claims reference rows.
4. **Fakes for every provider.** The whole station runs offline in tests with deterministic fakes.
5. **Privacy at the edge.** Phone numbers are dropped in the webhook handler and never reach the rest of the system.

## Concurrency model

`asyncio`, one process. Per station: a planner task, a writer task feeding a bounded `asyncio.Queue` of gated chunks, and an audio task that consumes it. Pollers run as one shared background task. Barge-in is an `asyncio.Event` that the audio task checks between frames (20 ms), which bounds stop latency well under 300 ms.

## Failure handling (NFR-4)

| Failure | Behavior |
|---|---|
| Feed source down | Skip source, keep the rest, log |
| LLM error / timeout | Fallback segment (music bed + station ID) |
| Gate fails twice | Fallback segment (FR-4.4) |
| TTS down | Music bed + pre-rendered station ID from `assets/` |
| Budget exceeded | Switch to music-only blocks until the next hour |
