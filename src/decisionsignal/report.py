"""Assemble the analysis panel, run every test, and write results/ (JSON + Markdown + figures)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import analysis as A
from .baselines import add_baselines
from .config import HORIZONS, PATHS, PRIMARY_HORIZON, RESULTS, model_release_date
from .features import PRIMARY_SIGNAL, PRIMARY_TARGET, event_signals, wide_features
from .prereg import is_locked
from .text import looks_like_earnings_release

INK, INK_2, SERIES_1, GRID = "#0b0b0b", "#52514e", "#2a78d6", "#e4e3df"

SECONDARY_SIGNALS = [
    "react_anon__nvr",
    "react_anon__reversal_signal",
    "react_anon__underappreciated_longterm",
    "text_anon__mismatch",
    "text_anon__naive_mismatch",
    "text_anon__composite",
]
BASELINE_SIGNALS = ["base__continuation", "base__reversal", "base__lm_tone", "base__lm_mismatch", "base__momentum"]
CONTROLS = ["r0_z", "momentum", "log_dollar_vol", "base__lm_tone"]


def build_panel() -> pd.DataFrame:
    events = pd.read_parquet(PATHS.events)
    texts = pd.read_parquet(PATHS.texts)[["accessionNumber", "text"]]
    answers = pd.read_parquet(PATHS.answers)
    feats = wide_features(answers)
    feats.to_parquet(PATHS.features, index=False)
    p = events[events["drop_reason"].isna()].merge(texts, on="accessionNumber").merge(feats, on="accessionNumber", how="left")
    if "text_anon__is_earnings_release" in p:
        p["is_earnings"] = p["text_anon__is_earnings_release"].fillna(0) >= 0.5
    else:
        p["is_earnings"] = p["text"].map(looks_like_earnings_release)
    p = p[p["is_earnings"]].reset_index(drop=True)
    p = event_signals(p)
    return add_baselines(p)


def _signal_row(d: pd.DataFrame, sig: str, edges: np.ndarray) -> dict:
    row = A.fama_macbeth_ic(d, sig, PRIMARY_TARGET, PRIMARY_HORIZON)
    row.update(A.pooled_ic_bootstrap(d, sig, PRIMARY_TARGET))
    q = A.quintile_spread(d, sig, PRIMARY_TARGET, edges)
    row.update({"q5_minus_q1": q["spread"], "q_ci_low": q["ci_low"], "q_ci_high": q["ci_high"],
                "q_means": q.get("q_means")})
    row["p_perm"] = A.permutation_placebo(d, sig, PRIMARY_TARGET)["p_perm"]
    return row


def run(include_holdout: bool | None = None) -> dict:
    panel = build_panel()
    include_holdout = is_locked() if include_holdout is None else include_holdout
    design = panel[panel["split"] == "design"]
    splits = ["design"] + (["holdout"] if include_holdout and (panel["split"] == "holdout").any() else [])
    res: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models_seen": sorted(pd.read_parquet(PATHS.answers)["model"].dropna().unique().tolist()),
        "sample": panel.groupby("split").size().to_dict(),
        "primary": {"signal": PRIMARY_SIGNAL, "target": PRIMARY_TARGET},
        "splits": {},
    }
    for split in splits:
        d = panel[panel["split"] == split]
        out: dict = {"n_events": int(len(d))}
        sigs = [s for s in [PRIMARY_SIGNAL, *SECONDARY_SIGNALS, *BASELINE_SIGNALS] if s in d and d[s].notna().any()]
        out["signals_primary_horizon"] = [_signal_row(d, s, A.design_edges(design[s])) for s in sigs]
        if PRIMARY_SIGNAL in d:
            out["primary_by_horizon"] = [A.fama_macbeth_ic(d, PRIMARY_SIGNAL, f"fwd_abn_{h}", h) | {"h": h} for h in HORIZONS]
            out["primary_sector_adjusted"] = A.fama_macbeth_ic(d, PRIMARY_SIGNAL, f"fwd_sec_abn_{PRIMARY_HORIZON}", PRIMARY_HORIZON)
            ctrls = [c for c in [*CONTROLS, "text_anon__composite"] if c in d]
            out["primary_incremental"] = A.incremental_regression(d, PRIMARY_SIGNAL, PRIMARY_TARGET, ctrls)
        sec_p = {r["signal"]: r["p"] for r in out["signals_primary_horizon"] if r["signal"] in SECONDARY_SIGNALS}
        out["secondary_holm"] = A.holm(sec_p)
        out["contamination"] = contamination(d)
        res["splits"][split] = out
    res["sensitivity_to_reaction"] = A.sensitivity_to_reaction(panel)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "results.json").write_text(json.dumps(res, indent=2, default=_json_default))
    figures(panel, splits)
    (RESULTS / "report.md").write_text(render_markdown(res), encoding="utf-8")
    return res


def contamination(d: pd.DataFrame) -> dict:
    out = {}
    for sig in ("facts_raw__fvr", "facts_anon__fvr", "react_raw__nvr", "react_anon__nvr",
                "text_raw__composite", "text_anon__composite", "probe__outperform_next_month"):
        if sig in d and d[sig].notna().any():
            out[sig] = A.fama_macbeth_ic(d, sig, PRIMARY_TARGET, PRIMARY_HORIZON)
    # Raw variants cover a sample of events; compare masked against raw on those same events.
    for raw, anon in (("facts_raw__fvr", "facts_anon__fvr"), ("react_raw__nvr", "react_anon__nvr"),
                      ("text_raw__composite", "text_anon__composite")):
        if raw in d and anon in d and d[raw].notna().any():
            same = d[d[raw].notna()]
            out[f"{anon}__on_raw_sample"] = A.fama_macbeth_ic(same, anon, PRIMARY_TARGET, PRIMARY_HORIZON)
    if "probe__outperform_next_quarter" in d:
        out["probe__outperform_next_quarter_vs_fwd60"] = A.fama_macbeth_ic(d, "probe__outperform_next_quarter", "fwd_abn_60", 60)
    by_year = []
    for yr, g in d.groupby(d["event_date"].dt.year):
        row = {"year": int(yr), "n": int(len(g))}
        for sig in ("facts_raw__fvr", "facts_anon__fvr", "probe__outperform_next_month"):
            if sig in g and g[sig].notna().sum() > 20:
                row[sig] = A.pooled_ic_bootstrap(g, sig, PRIMARY_TARGET)["pooled_ic"]
        by_year.append(row)
    out["by_year_pooled_ic"] = by_year
    released = model_release_date()
    if released and PRIMARY_SIGNAL in d:
        after = d[d["event_date"] > pd.Timestamp(released)]
        out["after_model_release"] = {"release_date": str(released), "n": int(len(after)),
                                      **A.fama_macbeth_ic(after, PRIMARY_SIGNAL, PRIMARY_TARGET, PRIMARY_HORIZON)}
    return out


def figures(panel: pd.DataFrame, splits: list[str]) -> None:
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
                         "xtick.color": INK_2, "ytick.color": INK_2, "axes.spines.top": False,
                         "axes.spines.right": False})
    if PRIMARY_SIGNAL not in panel:
        return
    edges = A.design_edges(panel.loc[panel["split"] == "design", PRIMARY_SIGNAL])
    for split in splits:
        d = panel[panel["split"] == split]
        ics = A.weekly_ic(d, PRIMARY_SIGNAL, PRIMARY_TARGET)
        if len(ics) >= 3:
            fig, ax = plt.subplots(figsize=(7, 3.2))
            ax.plot(ics.index.to_timestamp(), ics.cumsum().values, color=SERIES_1, lw=2)
            ax.axhline(0, color=GRID, lw=1)
            ax.set_title(f"Cumulative weekly rank IC, primary signal ({split})", color=INK, loc="left")
            ax.set_ylabel("cumulative IC")
            fig.tight_layout()
            fig.savefig(RESULTS / f"cum_ic_{split}.png", dpi=150)
            plt.close(fig)
        q = A.quintile_spread(d, PRIMARY_SIGNAL, PRIMARY_TARGET, edges)
        if q.get("q_means"):
            ks = sorted(q["q_means"])
            fig, ax = plt.subplots(figsize=(5, 3.2))
            ax.bar([str(k) for k in ks], [q["q_means"][k] * 100 for k in ks], color=SERIES_1, width=0.6)
            ax.axhline(0, color=INK_2, lw=1)
            ax.set_xlabel("quintile of primary signal (1 = facts weaker than reaction)")
            ax.set_ylabel(f"mean {PRIMARY_TARGET} (%)")
            ax.set_title(f"Forward abnormal return by quintile ({split})", color=INK, loc="left")
            fig.tight_layout()
            fig.savefig(RESULTS / f"quintiles_{split}.png", dpi=150)
            plt.close(fig)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp, pd.Period)):
        return str(o)
    return str(o)


def _fmt(x, pct=False, nd=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    return f"{x * 100:.2f}%" if pct else f"{x:.{nd}f}"


def render_markdown(res: dict) -> str:
    L = [f"# Results\n\nGenerated {res['generated_utc']}. Model(s): {', '.join(res['models_seen']) or '–'}.",
         f"Sample (earnings releases with prices): {res['sample']}.",
         f"Primary: `{res['primary']['signal']}` → `{res['primary']['target']}`.\n"]
    for split, out in res["splits"].items():
        tag = "CONFIRMATORY (pre-registered)" if split == "holdout" else "exploratory (questions may have been tuned here)"
        L.append(f"## {split} — {tag}\n\nEvents: {out['n_events']}\n")
        L.append("| signal | weeks | mean weekly IC | t (NW) | p | pooled IC [95% CI] | Q5−Q1 [95% CI] | p perm |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in out["signals_primary_horizon"]:
            L.append(
                f"| `{r['signal']}` | {r['weeks']} | {_fmt(r['mean_ic'])} | {_fmt(r['t_nw'], nd=2)} | {_fmt(r['p'])} | "
                f"{_fmt(r.get('pooled_ic'))} [{_fmt(r.get('ci_low'))}, {_fmt(r.get('ci_high'))}] | "
                f"{_fmt(r.get('q5_minus_q1'), True)} [{_fmt(r.get('q_ci_low'), True)}, {_fmt(r.get('q_ci_high'), True)}] | {_fmt(r.get('p_perm'))} |"
            )
        if "primary_by_horizon" in out:
            L.append("\n**Primary signal by horizon** (mean weekly IC, t):  " + ", ".join(
                f"h={r['h']}: {_fmt(r['mean_ic'])} ({_fmt(r['t_nw'], nd=2)})" for r in out["primary_by_horizon"]))
            inc = out["primary_incremental"]
            L.append(f"\n**Incremental regression** (target winsorized, per-SD coefficient, week-clustered): "
                     f"coef {_fmt(inc.get('coef_per_sd'), True)}, t {_fmt(inc.get('t'), nd=2)}, p {_fmt(inc.get('p'))}, "
                     f"n {inc.get('n')}, controls {inc.get('controls')}")
        if out["secondary_holm"]:
            L.append("\n**Secondary signals, Holm-adjusted p:** " + ", ".join(f"`{k}` {_fmt(v)}" for k, v in out["secondary_holm"].items()))
        c = out["contamination"]
        L.append("\n**Contamination checks** (mean weekly IC on the primary target):")
        for k, v in c.items():
            if k not in ("by_year_pooled_ic",):
                L.append(f"- `{k}`: {_fmt(v['mean_ic'])} (t {_fmt(v['t_nw'], nd=2)})")
        L.append("")
    s = res.get("sensitivity_to_reaction") or {}
    if s:
        L.append(f"## Does the model use the reaction?\n\nSame masked text, three made-up reactions (n={s['n']}). "
                 f"Mean P(better)−P(worse): {', '.join(f'{k.split(chr(95)*2)[0]} {v:.3f}' for k, v in s['mean_signal'].items())}. "
                 f"Monotone in the expected direction: {s['share_monotone']:.0%}. Essentially unchanged: {s['share_insensitive']:.0%}.")
    return "\n".join(L) + "\n"
