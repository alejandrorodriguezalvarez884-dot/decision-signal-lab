"""Pre-registration lock: freeze the design before any holdout event is sent to Jev.

``lock()`` hashes the files that define the questions, signals and primary test. Holdout scoring
and holdout analysis call ``assert_locked()``, which fails if any of those files changed since.
A legitimate change after locking (e.g. a bug fix) requires re-locking *and* a dated entry in the
"Deviations" section of docs/PREREGISTRATION.md, which is itself part of the hash.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone

from .config import DOCS, PATHS, ROOT

LOCKED_FILES = (
    "src/jevsignal/questions.py",
    "src/jevsignal/features.py",
    "src/jevsignal/config.py",
    "docs/PREREGISTRATION.md",
)


def _digest(rel: str) -> str:
    data = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def current_hashes() -> dict[str, str]:
    return {rel: _digest(rel) for rel in LOCKED_FILES}


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def lock() -> dict:
    record = {
        "locked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": _git_head(),
        "files": current_hashes(),
    }
    DOCS.mkdir(exist_ok=True)
    PATHS.lock.write_text(json.dumps(record, indent=2) + "\n")
    return record


def is_locked() -> bool:
    return PATHS.lock.exists()


def assert_locked() -> None:
    if not is_locked():
        raise RuntimeError(
            "Holdout is sealed: run `jevsignal lock` (after finalizing questions on the design "
            "split and committing docs/PREREGISTRATION.md) before touching holdout events."
        )
    locked = json.loads(PATHS.lock.read_text())["files"]
    now = current_hashes()
    changed = [f for f in LOCKED_FILES if locked.get(f) != now[f]]
    if changed:
        raise RuntimeError(
            f"Pre-registered files changed since the lock: {changed}. Revert them, or document a "
            "deviation in docs/PREREGISTRATION.md and re-lock."
        )
