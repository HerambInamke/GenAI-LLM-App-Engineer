Dead Air: Requirements
1. Project summary

Dead Air is a 24/7 internet radio station run entirely by AI. Two AI hosts read real headlines, argue about them, play generated music, and take live calls. A rival station, run by a separate AI with its own personality, broadcasts on the next "frequency" and feuds with them on air. Storylines persist across days in a memory store. Listeners vote on plot outcomes by phone, and votes change what the hosts do next.

Primary goals:

Be fun to listen to. The output is audio, and the demo is a recorded episode plus a live call.
Keep factual claims grounded in sourced headlines.
Show measurable engineering: latency, fact-gate accuracy, repetition control, and listener ratings.

Non-goals (v1):

Real voice cloning of real people.
Real defamation-risk content. Rival station and hosts are fictional.
Mobile native apps. A web player is enough.
Monetization, accounts, or moderation dashboards beyond basic blocklists.
2. Glossary
Feed: the list of normalized news items (headline, source, timestamp, category, tone tag).
Showrunner: the agent that plans programming blocks and tracks storylines.
Host: a persona agent with a voice, a personality, and per-episode memory.
Segment: one unit of programming (news read, banter, song intro, feud beat, caller, ad break).
Block: a planned sequence of about 10 minutes of segments.
Storyline: a running thread (for example, a feud or a recurring joke) that persists across episodes.
Fact gate: the component that checks factual claims in generated text against the feed.
Barge-in: a caller or listener interrupting playback; playback stops and the host re-plans.
Station: a broadcast identity with its own hosts, voices, and music style. Dead Air and the rival are two stations.
3. Functional requirements
3.1 Newsroom feed
FR-1.1 Poll configured sources (RSS feeds and one public news API) every 5 minutes.
FR-1.2 Normalize items to a schema: id, title, summary, source, published_at, category, tone where tone is one of light, neutral, serious.
FR-1.3 Deduplicate items by normalized title and URL.
FR-1.4 Drop items older than 48 hours from the active pool.
FR-1.5 Tag tone using a rules-based pass first, with an LLM fallback for unclear items.
FR-1.6 Store feed items in SQLite so every later claim can cite a stored id.
3.2 Showrunner
FR-2.1 Generate a block plan of about 10 minutes: an ordered list of segments with type, assigned host, and source item IDs where relevant.
FR-2.2 Maintain a storyline registry: name, status (active, resolved, dormant), participants, last-advanced episode, and a summary.
FR-2.3 Advance at most one beat per storyline per block, so feuds don't speed up unnaturally.
FR-2.4 Apply listener votes at the next block boundary, never mid-segment.
FR-2.5 Enforce tone rules: serious items may not be used for jokes. This is a hard constraint, checked in code.
FR-2.6 Re-plan immediately after a barge-in, keeping the segment's remaining context.
3.3 Host agents
FR-3.1 Each station has two or more hosts, each defined by a persona file: name, voice ID, speaking style, catchphrases (max 3), and a list of hard "never do" rules.
FR-3.2 Hosts write lines in chunks of 1 to 2 sentences so TTS can start before the full segment is generated.
FR-3.3 Hosts can only use facts that appear in a segment's cited feed items or in the storyline summary.
FR-3.4 Hosts keep an episode memory: last 7 days of jokes, phrases, and callers, stored in a vector store and retrieved by similarity.
FR-3.5 Hosts avoid reusing any catchphrase or joke within 24 hours (see NFR-5).
3.4 Fact gate
FR-4.1 Every generated chunk is parsed for factual claims. A claim is any statement about a real-world event, number, person's action, or date.
FR-4.2 Each claim must cite a feed item id or a storyline fact ID. Claims without a citation are removed before TTS.
FR-4.3 Citations are verified: the cited item must exist and must contain the key entity or number in the claim (string or fuzzy match).
FR-4.4 Rejected chunks are regenerated once. If they fail again, the segment is replaced with a safe fallback (music bed or a neutral weather line).
FR-4.5 Every gate decision is logged (chunk ID, claims, citations, result) for evaluation.
3.5 Voice and audio
FR-5.1 TTS: one streaming provider with at least 3 distinct voices (two hosts plus the rival station).
FR-5.2 Audio playback starts after the first chunk is synthesized, not after the whole segment.
FR-5.3 A music bed (royalty-free or generated, from a local library) plays under host speech with ducking (volume lowered by about 12 dB during speech).
FR-5.4 Segment transitions use short stingers from a local sound library.
FR-5.5 Audio is streamed to browsers over WebSocket or HTTP chunked audio (Opus or MP3).
FR-5.6 The station keeps running when no listeners are connected, and a recorder saves each block to disk.
3.6 Caller line
FR-6.1 A phone number (Twilio or similar) connects to a call handler.
FR-6.2 Caller audio is transcribed with streaming STT and passed to the showrunner.
FR-6.3 The showrunner decides whether to put the caller on air (queue, reject, or hold for later). Default: queue, max 3 callers waiting.
FR-6.4 When a caller is on air, their audio is mixed in and the host responds to their transcribed speech.
FR-6.5 A caller can barge in; host playback stops within 300 ms and the host re-plans (FR-2.6).
FR-6.6 Callers are identified only by a per-call random ID. Phone numbers are never stored in logs or memory.
FR-6.7 A caller can be dropped for abuse by a blocklist check on the transcript.
3.7 Listener voting
FR-7.1 Each episode has one open vote with 2 to 3 options, set by the showrunner (for example, "Does Host A apologize or double down?").
FR-7.2 Votes are cast by phone keypad (DTMF) or by a web button. One vote per call ID or browser session per vote.
FR-7.3 The winning option is applied at the next block boundary (FR-2.4) and announced on air.
FR-7.4 Votes and outcomes are stored for the evaluation report.
3.8 Rival station
FR-8.1 The rival station runs as a separate showrunner with its own hosts, voices, and persona files.
FR-8.2 The rival reads the same feed but may choose different items. It may reference Dead Air's on-air claims only by quoting stored transcripts.
FR-8.3 Feud beats are scheduled by the showrunner so the two stations trade at most one on-air jab per block each.
FR-8.4 The rival station uses the same fact gate. It may be rude, but it may not invent facts.
3.9 Web player and dashboard
FR-9.1 A single web page plays the live stream of Dead Air, shows the current segment name, the on-air hosts, and the active vote.
FR-9.2 The page has a "listen to rival" toggle that switches to the rival stream.
FR-9.3 A simple admin page (password-protected) shows: block plan, storyline registry, fact gate log, and call queue. It can skip a segment or force-close a vote.
FR-9.4 Recorded episodes are downloadable as MP3 from an archive page.
4. Non-functional requirements
NFR-1 Latency: time from a caller finishing a sentence to the first host audio on air is under 1.5 seconds at the median, measured over at least 30 caller turns.
NFR-2 Barge-in: playback stops within 300 ms of detected caller speech in 95% of tests.
NFR-3 Fact gate: on a planted-error test set of 100 false claims, at least 90% are caught before TTS. False positive rate on 100 true claims is below 10%.
NFR-4 Uptime: the station runs for 6 continuous hours in a soak test with no unhandled crashes. Feed or TTS failures degrade gracefully (music bed plus a station ID).
NFR-5 Repetition: a host does not reuse a catchphrase or joke within 24 hours. Measured with n-gram overlap over a 24-hour log.
NFR-6 Cost: a 1-hour episode costs under a set budget (set by the user, for example USD 2). Cost is logged per block.
NFR-7 Safety: no real named private individuals in generated content. Public figures may appear only in headline-sourced, neutral news segments. Hate, slurs, and explicit content are blocked by a moderation filter on all generated text.
NFR-8 Privacy: call audio is not stored by default. Transcripts are stored with caller IDs only, and phone numbers are never logged.
NFR-9 Observability: every block logs its plan, every chunk logs its gate decision, and every call logs its lifecycle events.
NFR-10 Configuration: stations, personas, feed sources, and budgets live in YAML files, not code.
5. Architecture overview

Components:

Feed service: pollers, normalizer, dedup, SQLite store.
Showrunner: planner (LLM with JSON output), storyline registry, vote manager, block scheduler.
Host runtime: persona loader, line writer, episode memory (vector store), chunker.
Fact gate: claim extractor, citation checker, regeneration policy, decision log.
Audio pipeline: TTS client, music bed mixer, stinger player, ducking, encoder (Opus/MP3), stream server.
Call handler: telephony webhook, streaming STT, caller queue, barge-in controller.
Web app: public player, vote buttons, archive, admin page.
Recorder: writes each block's audio and transcript to disk.

Data flow (happy path): feed → showrunner plans block → host writes chunk → fact gate checks chunk → TTS → mixer → stream → browser.

Caller path: phone → STT → showrunner decides → host reply chunk → gate → TTS → mixer → stream (with barge-in cutting playback).

6. Data model (minimum)
feed_items(id, title, summary, source, published_at, category, tone, url, fetched_at)
blocks(id, station, planned_at, plan_json, cost_usd)
segments(id, block_id, type, host, status, started_at, ended_at)
chunks(id, segment_id, host, text, gate_result, claims_json, created_at)
storylines(id, station, name, status, participants_json, summary, last_episode)
votes(id, station, question, options_json, opened_at, closed_at, result)
vote_casts(vote_id, voter_id, option, cast_at) where voter_id is a random ID, never a phone number
calls(id, station, started_at, ended_at, status, transcript_path)
memory_items in the vector store: (id, station, host, text, created_at, tags)
7. Tech stack
Language: Python 3.11+
Web: FastAPI, WebSocket endpoints for the stream and admin updates
DB: SQLite (v1); Postgres is optional
Vector memory: sqlite-vec or Chroma (local)
LLM: one provider SDK (Anthropic or OpenAI) with JSON-schema outputs for planning and gate checks
TTS: one streaming provider with at least 3 voices
STT: streaming provider (Deepgram or Whisper streaming)
Telephony: Twilio Voice with Media Streams, or a comparable provider
Audio: ffmpeg for encoding and mixing; pydub or numpy for ducking
Frontend: plain HTML, CSS, and vanilla JS (or a small React app if preferred)
Tests: pytest; fixtures include a planted-error claim set
Deploy: Docker; a single VM or Railway/Render for the always-on stream
8. Build plan (step by step)

Each step ends with a runnable demo and a test.

Step 0: Repo setup (Day 1)

Create the repo, Python env, Docker file, pre-commit (ruff, pytest).
Add config loader and YAML schema for stations, personas, feeds.
Test: config loads and validates.

Step 1: Feed service (Week 1)

Implement RSS and API pollers, normalizer, dedup, SQLite store.
Tone tagger (rules first, LLM fallback).
Test: 200 sample items normalize correctly; duplicates removed.

Step 2: Single host reads headlines (Week 1)

One host persona. Line writer reads 5 headlines in short chunks.
No TTS yet; print text to the console.
Test: every output sentence cites a feed ID (checked by a simple script).

Step 3: Fact gate v1 (Week 1)

Claim extractor (LLM with JSON output) and citation checker.
Regeneration once, then fallback.
Test: 50 hand-written claims (true and false) with expected results.

Step 4: Two hosts with turn-taking (Week 2)

Second persona. Turn-taking logic and chunk scheduling.
Episode memory in the vector store (store and retrieve per host).
Test: 20-minute text run with no catchphrase repeated within 24 hours.

Step 5: Streaming TTS and audio pipeline (Week 3)

TTS client with 3 voices, chunked synthesis, playback queue.
Music bed with ducking, stingers, Opus/MP3 encoder.
Stream server (HTTP chunked or WebSocket) and a minimal web player.
Test: the stream plays in a browser for 30 minutes without dropouts.

Step 6: Showrunner and storylines (Week 4)

Block planner (JSON output, validated against a schema).
Storyline registry with one-beat-per-block rule.
Tone rule enforcement (serious items cannot be joked about).
Test: a 3-block simulated run respects tone rules and advances storylines correctly.

Step 7: Voting (Week 4)

Vote manager, web vote buttons, block-boundary application.
Announce result on air.
Test: 50 simulated votes produce the expected winning option and apply at the next boundary.

Step 8: Caller line (Week 5)

Telephony webhook, streaming STT, caller queue (max 3).
Barge-in controller (stop playback within 300 ms).
Blocklist check on transcripts. Call IDs are random; no phone numbers stored.
Test: 30 scripted call turns; median latency under 1.5 s; barge-in works in 95%.

Step 9: Rival station (Week 5)

Second showrunner with separate personas and voices.
Feud scheduling (max one jab per station per block).
Test: a 30-minute dual-station run with no unsourced claims from either side.

Step 10: Evaluation harness (Week 5)

Planted-error test set (100 false, 100 true claims).
Repetition checker over a 24-hour log.
Latency and barge-in measurement scripts.
Listener rating form (10 raters).
Test: harness produces a single report file with all NFR numbers.

Step 11: Admin page, archive, and recorder (Week 6)

Admin page with block plan, gate log, call queue, skip and force-close.
Recorder writes MP3 per block; archive page lists episodes.
Test: a recorded episode plays back from the archive.

Step 12: Hardening and deploy (Week 6)

Soak test (6 hours), graceful degradation paths, budget logging.
Deploy to a VM or Railway with a public URL and a phone number.
Test: soak test passes; kill TTS and confirm the station falls back to music and a station ID.

Step 13: Demo assets (Week 6)

Record a 15-minute episode with a live feud and a caller.
Write README with architecture diagram, results table, and demo script.
9. Acceptance criteria (v1 done when)
All FR items marked MVP are implemented and tested.
NFR-1, NFR-2, NFR-3, NFR-5 are met and reported in the README.
A 15-minute episode can be generated and played back from the archive.
A live call can be placed, queued, put on air, and interrupted by barge-in.
A listener vote changes the next block's storyline and is announced.
No unsourced factual claims appear in the recorded episode (checked by the gate log).
10. Risks and mitigations
Risk	Mitigation
TTS and LLM latency makes calls feel slow	Stream chunks, start TTS early, keep chunks short; measure and report
Hallucinated facts	Fact gate with citations, regeneration, fallback content
Repetitive jokes	Episode memory, n-gram check, persona "never do" rules
Offensive caller content	Blocklist check, showrunner can reject callers, moderation filter
Cost overrun	Per-block budget logging, budget cap, shorter chunks
Copyrighted music	Use royalty-free or generated tracks from a local library only
Telephony setup takes too long	Build the stream first; add phone last (Step 8)
11. Open decisions (answer before Step 1)
LLM provider: Anthropic or OpenAI?
TTS and STT provider: which one, and what budget per hour?
Telephony: Twilio, or defer calls and do web-only calls first?
News sources: which RSS feeds and whether a news API key is available?
Music: royalty-free library, or generated tracks?
Deploy target: local demo only, or a public always-on URL?