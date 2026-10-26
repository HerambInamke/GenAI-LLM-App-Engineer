# Idea Plan

From raw idea to a buildable v1. Source of truth for requirements: [`../req.md`](../req.md).

## Users

| User | Wants |
|---|---|
| Listener | Something fun to have on; to call in; to vote on the plot |
| Operator (you) | Keep it running cheaply, skip a bad segment, see why a line was cut |
| Evaluator / reviewer | Hard numbers: latency, gate accuracy, repetition, ratings |

## Riskiest assumptions, tested first

1. **The fact gate can be strict without killing the comedy.** Tested in Step 3 with a 50-claim set, then the 200-claim set in Step 10.
2. **Chunked TTS keeps the caller round trip under 1.5 s.** Measured in Step 8. If it fails, shorten chunks or use a faster model for replies.
3. **Two LLM hosts can banter without repeating.** Tested in Step 4 with a 20-minute text run.

## Scope ladder

| Rung | Delivers | Steps |
|---|---|---|
| 1. Newsroom | Feed polled, normalized, stored, tone-tagged | 0–1 |
| 2. Talk radio (text) | Hosts write cited lines; the gate cuts unsourced ones | 2–4 |
| 3. Radio | Real audio stream in a browser with music and stingers | 5 |
| 4. Show | Showrunner, storylines, votes | 6–7 |
| 5. Live | Phone calls with barge-in | 8 |
| 6. Rivalry | Second station and feud beats | 9 |
| 7. Proof | Eval harness, admin, archive, deploy, demo | 10–13 |

Each rung is demoable on its own. If time runs out, ship the highest finished rung.

## Default answers to the open decisions (req §11)

These are defaults so work can start. Change them in `config/*.yaml` and `.env`.

| Decision | Default | Why |
|---|---|---|
| LLM provider | Anthropic (Claude) | JSON-schema outputs and fast small models for the gate |
| TTS | ElevenLabs streaming | Low first-byte latency, many distinct voices |
| STT | Deepgram streaming | Endpointing built in, good for barge-in |
| Telephony | Twilio Media Streams, added last (Step 8) | Web player first, per req §10 |
| News | Public RSS (BBC, NPR, Guardian) + optional NewsAPI key | Works with no key |
| Music | Local royalty-free / generated beds in `assets/music/` | No copyright risk |
| Deploy | Local Docker first, Railway for the public URL | Cheapest path to a demo |
| Budget | USD 2.00 per hour | From the req example |
