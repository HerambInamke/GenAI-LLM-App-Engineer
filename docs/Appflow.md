# App Flow

## 1. Happy path (one block)

```
poll feed (every 5 min) → feed_items
        │
showrunner.plan_block(station)
  ├─ pick items (respect tone rules)
  ├─ advance ≤1 beat per storyline
  ├─ apply closed vote result (block boundary only)
  └─ BlockPlan [segments…]  → blocks row
        │
for each segment:
  host.write(segment) ──streams──▶ chunk (1–2 sentences + citations)
        │
  gate.check(chunk)
    ├─ pass        → TTS
    ├─ fail        → regenerate once → pass → TTS
    └─ fail twice  → fallback (bed + neutral line)
        │
  TTS → mixer (bed ducked −12 dB, stinger between segments) → encoder → stream → browsers
                                                                 └──→ recorder (MP3/block)
```

## 2. Caller path

```
phone → /twilio/voice (drop number, assign call_id) → /twilio/media
   → STT (streaming) → blocklist check ─fail→ drop
   → showrunner.decide(call) → queue (max 3) | reject | hold
   → on air: caller audio mixed in; host replies to transcript
       → chunk → gate → TTS → mixer
   caller speaks while host talks → barge-in event
       → stop playback (< 300 ms) → showrunner re-plans with remaining context
```

## 3. Vote flow

```
showrunner opens vote (2–3 options) at block start
   → web button  (session id)  ┐
   → phone DTMF  (call id)     ┴→ vote_casts (one per voter)
block boundary → close → tally → result → applied to next plan → announced on air
```

## 4. Feud flow

```
rival showrunner reads the same feed
   → may quote Dead Air only from stored transcripts (chunks table)
   → feud scheduler: ≤ 1 jab per station per block
   → same fact gate
```

## 5. Degraded mode

```
LLM / TTS / feed failure or budget hit → music bed + pre-rendered station ID
   → retry with backoff each block → resume normal programming
```

## Screens

| Screen | Shows | Actions |
|---|---|---|
| Player `/` | Live audio, segment name, on-air hosts, active vote | Play/pause, vote, switch to rival |
| Admin `/admin` | Block plan, storylines, gate log, call queue | Skip segment, force-close vote |
| Archive `/archive` | Recorded blocks by date | Download MP3 |
