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
- [ ] Full 6-hour soak (the accelerated 6 h run was stopped: the machine ran low on memory)
- [x] Crash fallback per block, hourly budget cap, per-block cost logging
- [x] Dockerfile (built and started locally), `PORT` support for Railway/Render
- [ ] Real-time 6-hour soak and a public deploy with a phone number (needs accounts and keys)

## Task 13: Demo assets — partly DONE (PR #5)
- [x] README with architecture diagram, results table, demo script
- [ ] Record a 15-minute episode with real voices, a live feud and a phone caller (needs keys)
