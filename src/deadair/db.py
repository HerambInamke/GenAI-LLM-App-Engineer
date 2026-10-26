"""One SQLite connection with the full schema (docs/backendschema.md)."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS feed_items (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL, published_at TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
  tone TEXT NOT NULL CHECK (tone IN ('light','neutral','serious')),
  url TEXT NOT NULL DEFAULT '', title_key TEXT NOT NULL UNIQUE, fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS feed_items_published ON feed_items(published_at);
CREATE TABLE IF NOT EXISTS blocks (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, planned_at TEXT NOT NULL,
  plan_json TEXT NOT NULL, cost_usd REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS segments (
  id TEXT PRIMARY KEY, block_id TEXT NOT NULL, type TEXT NOT NULL, host TEXT,
  status TEXT NOT NULL, started_at TEXT, ended_at TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, segment_id TEXT NOT NULL, host TEXT NOT NULL, text TEXT NOT NULL,
  gate_result TEXT NOT NULL, claims_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS storylines (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','resolved','dormant')),
  participants_json TEXT NOT NULL, summary TEXT NOT NULL, last_episode INTEGER
);
CREATE TABLE IF NOT EXISTS votes (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, question TEXT NOT NULL, options_json TEXT NOT NULL,
  opened_at TEXT NOT NULL, closed_at TEXT, result TEXT
);
CREATE TABLE IF NOT EXISTS vote_casts (
  vote_id TEXT NOT NULL, voter_id TEXT NOT NULL, option TEXT NOT NULL, cast_at TEXT NOT NULL,
  PRIMARY KEY (vote_id, voter_id)
);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
  status TEXT NOT NULL, transcript_path TEXT
);
CREATE TABLE IF NOT EXISTS memory_items (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, host TEXT NOT NULL, text TEXT NOT NULL,
  created_at TEXT NOT NULL, tags TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS memory_host_time ON memory_items(host, created_at);
CREATE TABLE IF NOT EXISTS ratings (
  rater_id TEXT PRIMARY KEY, score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
  comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
"""


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the web app and station loop share one connection on one event loop
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
