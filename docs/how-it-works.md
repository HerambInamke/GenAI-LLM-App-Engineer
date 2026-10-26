# How It Works

A plain-language walkthrough of one minute of Dead Air.

**1. The newsroom.** Every 5 minutes the feed service pulls RSS feeds and a news API. Each headline becomes a `FeedItem` with an id, cleaned title and summary, and a tone: *light*, *neutral* or *serious*. Simple keyword rules decide most tones ("dies", "war", "earthquake" → serious; "cat", "festival", "record-breaking pizza" → light). Only unclear items go to the LLM. Duplicates (same URL or same normalized title) are dropped, and anything older than 48 hours leaves the pool.

**2. The showrunner.** Every ~10 minutes it plans a block: news read → banter → song intro → feud beat → caller → … Each segment names a host and the feed item ids it may use. Code checks the plan: a serious item in a comedy segment is rejected, and a storyline may move only one beat.

**3. The hosts.** Each host is a YAML persona: name, voice, style, up to 3 catchphrases, and "never do" rules. The host writes one or two sentences at a time and tags each fact with the id it came from, like `[f:3a9c…]`. Before writing, it looks up its own recent jokes in memory so it doesn't repeat them.

**4. The fact gate.** Each chunk is split into claims. Every claim must cite a feed item or storyline fact, and the cited item must actually contain the claim's key name or number. A claim that fails is removed. If the chunk can't be fixed, the host gets one retry; after that the segment falls back to music. Every decision is logged.

**5. The sound.** Approved chunks go to streaming TTS immediately, so the first sentence plays while the second is still being written. Music runs underneath and dips about 12 dB while someone talks. Short stingers mark segment changes. The mix is encoded to MP3 and streamed to every listener, and the recorder saves each block even when nobody is listening.

**6. Callers.** You call the number. Your phone number is discarded at once; you become `call_7f2e…`. Your speech is transcribed live. If you're not on the blocklist, you join a queue of up to 3. On air, the host answers you. Talk over the host and they stop within 300 ms and adjust.

**7. Votes and the rival.** Each episode has one question ("Does Max apologize or double down?"). You vote by keypad or web button; the result applies at the next block and is announced. Meanwhile the rival station runs the same machinery with ruder hosts. It can quote Dead Air only from real transcripts, and it gets at most one jab per block.
