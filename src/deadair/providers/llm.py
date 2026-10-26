"""Claude client for JSON (planning, gate, tone) and streamed host lines. Tracks cost (NFR-6)."""

import os
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# USD per 1M tokens (input, output)
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


class CostMeter:
    """Accumulates spend; the station reads and resets it at each block boundary."""

    def __init__(self) -> None:
        self.usd = 0.0

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        pin, pout = PRICES.get(model, (4.0, 20.0))
        self.usd += (input_tokens * pin + output_tokens * pout) / 1_000_000

    def add_usd(self, usd: float) -> None:
        self.usd += usd

    def take(self) -> float:
        usd, self.usd = self.usd, 0.0
        return usd


class AnthropicLLM:
    def __init__(self, meter: CostMeter | None = None, timeout: float = 20.0):
        import anthropic

        self.client = anthropic.AsyncAnthropic(timeout=timeout, max_retries=1)
        self.meter = meter or CostMeter()

    def _bill(self, model: str, usage) -> None:
        self.meter.add(model, usage.input_tokens, usage.output_tokens)

    async def parse(self, model: str, system: str, prompt: str, schema: type[T]) -> T:
        resp = await self.client.messages.parse(
            model=model,
            max_tokens=4000,
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        self._bill(model, resp.usage)
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise ValueError(f"no parsed output (stop_reason={resp.stop_reason})")
        return resp.parsed_output

    async def stream(self, model: str, system: str, prompt: str) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=model,
            max_tokens=2000,
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
            self._bill(model, (await stream.get_final_message()).usage)


def get_llm(meter: CostMeter | None = None) -> AnthropicLLM | None:
    """Real client when a key is configured; None means offline mode (template hosts, rule gate)."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return AnthropicLLM(meter)
    return None
