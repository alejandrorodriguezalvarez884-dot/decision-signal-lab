"""The public service: the site and the on-demand analysis, from one origin.

    GET /api/health
    GET /api/companies?q=...      companies whose ticker or name matches
    GET /api/analysis/{ticker}    the company's latest results release, read by the model

Everything else is the static site, when RADAR_STATIC_DIR points at its build.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .client import BudgetExceeded
from .config import ONDEMAND_PER_IP_PER_HOUR
from .ondemand import (
    Analyser,
    DailyBudgetReached,
    Directory,
    FileStore,
    GcsStore,
    NoResultsRelease,
    Store,
    UnknownCompany,
)

log = logging.getLogger("radar.api")


class RateLimiter:
    """At most ``limit`` calls per address in any ``window`` seconds. Per instance, in memory."""

    def __init__(self, limit: int, window: float = 3600.0):
        self.limit, self.window = limit, window
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, who: str) -> bool:
        now = time.monotonic()
        with self._lock:
            calls = self._calls[who]
            while calls and now - calls[0] > self.window:
                calls.popleft()
            if len(calls) >= self.limit:
                return False
            calls.append(now)
            return True


def _client_address(request: Request) -> str:
    # Cloud Run puts the caller first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def default_store() -> Store:
    bucket = os.environ.get("RADAR_BUCKET", "").strip()
    return GcsStore(bucket) if bucket else FileStore()


def create_app(analyser: Analyser | None = None, directory: Directory | None = None,
               static_dir: str | None = None) -> FastAPI:
    """App factory. Tests pass their own analyser and directory, so they need no network."""
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="Earnings Radar", docs_url=None, redoc_url=None, openapi_url=None)

    # Same origin in production. This only matters for local development, where the site runs
    # on its own port.
    origins = [o.strip() for o in os.environ.get("RADAR_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])

    directory = directory or Directory()
    analyser = analyser or Analyser(default_store())
    limiter = RateLimiter(ONDEMAND_PER_IP_PER_HOUR)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/companies")
    def companies(q: str = Query(min_length=1, max_length=60)) -> dict:
        try:
            found = directory.search(q)
        except httpx.HTTPError as exc:
            log.warning("SEC ticker list unavailable: %s", exc)
            raise HTTPException(502, "The SEC company list is not available right now.") from exc
        return {"companies": [{"ticker": r.ticker, "name": r.name} for r in found]}

    @app.get("/api/analysis/{ticker}")
    def analysis(ticker: str, request: Request) -> dict:
        if not limiter.allow(_client_address(request)):
            raise HTTPException(429, "Too many analyses from this address. Try again in an hour.")
        try:
            ref = directory.get(ticker)
            result = analyser.analyse(ref)
        except UnknownCompany:
            raise HTTPException(404, "No company with that ticker files with the SEC.") from None
        except NoResultsRelease:
            raise HTTPException(
                404, "No results release found for this company in the last 14 months. It may report "
                     "under a different form, as foreign companies do.") from None
        except (DailyBudgetReached, BudgetExceeded):
            raise HTTPException(
                429, "The service has reached its spending limit. Companies that were already analysed "
                     "still work; new ones have to wait.") from None
        except httpx.HTTPError as exc:
            log.warning("upstream failure for %s: %s", ticker, exc)
            raise HTTPException(502, "EDGAR or the model did not answer. Try again in a moment.") from exc
        log.info("analysis %s read_now=%s spent_usd=%s", ref.ticker, result["read_now"], result["spent_usd"])
        return result

    static_dir = static_dir or os.environ.get("RADAR_STATIC_DIR", "")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="site")
    return app
