import dataclasses

import pandas as pd
import pytest

from decisionsignal import prereg
from decisionsignal.config import PATHS
from decisionsignal.score import score_events


@pytest.fixture
def tmp_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(prereg, "PATHS", dataclasses.replace(PATHS, lock=tmp_path / "lock.json"))
    return tmp_path / "lock.json"


def test_holdout_sealed_without_lock(tmp_lock, monkeypatch):
    monkeypatch.setattr("decisionsignal.score.assert_locked", prereg.assert_locked)
    ev = pd.DataFrame({"split": ["holdout"]})
    with pytest.raises(RuntimeError, match="sealed"):
        score_events(ev, ("text_raw",), client=object())


def test_lock_detects_changes(tmp_lock, monkeypatch):
    prereg.lock()
    prereg.assert_locked()
    monkeypatch.setattr(prereg, "current_hashes", lambda: {f: "changed" for f in prereg.LOCKED_FILES})
    with pytest.raises(RuntimeError, match="changed since the lock"):
        prereg.assert_locked()
