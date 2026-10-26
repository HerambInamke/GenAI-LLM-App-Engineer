# Dead Air

A 24/7 internet radio station run entirely by AI. Two hosts read real headlines, argue about them, play music and take live calls. A rival AI station across the dial feuds with them on air. Listeners vote on what happens next. Every factual claim on air has to cite a stored headline, or the **fact gate** cuts it.

> Status: **Step 1 of 13.** The config and the newsroom feed work. Hosts, audio, calls and the rival station are planned; see [`tasks/todo.md`](tasks/todo.md).

## Quick start

```bash
uv venv .venv && uv pip install -e ".[dev]"   # or: python -m venv .venv && pip install -e ".[dev]"
cp .env.example .env                           # keys are optional for now
.venv/Scripts/python -m pytest -q              # (Linux/macOS: .venv/bin/python)
.venv/Scripts/python -m deadair.feed --once    # poll RSS into data/deadair.db
```

Docker: `docker build -t deadair . && docker run --rm -v ./data:/app/data deadair`

## Docs

| Doc | What's in it |
|---|---|
| [core-idea](docs/core-idea.md) | The pitch in one page |
| [ideaplan](docs/ideaplan.md) | Users, riskiest assumptions, scope ladder, default provider choices |
| [PRD](docs/PRD.md) | Product requirements and success metrics |
| [TRD](docs/TRD.md) | Technical requirements, stack, latency budget |
| [architecture](docs/architecture.md) | Components, module map, concurrency, failure handling |
| [backendschema](docs/backendschema.md) | SQLite + vector store schema |
| [api-architecture](docs/api-architecture.md) | HTTP / WebSocket / Twilio endpoints and provider interfaces |
| [Appflow](docs/Appflow.md) | Block, caller, vote, feud and degraded-mode flows |
| [how-it-works](docs/how-it-works.md) | One minute of Dead Air in plain language |
| [implementation-plan](docs/implementation-plan.md) | Phased build plan, risks, open questions |
| [req.md](req.md) | The original requirements (source of truth) |

## Layout

```
config/            stations.yaml, feeds.yaml, personas/*.yaml   (all tunables, NFR-10)
src/deadair/
  config.py        YAML → validated pydantic config
  feed/            pollers → normalize → tone → dedup → SQLite store
tests/             pytest
docs/              planning docs
tasks/todo.md      task checklist
```

## Results

Filled in at Step 10 (latency, barge-in, fact gate, repetition, ratings).
