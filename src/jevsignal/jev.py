"""Minimal TypeSafe System One client with a permanent on-disk cache and a hard spending cap.

Direct HTTP (POST /v1/systemone) instead of the SDK so the exact payload is visible and logged.
Every request is cached by a hash of (model, state, questions): re-running analysis never pays
twice, and the cache doubles as the audit trail of what Jev was asked.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import httpx
from tqdm import tqdm

from .config import (
    CHARS_PER_TOKEN_ESTIMATE,
    JEV_CONCURRENCY,
    JEV_MAX_RPS,
    JEV_MODEL,
    JEV_MODELS_URL,
    JEV_PRICE_PER_INPUT_TOKEN,
    JEV_URL,
    PATHS,
    max_usd,
    typesafe_api_key,
)
from .http import RateLimiter


def payload(state, questions: dict, model: str = JEV_MODEL) -> dict:
    return {"model": model, "state": state, "questions": questions}


def request_key(p: dict) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def estimate_tokens(p: dict) -> int:
    body = json.dumps({"state": p["state"], "questions": p["questions"]}, ensure_ascii=False)
    return int(len(body) / CHARS_PER_TOKEN_ESTIMATE) + 50


def estimate_usd(payloads: list[dict]) -> float:
    return sum(estimate_tokens(p) for p in payloads) * JEV_PRICE_PER_INPUT_TOKEN


class Cache:
    def __init__(self, path=PATHS.jev_cache):
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, request TEXT, response TEXT,"
            " model TEXT, input_tokens INTEGER, created_at REAL)"
        )
        self.db.commit()

    def get(self, key: str) -> dict | None:
        with self._lock:
            row = self.db.execute("SELECT response FROM responses WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, request: dict, response: dict) -> None:
        usage = response.get("usage", {})
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO responses VALUES (?,?,?,?,?,?)",
                (
                    key,
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(response, ensure_ascii=False),
                    response.get("model"),
                    usage.get("input_tokens"),
                    time.time(),
                ),
            )
            self.db.commit()

    def total_input_tokens(self) -> int:
        with self._lock:
            return int(self.db.execute("SELECT COALESCE(SUM(input_tokens),0) FROM responses").fetchone()[0])


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Spend:
    cap_usd: float
    input_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def usd(self) -> float:
        return self.input_tokens * JEV_PRICE_PER_INPUT_TOKEN

    def check(self) -> None:
        if self.usd > self.cap_usd:
            raise BudgetExceeded(f"spent ${self.usd:.4f} > cap ${self.cap_usd:.2f}")

    def add(self, tokens: int) -> None:
        with self._lock:
            self.input_tokens += tokens
        self.check()


class JevClient:
    def __init__(self, cache: Cache | None = None, transport: httpx.BaseTransport | None = None,
                 cap_usd: float | None = None, api_key: str | None = None):
        self.cache = cache or Cache()
        self._api_key = api_key
        self._transport = transport
        self._http: httpx.Client | None = None
        self.limiter = RateLimiter(JEV_MAX_RPS)
        self.spend = Spend(cap_usd if cap_usd is not None else max_usd())

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            key = self._api_key or typesafe_api_key()
            self._http = httpx.Client(
                timeout=120,
                transport=self._transport,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
        return self._http

    def call(self, p: dict, retries: int = 8) -> dict:
        key = request_key(p)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        self.spend.check()
        for attempt in range(retries):
            self.limiter.wait()
            try:
                resp = self.http.post(JEV_URL, json=p)
            except httpx.TransportError:
                time.sleep(min(60, 2**attempt))
                continue
            if resp.status_code in (429, 500, 502, 503, 504, 529):
                time.sleep(float(resp.headers.get("retry-after", min(60, 2**attempt))))
                continue
            if resp.status_code == 422:
                return {"error": "unprocessable", "detail": resp.text[:2000]}
            resp.raise_for_status()
            data = resp.json()
            self.cache.put(key, p, data)
            self.spend.add(int(data.get("usage", {}).get("input_tokens", 0)))
            return data
        return {"error": "retries_exhausted"}

    def call_many(self, payloads: list[dict], desc: str = "Jev") -> list[dict]:
        todo = [p for p in payloads if self.cache.get(request_key(p)) is None]
        est = estimate_usd(todo)
        print(f"{desc}: {len(payloads)} requests, {len(todo)} not cached, estimated ${est:.4f} "
              f"(cap ${self.spend.cap_usd:.2f})")
        if est > self.spend.cap_usd:
            raise BudgetExceeded(
                f"estimated ${est:.4f} exceeds JEV_MAX_USD=${self.spend.cap_usd:.2f}; raise the cap "
                "explicitly after approving the cost"
            )
        results: list[dict | None] = [None] * len(payloads)
        pool = ThreadPoolExecutor(JEV_CONCURRENCY)
        try:
            futs = {pool.submit(self.call, p): i for i, p in enumerate(payloads)}
            for fut in tqdm(as_completed(futs), total=len(futs), desc=desc):
                results[futs[fut]] = fut.result()
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)  # stop queued requests from spending
            raise
        pool.shutdown()
        print(f"{desc}: actual new spend ${self.spend.usd:.4f} ({self.spend.input_tokens} input tokens)")
        return results  # type: ignore[return-value]

    def list_models(self) -> dict:
        resp = self.http.get(JEV_MODELS_URL)
        resp.raise_for_status()
        return resp.json()
