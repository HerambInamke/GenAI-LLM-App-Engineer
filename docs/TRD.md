# TRD — Technical Requirements

How the [PRD](PRD.md) is met technically. Component detail is in [architecture.md](architecture.md).

## Stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | `asyncio` throughout |
| Web | FastAPI + WebSockets | Stream, votes, admin updates |
| DB | SQLite (WAL mode) | Postgres optional later |
| Vector memory | sqlite-vec | One file, no extra service |
| LLM | Anthropic SDK, structured JSON outputs | Larger model for host lines, small model for gate and tone |
| TTS | ElevenLabs streaming | ≥ 3 voices, set per persona |
| STT | Deepgram streaming | Endpointing drives barge-in |
| Telephony | Twilio Voice Media Streams | μ-law 8 kHz in/out |
| Audio | ffmpeg (encode/mix), numpy (ducking) | MP3 for browsers, Opus optional |
| Frontend | Plain HTML/CSS/JS | No build step |
| Config | YAML + pydantic validation | NFR-10 |
| Tests | pytest, pytest-asyncio | Planted-error fixtures |
| Lint | ruff via pre-commit | |
| Deploy | Docker, Railway or a single VM | |

## Technical requirements

| ID | Requirement | Verified by |
|---|---|---|
| T-1 | All external providers (LLM, TTS, STT, telephony, news) sit behind a small interface with a fake for tests | Unit tests run with no network or keys |
| T-2 | Config is YAML validated by pydantic at startup; bad config fails fast with a clear error | `tests/test_config.py` |
| T-3 | Every DB write that a later claim may cite uses a stable id (`sha1` of normalized URL or title) | `tests/test_feed.py` |
| T-4 | Host output is a stream of chunks of 1–2 sentences, each with a `citations` list | Step 2 script |
| T-5 | Gate verification is deterministic code (entity / number match); only claim *extraction* uses the LLM | Step 3 tests |
| T-6 | The audio loop never blocks on the LLM: when the next chunk is late, the music bed fills | Step 5 soak |
| T-7 | Barge-in cancels the current TTS task and flushes the mixer queue | Step 8 timing test |
| T-8 | Cost of each LLM/TTS/STT call is accumulated per block and stored in `blocks.cost_usd` | Step 12 |
| T-9 | Phone numbers never leave the Twilio webhook handler; callers get `uuid4` ids | Grep test + log scan |
| T-10 | Every block, chunk and call writes structured JSON logs | NFR-9 |

## Latency budget (caller turn, NFR-1)

| Stage | Budget |
|---|---|
| STT endpoint detection | 300 ms |
| Showrunner decide + host first chunk (LLM first tokens) | 600 ms |
| Fact gate on first chunk | 200 ms |
| TTS first audio byte | 300 ms |
| Mixer + network | 100 ms |
| **Total** | **1.5 s** |

If the gate is too slow, the first chunk of a caller reply is restricted to no-claim content (acknowledgement), and claims start from chunk 2.

## Environment variables

See [`../.env.example`](../.env.example). Keys: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY`, `TWILIO_*`, `NEWSAPI_KEY` (optional), `ADMIN_PASSWORD`.
