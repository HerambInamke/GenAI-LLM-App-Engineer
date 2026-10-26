# Contributing

1. Set up: `uv venv .venv && uv pip install -e ".[dev]" && pre-commit install`
2. Pick the next unchecked task in `tasks/todo.md`. Keep changes to one task.
3. Write the test first when the task adds logic. Tests must run offline (use fakes for providers).
4. Before committing: `pytest -q` and `ruff check .` must pass (pre-commit runs both).
5. Commit style: `feat(feed): ...`, `fix(gate): ...`, `docs: ...`, `test: ...`.
6. Tick the task's checkboxes in `tasks/todo.md` in the same commit.

## Ground rules
- No real private individuals in fixtures or personas. Stations and hosts are fictional.
- No copyrighted music in `assets/`; royalty-free or generated only.
- Never commit `.env`, `data/`, recordings, or caller transcripts.
- New config goes in `config/*.yaml` with a pydantic model in `src/deadair/config.py`.
