"""Check the model's reading of guidance against an independent reader.

``sample`` draws releases stratified by the model's own answer (so the rare classes are covered),
shuffles them and writes only what a reader needs: an opaque id and the passages of the release
that talk about guidance. The model's answer is not in that file, so the reader labels blind.
``evaluate`` joins the reader's labels with the model's answers.

Stratifying by the model's answer measures precision per class ("when the model says lowered, is
it right?"). It does not measure how many lowered-guidance releases the model misses.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pandas as pd

from .config import PATHS, ROOT

VALIDATION = ROOT / "validation"
SAMPLE_FILE = VALIDATION / "guidance_sample.jsonl"
KEY_FILE = VALIDATION / "guidance_key.json"
LABELS_FILE = VALIDATION / "guidance_labels.csv"
RESULT_FILE = VALIDATION / "guidance_result.json"

GUIDANCE_CLASSES = ("raised", "lowered", "mixed", "reaffirmed", "new_period", "withdrawn", "none")
PER_CLASS = {"raised": 9, "lowered": 9, "mixed": 7, "reaffirmed": 7, "new_period": 7, "withdrawn": 2, "none": 7}
SEED = 20261004

_STRONG = re.compile(r"\b(guidance|outlook|forecasts?|targets?)\b", re.I)
_CHANGE = re.compile(r"\b(rais\w+|lower\w+|reaffirm\w+|reiterat\w+|maintain\w+|updat\w+|narrow\w+|increas\w+ (?:its|the|full)|"
                     r"withdr\w+|suspend\w+)\b", re.I)
_WEAK = re.compile(r"\b(expects?|expected|anticipat\w+|full[- ]year|fiscal (?:year )?\d{4}|range of)\b", re.I)


def guidance_excerpt(text: str, head_chars: int = 1200, max_chars: int = 3000) -> str:
    """Opening of the release plus the paragraphs most likely to state guidance."""
    head = text[:head_chars]
    paras = [p for p in text[head_chars:].split("\n") if p.strip()]

    def rank(p: str) -> int:
        if _STRONG.search(p):
            return 0 if _CHANGE.search(p) else 1
        if _CHANGE.search(p) and _WEAK.search(p):
            return 2
        return 3 if _WEAK.search(p) else 9

    picked, used = [], len(head)
    for r in (0, 1, 2, 3):
        for i, p in enumerate(paras):
            if rank(p) != r:
                continue
            p = p[:700]
            if used + len(p) > max_chars:
                continue
            picked.append((i, p))
            used += len(p)
    body = "\n".join(p for _, p in sorted(picked))
    return f"{head}\n[...]\n{body}" if body else head


def model_guidance(answers: pd.DataFrame) -> pd.DataFrame:
    g = answers[(answers["variant"] == "text_anon") & (answers["question"] == "guidance") & answers["error"].isna()]
    return g[["accessionNumber", "choice", "confidence"]].rename(columns={"choice": "model"})


def sample(answers_path: Path = PATHS.answers) -> int:
    g = model_guidance(pd.read_parquet(answers_path))
    texts = pd.read_parquet(PATHS.texts).set_index("accessionNumber")["text"]
    rng = random.Random(SEED)
    chosen = []
    for cls, n in PER_CLASS.items():
        pool = sorted(g.loc[g["model"] == cls, "accessionNumber"])
        chosen += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(chosen)
    VALIDATION.mkdir(exist_ok=True)
    key = {f"r{i:02d}": acc for i, acc in enumerate(chosen, 1)}
    KEY_FILE.write_text(json.dumps(key, indent=1) + "\n")
    with SAMPLE_FILE.open("w") as fh:
        for rid, acc in key.items():
            fh.write(json.dumps({"id": rid, "excerpt": guidance_excerpt(texts[acc])}, ensure_ascii=False) + "\n")
    return len(key)


def evaluate(answers_path: Path = PATHS.answers) -> dict:
    """Agreement between the reader and the model.

    ``reader`` is the reader's label and ``alt`` a second label the reader also accepts (a range
    narrowed around the same midpoint can be read as reaffirmed or as mixed). Releases the reader
    marked ``unclear`` state a change without its direction; they are counted apart.
    """
    key = json.loads(KEY_FILE.read_text())
    labels = pd.read_csv(LABELS_FILE).fillna("")
    labels["accessionNumber"] = labels["id"].map(key)
    m = labels.merge(model_guidance(pd.read_parquet(answers_path)), on="accessionNumber")
    unclear = m[m["reader"] == "unclear"]
    m = m[m["reader"] != "unclear"].copy()
    m["strict"] = m["reader"] == m["model"]
    m["lenient"] = m["strict"] | (m["alt"] == m["model"])

    def direction(s: pd.Series) -> pd.Series:
        # What the site's headline index uses: raised, lowered, or neither.
        return s.where(s.isin(["raised", "lowered"]), "other")

    cols = ["id", "accessionNumber", "model", "reader", "alt", "note"]
    result = {
        "labelled": int(len(m)),
        "agree_strict": int(m["strict"].sum()),
        "agree_lenient": int(m["lenient"].sum()),
        "agree_direction": int((direction(m["reader"]) == direction(m["model"])).sum()),
        "by_model_class": {
            cls: {"n": int(len(rows)), "agree_strict": int(rows["strict"].sum()),
                  "agree_lenient": int(rows["lenient"].sum())}
            for cls, rows in m.groupby("model")
        },
        "disagreements": m.loc[~m["lenient"], cols].to_dict("records"),
        "unclear": unclear[cols].to_dict("records"),
    }
    RESULT_FILE.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return result
