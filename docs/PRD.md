# PRD — Dead Air v1

Full requirement text lives in [`../req.md`](../req.md). This document is the product view: who, what, and how we know it works. FR/NFR IDs match the req.

## Problem

AI-generated audio is either scripted and dull, or live and untrustworthy. Dead Air shows that a live, unscripted AI show can be entertaining **and** grounded: every factual claim cites a stored headline.

## Goals

1. Be fun to listen to. The demo is a recorded episode plus a live call.
2. Keep factual claims grounded in sourced headlines.
3. Show measurable engineering: latency, fact-gate accuracy, repetition control, listener ratings.

## Non-goals (v1)

Voice cloning of real people · defamation-risk content · native mobile apps · monetization, accounts, or moderation dashboards beyond blocklists.

## Features

| Area | Summary | FRs | Priority |
|---|---|---|---|
| Newsroom feed | Poll RSS + 1 API every 5 min, normalize, dedup, 48 h window, tone tag, SQLite | FR-1.x | MVP |
| Showrunner | 10-min block plans, storylines (1 beat/block), votes at boundaries, tone rules in code, re-plan on barge-in | FR-2.x | MVP |
| Hosts | Persona YAML, 1–2 sentence chunks, cited facts only, 7-day memory, no repeats in 24 h | FR-3.x | MVP |
| Fact gate | Extract claims, require + verify citations, regenerate once, then fallback; log everything | FR-4.x | MVP |
| Audio | Streaming TTS (3+ voices), start on first chunk, ducked music bed, stingers, MP3/Opus stream, always-on recorder | FR-5.x | MVP |
| Caller line | Twilio → streaming STT → queue (max 3) → on air; barge-in < 300 ms; random caller IDs; blocklist | FR-6.x | MVP |
| Voting | 1 vote/episode, 2–3 options, DTMF or web, one vote per voter, applied at next boundary | FR-7.x | MVP |
| Rival station | Separate showrunner + personas, same feed + gate, quotes Dead Air only from transcripts, ≤ 1 jab/block | FR-8.x | MVP |
| Web | Player with rival toggle, admin (plan, storylines, gate log, queue, skip, force-close), MP3 archive | FR-9.x | MVP |

## Success metrics

| Metric | Target | NFR |
|---|---|---|
| Caller-end → first host audio | median < 1.5 s over ≥ 30 turns | NFR-1 |
| Barge-in stop time | < 300 ms in 95% of tests | NFR-2 |
| Planted false claims caught | ≥ 90% of 100 | NFR-3 |
| True claims wrongly blocked | < 10% of 100 | NFR-3 |
| Soak test | 6 h, no unhandled crash | NFR-4 |
| Catchphrase / joke reuse | none within 24 h (n-gram) | NFR-5 |
| Cost | < USD 2 / hour, logged per block | NFR-6 |
| Listener rating | 10 raters, reported | Goal 3 |

## Safety and privacy (hard rules)

- No real named private individuals. Public figures only in headline-sourced, neutral news segments (NFR-7).
- Moderation filter on all generated text.
- Phone numbers are never stored or logged. Call audio is not stored by default (FR-6.6, NFR-8).
- Serious news is never used for jokes, enforced in code (FR-2.5).

## Acceptance (v1 done when)

See req §9. In short: MVP FRs tested; NFR-1/2/3/5 met and reported; a 15-minute episode plays from the archive; a live call is queued, aired and barged-in; a vote changes the next block; the gate log shows no unsourced claims.
