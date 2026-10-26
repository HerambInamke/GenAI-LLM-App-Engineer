# API Architecture

FastAPI app in `src/deadair/web/`. Station names: `deadair`, `rival`. Planned for Steps 5, 7, 8 and 11; none of this exists yet.

## Public

| Method | Path | Purpose | FR |
|---|---|---|---|
| GET | `/` | Web player | 9.1 |
| GET | `/stream/{station}.mp3` | HTTP chunked MP3 live stream | 5.5 |
| WS | `/ws/now/{station}` | Push: current segment, on-air hosts, active vote | 9.1 |
| GET | `/api/vote/{station}` | Active vote | 7.1 |
| POST | `/api/vote/{station}` | Cast `{option}`; voter = signed session cookie | 7.2 |
| GET | `/archive` | Archive page | 9.4 |
| GET | `/archive/{block_id}.mp3` | Download a recorded block | 9.4 |
| GET | `/healthz` | Liveness | NFR-4 |

## Telephony (Twilio)

| Method | Path | Purpose | FR |
|---|---|---|---|
| POST | `/twilio/voice` | Incoming call → TwiML `<Connect><Stream>`; strips `From` | 6.1, 6.6 |
| WS | `/twilio/media` | Bidirectional μ-law audio; DTMF events for votes | 6.2, 7.2 |

The `/twilio/*` routes validate the `X-Twilio-Signature` header.

## Admin (HTTP Basic, `ADMIN_PASSWORD`)

| Method | Path | Purpose | FR |
|---|---|---|---|
| GET | `/admin` | Admin page | 9.3 |
| GET | `/api/admin/{station}/plan` | Current block plan | 9.3 |
| GET | `/api/admin/{station}/storylines` | Storyline registry | 9.3 |
| GET | `/api/admin/gate-log?limit=` | Recent gate decisions | 9.3 |
| GET | `/api/admin/{station}/calls` | Call queue | 9.3 |
| POST | `/api/admin/{station}/skip` | Skip current segment | 9.3 |
| POST | `/api/admin/{station}/vote/close` | Force-close vote | 9.3 |
| WS | `/ws/admin` | Push admin updates | 9.3 |

## Internal interfaces (Python, not HTTP)

```python
class LLM(Protocol):
    async def json(self, system: str, prompt: str, schema: dict) -> dict: ...
    async def stream(self, system: str, prompt: str) -> AsyncIterator[str]: ...


class TTS(Protocol):
    async def synth(self, text: str, voice_id: str) -> AsyncIterator[bytes]: ...  # PCM 24 kHz


class STT(Protocol):
    async def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Utterance]: ...
```

Error shape for all JSON endpoints: `{"error": "<code>", "detail": "<message>"}` with a matching HTTP status.
