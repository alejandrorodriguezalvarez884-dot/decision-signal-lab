"""The public service: the site and the on-demand analysis, from one origin.

    GET /api/health
    GET /api/companies?q=...      companies whose ticker or name matches
    GET /api/analysis/{ticker}    the company's latest results release, read by the model
    GET /api/analysis/{ticker}/stream   the same, reported step by step as it runs
    GET /api/me                   who is signed in to Market Hub, and the hub's address

With HUB_URL and HUB_SESSION_SECRET set (the deployment inside Market Hub), only people signed in
to Market Hub get in; without them (earningsradar.app) the service is public, as it always was.

Everything else is the static site, when RADAR_STATIC_DIR points at its build.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .client import BudgetExceeded
from .config import ONDEMAND_PER_IP_PER_HOUR
from .hubauth import HubGate
from .hubauth import settings as hub_settings
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


def _failure(exc: Exception, ticker: str) -> HTTPException:
    """What the visitor is told when an analysis cannot be run."""
    if isinstance(exc, UnknownCompany):
        return HTTPException(404, "No company with that ticker files with the SEC.")
    if isinstance(exc, NoResultsRelease):
        return HTTPException(
            404, "No results release found for this company in the last 14 months. It may report "
                 "under a different form, as foreign companies do.")
    if isinstance(exc, (DailyBudgetReached, BudgetExceeded)):
        return HTTPException(
            429, "The service has reached its spending limit. Companies that were already analysed "
                 "still work; new ones have to wait.")
    if isinstance(exc, httpx.HTTPError):
        log.warning("upstream failure for %s: %s", ticker, exc)
        return HTTPException(502, "EDGAR or the model did not answer. Try again in a moment.")
    log.exception("analysis of %s failed", ticker)
    return HTTPException(500, "The analysis failed. Try again in a moment.")


def default_store() -> Store:
    bucket = os.environ.get("RADAR_BUCKET", "").strip()
    return GcsStore(bucket) if bucket else FileStore()


def create_app(analyser: Analyser | None = None, directory: Directory | None = None,
               static_dir: str | None = None, hub: tuple[str, str] | None | bool = True) -> FastAPI:
    """App factory. Tests pass their own analyser and directory, so they need no network.

    ``hub`` is (hub URL, hub session secret) to admit only people signed in to Market Hub; by
    default it comes from HUB_URL and HUB_SESSION_SECRET, and None leaves the service public."""
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(title="Earnings Radar", docs_url=None, redoc_url=None, openapi_url=None)

    # Same origin in production. This only matters for local development, where the site runs
    # on its own port.
    origins = [o.strip() for o in os.environ.get("RADAR_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])
    hub = hub_settings() if hub is True else hub or None
    if hub:
        app.add_middleware(HubGate, hub_url=hub[0], secret=hub[1])

    directory = directory or Directory()
    analyser = analyser or Analyser(default_store())
    limiter = RateLimiter(ONDEMAND_PER_IP_PER_HOUR)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/me")
    def me(request: Request) -> dict:
        return {"user": getattr(request.state, "user", None), "hub": hub[0] if hub else None}

    @app.get("/api/companies")
    def companies(q: str = Query(min_length=1, max_length=60)) -> dict:
        try:
            found = directory.search(q)
        except httpx.HTTPError as exc:
            log.warning("SEC ticker list unavailable: %s", exc)
            raise HTTPException(502, "The SEC company list is not available right now.") from exc
        return {"companies": [{"ticker": r.ticker, "name": r.name} for r in found]}

    def allow(request: Request) -> None:
        # Behind the hub's sign-in there is no per-address limit (the owner's choice); the
        # spending caps still apply. The public deployment keeps it.
        if hub:
            return
        if not limiter.allow(_client_address(request)):
            raise HTTPException(429, "Too many analyses from this address. Try again in an hour.")

    @app.get("/api/analysis/{ticker}")
    def analysis(ticker: str, request: Request) -> dict:
        allow(request)
        try:
            ref = directory.get(ticker)
            result = analyser.analyse(ref)
        except Exception as exc:
            raise _failure(exc, ticker) from None
        log.info("analysis %s read_now=%s spent_usd=%s", ref.ticker, result["read_now"], result["spent_usd"])
        return result

    @app.get("/api/analysis/{ticker}/stream")
    def analysis_stream(ticker: str, request: Request) -> StreamingResponse:
        """One JSON object per line, sent as each step happens. The last line is ``done`` with
        the result, or ``error`` with the reason."""
        allow(request)
        try:
            ref = directory.get(ticker)
        except Exception as exc:
            raise _failure(exc, ticker) from None

        def lines() -> Iterator[str]:
            try:
                for event in analyser.run(ref):
                    if event["step"] == "done":
                        result = event["result"]
                        log.info("analysis %s read_now=%s spent_usd=%s", ref.ticker, result["read_now"],
                                 result["spent_usd"])
                    yield json.dumps(event) + "\n"
            except Exception as exc:
                failure = _failure(exc, ticker)
                yield json.dumps({"step": "error", "status": failure.status_code, "detail": failure.detail}) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    static_dir = static_dir or os.environ.get("RADAR_STATIC_DIR", "")
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="site")
    return app
