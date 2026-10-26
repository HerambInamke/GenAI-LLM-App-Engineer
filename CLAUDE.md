# CLAUDE.md — Dead Air

AI-run 24/7 radio station. Requirements: `req.md` (source of truth). Plan: `docs/implementation-plan.md`. Checklist: `tasks/todo.md`.

## Commands
- Tests: `.venv/Scripts/python -m pytest -q`
- Lint: `.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .`
- Poll feed once: `.venv/Scripts/python -m deadair.feed --once`
- Code graph: `graphify update .` (no LLM), then `graphify query "<question>"`

## Rules
- Cite FR/NFR ids from `req.md` in docstrings where a module implements one.
- Every external provider (LLM, TTS, STT, Twilio, news) goes behind a small interface with a fake; tests never hit the network.
- Code enforces, LLM proposes: tone rules, feud caps and citation checks are deterministic Python.
- All tunables in `config/*.yaml`, never hard-coded (NFR-10).
- Never store or log phone numbers; callers are `uuid4` ids (FR-6.6).
- Serious feed items are never used for jokes (FR-2.5).
- Default models: `claude-opus-5-5` for host lines, `claude-haiku-5-5` for gate/tone (set in `config/stations.yaml`).
- Update `tasks/todo.md` checkboxes when a task's acceptance criteria pass.

## Local-only folders (gitignored)
`.agents/`, `.skills/`, `graphify-out/`, `.claude/settings.local.json`, `data/`, `.env`.
