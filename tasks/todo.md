# Dead Air — Task List

Plan: [`docs/implementation-plan.md`](../docs/implementation-plan.md). Verify every task with `pytest -q` and `ruff check .`.

## Task 0: Repo setup and config — DONE
**Acceptance:**
- [x] `pyproject.toml`, Dockerfile, pre-commit (ruff, pytest)
- [x] `config/` YAML for stations, personas, feeds, budget, validated by pydantic
- [x] Invalid config (e.g. 4 catchphrases, unknown persona) fails with a clear error
**Verify:** `pytest tests/test_config.py`
**Files:** `pyproject.toml`, `Dockerfile`, `.pre-commit-config.yaml`, `src/deadair/config.py`, `config/*`

## Task 1: Feed service core — DONE
**Acceptance:**
- [x] 200 sample items normalize to the FR-1.2 schema
- [x] Duplicates by URL or normalized title removed (FR-1.3)
- [x] Items older than 48 h excluded from the active pool (FR-1.4)
- [x] Rules-based tone tagging (FR-1.5 part 1)
- [x] Stored in SQLite with stable ids (FR-1.6)
**Verify:** `pytest tests/test_feed.py`
**Files:** `src/deadair/feed/*`, `tests/test_feed.py`

## Task 1b: Feed service complete
**Acceptance:**
- [ ] LLM fallback for items the rules can't tag (fake LLM in tests)
- [x] NewsAPI poller when `NEWSAPI_KEY` is set (untested against the live API; no key yet)
- [x] Background loop polls every `poll_minutes`; one bad source doesn't stop the others
**Verify:** `pytest tests/test_feed.py`; `python -m deadair.feed --once`
**Depends on:** 1

## Checkpoint A
- [ ] Tests and lint green · live RSS fills `data/deadair.db` · review with human

## Task 2: Single host reads headlines
- [ ] `providers/llm.py` Anthropic + fake · `hosts/persona.py` · `hosts/writer.py` streams 1–2 sentence chunks with `[f:id]` citations
- [ ] Script asserts every factual sentence cites a feed id
**Depends on:** 1b

## Task 3: Fact gate v1
- [ ] Claim extractor (LLM JSON) · deterministic verifier (entity/number fuzzy match) · regen once then fallback · `chunks` log
- [ ] 50 hand-written claims fixture, expected results pass
**Depends on:** 2

## Task 4: Two hosts with turn-taking
- [ ] Second persona, turn scheduler, sqlite-vec memory, catchphrase/joke 24 h guard
- [ ] 20-minute text run with no repeats
**Depends on:** 3

## Checkpoint B — text show works end to end

## Task 5: Streaming TTS and audio pipeline
## Task 6: Showrunner and storylines
## Task 7: Voting
## Checkpoint C
## Task 8: Caller line
## Task 9: Rival station
## Checkpoint D
## Task 10: Evaluation harness
## Task 11: Admin, archive, recorder
## Task 12: Hardening and deploy
## Task 13: Demo assets

(Tasks 5–13 get full acceptance criteria when Checkpoint B is reached; see req §8 for their tests.)
