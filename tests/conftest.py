import pytest

from deadair.db import connect
from deadair.eval.planted import fixture_items
from deadair.feed.store import FeedStore


@pytest.fixture
def db():
    conn = connect(":memory:")
    FeedStore(conn).add(fixture_items())
    return conn


@pytest.fixture
def items():
    return fixture_items()


class FakeLLM:
    """Scripted stand-in for AnthropicLLM: returns queued outputs, records prompts."""

    def __init__(self, streams=(), parsed=()):
        from deadair.providers.llm import CostMeter

        self.streams, self.parsed, self.prompts = list(streams), list(parsed), []
        self.meter = CostMeter()

    async def stream(self, model, system, prompt):
        self.prompts.append(prompt)
        text = self.streams.pop(0) if self.streams else "Nothing to add."
        for i in range(0, len(text), 7):  # arrive in small pieces like a real stream
            yield text[i : i + 7]

    async def parse(self, model, system, prompt, schema):
        self.prompts.append(prompt)
        if not self.parsed:
            raise ValueError("no scripted output")
        out = self.parsed.pop(0)
        return out if isinstance(out, schema) else schema.model_validate(out)
