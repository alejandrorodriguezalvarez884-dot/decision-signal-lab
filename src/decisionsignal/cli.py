"""Command line: `uv run decisionsignal <step>`. Run `uv run decisionsignal -h` for the list."""

from __future__ import annotations

import argparse
import json
from datetime import date

from .config import HOLDOUT_START, STUDY_START


def _d(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="decisionsignal", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("universe", help="point-in-time S&P 500 spells + CIK map")
    s.add_argument("--end", type=_d, default=date.today())

    s = sub.add_parser("filings", help="8-K Item 2.02 filings + acceptance times from EDGAR")
    s.add_argument("--start", type=_d, default=STUDY_START)
    s.add_argument("--end", type=_d, default=date.today())
    s.add_argument("--limit-ciks", type=int)

    sub.add_parser("texts", help="download EX-99 exhibits and extract narrative text")

    s = sub.add_parser("prices", help="daily adjusted prices for filers, SPY and sector ETFs")
    s.add_argument("--end", type=_d, default=date.today())

    sub.add_parser("events", help="event timing, day-0 reaction, forward returns")

    for name in ("estimate", "score"):
        s = sub.add_parser(name, help="estimate cost" if name == "estimate" else "call the decision model (cached)")
        s.add_argument("--split", choices=["design", "holdout", "all"], default="design")
        s.add_argument("--limit", type=int, help="first N events only")
        s.add_argument("--n-cf", type=int, default=0, help="events for the counterfactual-reaction check")

    sub.add_parser("lock", help="freeze questions/signals before touching the holdout")
    s = sub.add_parser("report", help="run statistics and write results/")
    s.add_argument("--holdout", action="store_true", help="include holdout (requires lock)")

    s = sub.add_parser("pilot", help="small end-to-end run on design-period events")
    s.add_argument("--ciks", type=int, default=15)
    s.add_argument("--start", type=_d, default=date(2024, 7, 1))
    s.add_argument("--end", type=_d, default=date(2024, 12, 31))
    s.add_argument("--skip-model", action="store_true", help="stop before calling the API")

    a = ap.parse_args(argv)
    from . import pipeline as P

    if a.cmd == "universe":
        P.step_universe(a.end)
    elif a.cmd == "filings":
        P.step_filings(a.start, a.end, a.limit_ciks)
    elif a.cmd == "texts":
        P.step_texts()
    elif a.cmd == "prices":
        P.step_prices(a.end)
    elif a.cmd == "events":
        P.step_events()
    elif a.cmd == "estimate":
        P.step_estimate(a.split, a.limit, a.n_cf)
    elif a.cmd == "score":
        P.step_score(a.split, a.limit, a.n_cf)
    elif a.cmd == "lock":
        from .prereg import lock
        print(json.dumps(lock(), indent=2))
    elif a.cmd == "report":
        from .report import run
        res = run(include_holdout=a.holdout)
        print(f"wrote results/report.md ({', '.join(res['splits'])})")
    elif a.cmd == "pilot":
        if a.end >= HOLDOUT_START:
            raise SystemExit("The pilot must use design-period events; the holdout stays sealed.")
        P.step_universe(date.today())
        P.step_filings(a.start, a.end, a.ciks)
        P.step_texts()
        P.step_prices(date.today())
        P.step_events()
        P.step_estimate("design", None, n_cf=10)
        if a.skip_model:
            return
        P.step_score("design", None, n_cf=10)
        from .report import run
        run(include_holdout=False)
        print("pilot done: see results/report.md (statistics on ~30 events are NOT meaningful)")


if __name__ == "__main__":
    main()
