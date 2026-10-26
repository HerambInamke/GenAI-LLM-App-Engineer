"""Load and validate YAML config: stations, personas, feeds, budget (NFR-10)."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, model_validator

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


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
    llm: LLMConfig
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
