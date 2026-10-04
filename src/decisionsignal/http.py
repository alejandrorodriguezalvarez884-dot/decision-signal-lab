"""Polite, cached HTTP GET for public data sources (EDGAR, GitHub raw files)."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path

import httpx

from .config import PATHS


class RateLimiter:
    """Simple thread-safe limiter: at most ``rps`` calls per second."""

    def __init__(self, rps: float):
        self.min_interval = 1.0 / rps
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.min_interval
        if delay > 0:
            time.sleep(delay)


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()
    return PATHS.http_cache / digest[:2] / digest


def cached_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    limiter: RateLimiter | None = None,
    client: httpx.Client | None = None,
    retries: int = 5,
    use_cache: bool = True,
) -> bytes:
    """GET ``url`` once and keep the body on disk; later calls are served from disk.

    Raises ``httpx.HTTPStatusError`` for 404 and other non-retryable statuses.
    """
    path = _cache_path(url)
    # A server has no use for the on-disk copy and its disk is memory: DECISIONSIGNAL_HTTP_CACHE=off.
    keep = os.environ.get("DECISIONSIGNAL_HTTP_CACHE", "on") != "off"
    if use_cache and keep and path.exists():
        return path.read_bytes()
    own_client = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    try:
        for attempt in range(retries):
            if limiter:
                limiter.wait()
            try:
                resp = client.get(url, headers=headers)
            except httpx.TransportError:
                if attempt == retries - 1:
                    raise
                time.sleep(2**attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(float(resp.headers.get("retry-after", 2**attempt)))
                continue
            resp.raise_for_status()
            if keep:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)
            return resp.content
        resp.raise_for_status()
        raise RuntimeError(f"GET failed after {retries} attempts: {url}")
    finally:
        if own_client:
            client.close()
