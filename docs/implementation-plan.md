# Implementation Plan: Dead Air v1

## Overview

Build the AI radio station in 14 steps (req §8). Each step ends with a runnable demo and a test, and leaves the system working. Tasks are tracked in [`../tasks/todo.md`](../tasks/todo.md).

## Architecture decisions

- **Single asyncio process** for both stations. Simple, enough for v1 load; split later if needed.
- **Providers behind protocols, with fakes** so the whole pipeline is tested offline (TRD T-1).
- **Gate verification is deterministic code.** The LLM only extracts claims, which makes NFR-3 measurable and repeatable.
- **SQLite + sqlite-vec.** One file and no services, until Postgres is actually needed.
- **Inline citations** (`[f:<id>]`, `[s:<id>]`) in host text. The gate parses them and strips them before TTS.
- **Defaults for the open decisions** are in [ideaplan.md](ideaplan.md#default-answers-to-the-open-decisions-req-11).

## Dependency graph

```
config ─▶ feed ─▶ host writer ─▶ fact gate ─▶ two hosts + memory ─▶ audio ─▶ showrunner ─▶ votes
                                                                       │            └─▶ rival
                                                                       └─▶ calls (barge-in)
                                                          all ─▶ eval ─▶ admin/archive ─▶ deploy ─▶ demo
```

## Phases

### Phase 1: Foundation (Steps 0–1) — **in progress**
- [x] T0 Repo, env, Dockerfile, pre-commit, config loader + YAML schema
- [x] T1 Feed: normalizer, dedup, tone rules, SQLite store, RSS poller
- [ ] T1b Tone LLM fallback, NewsAPI poller, 5-minute polling service

**Checkpoint:** `pytest` green; `python -m deadair.feed` fills the DB from live RSS.

### Phase 2: Talk radio in text (Steps 2–4)
- [ ] T2 Anthropic provider + fake; one host reads 5 headlines in cited chunks
- [ ] T3 Claim extractor + citation verifier + regen/fallback + gate log (50-claim test)
- [ ] T4 Second host, turn-taking, sqlite-vec memory, repetition check (20-min run)

**Checkpoint:** a 20-minute text show with zero uncited claims and no 24 h repeats.

### Phase 3: Radio (Step 5)
- [ ] T5 TTS client (3 voices), mixer with ducking, stingers, MP3 encoder, stream, minimal player

**Checkpoint:** the stream plays in a browser for 30 minutes without dropouts.

### Phase 4: Show (Steps 6–7)
- [ ] T6 Block planner (JSON schema), storyline registry, tone + beat rules
- [ ] T7 Vote manager, web buttons, boundary application, on-air announcement

**Checkpoint:** 3-block simulated run passes rule checks; 50 simulated votes apply correctly.

### Phase 5: Live and rivalry (Steps 8–9)
- [ ] T8 Twilio webhook, STT, queue, barge-in, blocklist, privacy
- [ ] T9 Rival showrunner, personas, feud scheduler

**Checkpoint:** 30 call turns, median < 1.5 s, barge-in OK in 95%; 30-minute dual run with no unsourced claims.

### Phase 6: Proof and ship (Steps 10–13)
- [ ] T10 Eval harness (200 planted claims, repetition, latency, ratings) → one report
- [ ] T11 Admin page, recorder, archive
- [ ] T12 6-hour soak, degradation paths, budget logging, deploy
- [ ] T13 15-minute demo episode, README results table

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Caller latency > 1.5 s | High | Short chunks, small model for replies, ack-first chunk without claims |
| Gate too strict, show goes flat | Med | Banter without claims needs no citation; tune fuzzy threshold on the true-claim set |
| Gate too loose | High | Deterministic entity/number match; planted-error set in CI |
| Cost overrun | Med | Per-block cost log, hard cap → music-only mode |
| Twilio setup delays | Med | Stream first, phone last (Step 8) |
| RSS sources change format | Low | `feedparser` tolerates most; per-source failure isolation |

## Open questions

- Confirm or change the provider defaults (LLM, TTS, STT, telephony).
- Budget per hour: USD 2 assumed.
- Public URL needed for the demo, or local only?
