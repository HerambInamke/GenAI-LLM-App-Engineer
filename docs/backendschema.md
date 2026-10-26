# Backend Schema

SQLite, one file (`data/deadair.db`), WAL mode. Source: req §6. Times are ISO-8601 UTC strings.

```sql
CREATE TABLE feed_items (
  id           TEXT PRIMARY KEY,      -- sha1(normalized url or title)[:16]
  title        TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  source       TEXT NOT NULL,
  published_at TEXT NOT NULL,
  category     TEXT NOT NULL DEFAULT 'general',
  tone         TEXT NOT NULL CHECK (tone IN ('light','neutral','serious')),
  url          TEXT NOT NULL DEFAULT '',
  title_key    TEXT NOT NULL UNIQUE,  -- normalized title for dedup (FR-1.3)
  fetched_at   TEXT NOT NULL
);

CREATE TABLE blocks (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, planned_at TEXT NOT NULL,
  plan_json TEXT NOT NULL, cost_usd REAL NOT NULL DEFAULT 0
);

CREATE TABLE segments (
  id TEXT PRIMARY KEY, block_id TEXT NOT NULL REFERENCES blocks(id),
  type TEXT NOT NULL,     -- news|banter|song_intro|feud|caller|ad|fallback
  host TEXT, status TEXT NOT NULL,  -- planned|on_air|done|skipped|fallback
  started_at TEXT, ended_at TEXT
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY, segment_id TEXT NOT NULL REFERENCES segments(id),
  host TEXT NOT NULL, text TEXT NOT NULL,
  gate_result TEXT NOT NULL,  -- pass|stripped|regen_pass|fallback
  claims_json TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE storylines (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','resolved','dormant')),
  participants_json TEXT NOT NULL, summary TEXT NOT NULL, last_episode INTEGER
);

CREATE TABLE votes (
  id TEXT PRIMARY KEY, station TEXT NOT NULL, question TEXT NOT NULL,
  options_json TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT, result TEXT
);

CREATE TABLE vote_casts (
  vote_id TEXT NOT NULL REFERENCES votes(id),
  voter_id TEXT NOT NULL,    -- random call id or browser session id, never a phone number
  option TEXT NOT NULL, cast_at TEXT NOT NULL,
  PRIMARY KEY (vote_id, voter_id)   -- one vote per voter (FR-7.2)
);

CREATE TABLE calls (
  id TEXT PRIMARY KEY,       -- uuid4, the only caller identity (FR-6.6)
  station TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
  status TEXT NOT NULL,      -- queued|on_air|held|rejected|dropped|done
  transcript_path TEXT
);
```

## Vector store (sqlite-vec)

`memory_items(id, station, host, text, created_at, tags)` plus a `vec0` virtual table keyed by `id` with the text embedding. Retention: 7 days (FR-3.4).

## Feed item schema (application side)

`FeedItem` (pydantic) mirrors `feed_items` minus `title_key`. `tone` is a `Literal["light","neutral","serious"]`.

## Status as built

Step 1 creates `feed_items` only. Other tables land with the step that first writes them.
