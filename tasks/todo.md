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
- [ ] Web vote buttons (with Task 5)

## Checkpoint B — text show works end to end
- [x] `python -m deadair text --minutes 20`

## Task 5: Streaming TTS and audio pipeline
- [ ] TTS (ElevenLabs + offline synthetic voice), music bed with ~12 dB ducking, stingers, MP3 encoder
- [ ] Stream server + minimal web player with vote buttons and rival toggle; recorder per block
- [ ] Test: stream produces continuous MP3 for a simulated 30 minutes

## Task 8: Caller line
- [ ] Twilio webhook + media stream, STT, queue (max 3), barge-in < 300 ms, blocklist, random caller ids
- [ ] Test: 30 scripted call turns, latency and barge-in measured

## Task 9: Rival station
- [ ] Second station running in parallel, transcript quoting, feud cap

## Task 10: Evaluation harness
- [ ] One report with NFR-1/2/3/5/6 numbers

## Task 11: Admin page and archive
## Task 12: Hardening and deploy
## Task 13: Demo assets
