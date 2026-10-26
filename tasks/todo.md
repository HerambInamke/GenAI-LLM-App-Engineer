# Dead Air — Task List

Plan: [`docs/implementation-plan.md`](../docs/implementation-plan.md). Verify every task with `pytest -q` and `ruff check .`.
Everything runs offline (template hosts, rule-based gate, synthetic voice). Real providers switch on when their API keys are set.

## Task 0: Repo setup and config — DONE (PR #1)
- [x] `pyproject.toml`, Dockerfile, pre-commit (ruff, pytest)
- [x] YAML for stations, personas, feeds, budget, validated by pydantic; bad config fails clearly

## Task 1 / 1b: Feed service — DONE (PR #1, #2)
- [x] 200 sample items normalize; dedup by URL and title; 48 h window; SQLite with stable ids
- [x] Rules-based tone tagging; batched Claude fallback for unclear items (`llm_tones`)
- [x] NewsAPI poller when `NEWSAPI_KEY` is set (not tested live: no key)
- [x] Polling loop, per-source failure isolation

## Task 2: Single host reads headlines — DONE (PR #2)
- [x] `providers/llm.py` (Claude, cost meter) · `hosts/writer.py` streams 1–2 sentence chunks with `[f:id]` citations
- [x] Test: every factual sentence cites a feed id (`test_offline_news_cites_every_item`)

## Task 3: Fact gate v1 — DONE (PR #2)
- [x] Rule claim extractor + optional Claude flagging · deterministic number/entity verification · regen once, strip, or fallback · `chunks` log · moderation blocklist
- [x] 50-claim test and the 100/100 NFR-3 test pass (generated set: see caveat in README)

## Task 4: Two hosts with turn-taking — DONE (PR #2)
- [x] Two personas alternate; episode memory; catchphrase and joke 24 h guard
- [x] 20-minute text run with 0 repetition violations (`test_twenty_minute_text_run`)

## Task 6: Showrunner and storylines — DONE (PR #2)
- [x] Block planner (Claude JSON + deterministic fallback), rules enforced in code, storyline registry (1 beat/block)
- [x] 3-block simulated run test

## Task 7: Voting — core DONE (PR #2), web buttons in Task 5
- [x] Vote manager, one vote per voter, keypad digits, apply at block boundary, on-air announcement
- [x] 50 simulated votes test
- [x] Web vote buttons, one vote per browser session (PR #3)

## Checkpoint B — text show works end to end
- [x] `python -m deadair text --minutes 20`

## Task 5: Streaming TTS and audio pipeline — DONE (PR #3)
- [x] TTS (ElevenLabs streaming PCM + offline synthetic voice), generated bed with 12 dB ducking, stingers, MP3 via lameenc
- [x] HTTP MP3 stream, web player with vote buttons and rival toggle, recorder per block (MP3 + transcript)
- [x] Test: 30 simulated minutes of continuous MP3 with no silent frames; live server checked in Chrome
- [ ] ElevenLabs path not tested live (no key)

## Task 8: Caller line — DONE (PR #4)
- [x] Twilio webhook (signature checked) + bidirectional Media Stream, Deepgram streaming STT, DTMF votes
- [x] Queue (max 3), random caller ids only, blocklist drop, transcripts per call, caller audio kept out of the archive (NFR-8)
- [x] Energy-VAD barge-in cuts playback within one 50 ms frame; host re-plans on the next turn
- [x] Text call-in (`POST /api/call/{station}` + player UI) runs the same pipeline with no telephony keys
- [x] Tests: 30 scripted turns (median latency < 1.5 s, offline providers), 20/20 barge-ins < 300 ms
- [ ] Twilio + Deepgram not tested live (no keys)

## Task 9: Rival station — DONE (PR #3)
- [x] Both stations run in parallel on their own audio clocks; rival quotes `[t:chunk]` transcripts; one jab per block
- [x] Test: dual-station run with no unsourced claims

## Task 10: Evaluation harness — DONE (PR #5)
- [x] `python -m deadair.eval report [--live]` writes one report: NFR-1/2/3/4/5/6, unsourced claims, ratings
- [x] Planted-error set (100 false + 100 true), repetition checker, latency and barge-in runs
- [x] Listener rating form on `/archive` (one per browser)
- [ ] Collect 10 real listener ratings

## Task 12: Hardening and deploy — mostly DONE (PR #5)
- [x] Accelerated soak with a TTS outage: 30-minute run passed (0 unhandled, bed + station ID fallback)
- [x] Full 6-hour soak (accelerated): 0 unhandled, TTS outage handled, memory plateaus ~100 MB
- [x] Crash fallback per block, hourly budget cap, per-block cost logging
- [x] Dockerfile (built and started locally), `PORT` support for Railway/Render
- [ ] Real-time 6-hour soak and a public deploy with a phone number (needs accounts and keys)

## Task 13: Demo assets — partly DONE (PR #5)
- [x] README with architecture diagram, results table, demo script
- [ ] Record a 15-minute episode with real voices, a live feud and a phone caller (needs keys)

## Phase 6: v1 hardening (no keys needed)

### Task 14: CI — DONE
- [x] GitHub Actions: ruff check, ruff format --check, pytest on every push and PR
**Verify:** workflow green on the PR

### Task 15: 24/7 scalability of the repetition guard — DONE
- [x] Episode memory is now pruned to 7 days at every block boundary (it was never pruned)
- [x] 1 h accelerated soak: RSS 64 → 75 MB, flattening (73, 74, 75)
- [x] Repeat checks use an in-memory 24 h n-gram index per host instead of re-reading every line from SQLite
- [x] Soak report records process memory at start, peak and end
**Verify:** repeat check stays fast with 10,000 stored lines (test); 1 h accelerated soak shows flat memory

### Task 16: NFR-7 public figures only in news — DONE
- [x] With Claude: the gate also flags sentences naming real people; in non-news segments they are stripped
- [x] Offline: template lines never name people (already true), covered by a test
**Verify:** `pytest tests/test_gate.py`

### Task 17: `python -m deadair doctor` — DONE
- [x] Reports config, DB, and each provider: key present, key works, persona voice ids exist
**Verify:** offline run prints a clear table; provider checks tested with mocked HTTP

## Phase 7: operations hardening (no keys needed)

### Task 18: Full cost accounting (NFR-6, TRD T-8) — DONE
- [x] TTS characters and STT minutes are priced from `config/stations.yaml` and added to each block's `cost_usd`
- [x] The hourly budget cap therefore covers voice spend too
**Verify:** test with a priced fake TTS; block cost includes it

### Task 19: Recording retention — DONE
- [x] Recordings and call transcripts older than `retention_days` (config) are deleted hourly
- [x] `doctor` reports recording disk use
**Verify:** test with back-dated files

### Task 20: Caller-input hardening — DONE
- [x] Text call lines capped at 300 chars; per-client rate limits on call-in, votes and ratings
- [x] Caller words reach the host prompt as quoted, untrusted text with an instruction not to follow them
**Verify:** tests for 413/422 and 429 responses and the prompt framing

### Task 21: Structured logs (NFR-9, TRD T-10) — DONE
- [x] `DEADAIR_LOG_JSON=1` switches logging to one JSON object per line
**Verify:** test parses emitted lines as JSON

## Phase 8: episodes and caller hold (no keys needed)

### Task 22: Caller hold decision (FR-6.3) — DONE
- [x] Callers are held, not put on air, when the next segment reads a serious news item; they go on after it
- [x] Hold is logged as a call status
**Verify:** test with a serious item ahead of a waiting caller

### Task 23: Render a full episode (Step 13, acceptance criterion 3) — DONE
- [x] `python -m deadair record --minutes 15` renders one MP3 + transcript per station, faster than real time
- [x] The episode includes a feud jab, a scripted caller and a vote result; it appears in `/archive`
**Verify:** test renders a short episode and checks the file and transcript; manual 15-minute render
- [x] Also fixed: offline blocks were ~1.5 min (20 s songs); `song_seconds` (150) and `vote_blocks` (6) now in config
- [x] Also fixed: typed call-in lines are spoken on air in `caller_voice_id`, after moderation, the gate and NFR-7
