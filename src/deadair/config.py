"""Load and validate YAML config: stations, personas, feeds, budget (NFR-10)."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator

CONFIG_DIR = Path(os.environ.get("DEADAIR_CONFIG", Path(__file__).resolve().parents[2] / "config"))


class Persona(BaseModel):
    id: str
    name: str
    voice_id: str
    speaking_style: str
    catchphrases: list[str] = Field(max_length=3)  # FR-3.1
    never_do: list[str] = Field(min_length=1)


class Station(BaseModel):
    id: str
    name: str
    music_style: str
    hosts: list[str] = Field(min_length=2)  # FR-3.1


class LLMConfig(BaseModel):
    host_model: str
    fast_model: str


class Pricing(BaseModel):
    """Voice prices for the per-block cost log (NFR-6). LLM prices live in providers/llm.py."""

    tts_usd_per_1k_chars: float = Field(0.15, ge=0)
    stt_usd_per_minute: float = Field(0.0077, ge=0)


class FeedSource(BaseModel):
    name: str
    kind: Literal["rss", "newsapi"]
    url: HttpUrl
    category: str = "general"


class FeedConfig(BaseModel):
    poll_minutes: int = Field(5, gt=0)
    max_age_hours: int = Field(48, gt=0)
    sources: list[FeedSource] = Field(min_length=1)


class Config(BaseModel):
    budget_usd_per_hour: float = Field(gt=0)
    recording_retention_days: int = Field(14, ge=1)
    caller_voice_id: str = "TBD-caller-voice"  # voice for typed call-in lines read on air
    song_seconds: float = Field(150, gt=0)  # one music segment; two per block keeps blocks ~10 min
    vote_blocks: int = Field(6, ge=1)  # a vote stays open this many blocks (~1 h: one per episode)
    llm: LLMConfig
    pricing: Pricing = Pricing()
    stations: list[Station]
    personas: dict[str, Persona]
    feeds: FeedConfig

    @model_validator(mode="after")
    def _hosts_exist(self) -> "Config":
        for s in self.stations:
            missing = [h for h in s.hosts if h not in self.personas]
            if missing:
                raise ValueError(f"station {s.id!r} uses unknown personas {missing}")
        return self


def _yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(config_dir: Path = CONFIG_DIR) -> Config:
    personas = {
        p.stem: {"id": p.stem, **_yaml(p)} for p in sorted((config_dir / "personas").glob("*.yaml"))
    }
    return Config(
        **_yaml(config_dir / "stations.yaml"),
        personas=personas,
        feeds=_yaml(config_dir / "feeds.yaml"),
    )


def load_dotenv(path: Path = Path(".env")) -> int:
    """Read KEY=VALUE lines from .env into os.environ without overriding real env vars.

    Supports `# comments`, inline ` # comments` after unquoted values, and quoted values.
    Returns how many variables were set.
    """
    if not path.is_file():
        return 0
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if value[:1] in {'"', "'"} and value[0] in value[1:]:
            value = value[1 : value.index(value[0], 1)]
        else:  # "KEY=   # note" has an empty value, not "# note"
            value = "" if value.startswith("#") else value.split(" #", 1)[0].strip()
        if key and value and key not in os.environ:
            os.environ[key] = value
            n += 1
    return n
