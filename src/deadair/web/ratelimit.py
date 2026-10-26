"""Small in-memory sliding-window rate limit for the public write endpoints."""

import os
import time
from collections import deque

from fastapi import HTTPException, Request


class RateLimit:
    def __init__(self, limit: int, per_seconds: float):
        self.limit, self.per = limit, per_seconds
        self.hits: dict[str, deque[float]] = {}

    def client(self, request: Request) -> str:
        # shortcut: per-process memory and the socket address; behind a proxy set
        # DEADAIR_TRUST_PROXY=1 so X-Forwarded-For is used, and move to Redis if you run replicas
        if os.environ.get("DEADAIR_TRUST_PROXY") == "1":
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def __call__(self, request: Request) -> None:
        now, key = time.monotonic(), self.client(request)
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= now - self.per:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "too many requests, slow down")
        q.append(now)
        if len(self.hits) > 10_000:  # drop idle clients so the table cannot grow without bound
            for k in [k for k, v in self.hits.items() if not v]:
                del self.hits[k]
