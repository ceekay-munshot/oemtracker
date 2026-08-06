#!/usr/bin/env python3
"""
scripts/resolve_tickers.py — one-shot probe: which ticker symbol does Muns actually accept?
==========================================================================================

For every ticker in config/tickers.yaml, tries the candidate symbol formats (bare NSE, then
``.NS``, plus any explicit ``yf`` override) against the Muns Corporate Announcements endpoint
(with country="India"), and records which one resolves. Prints a per-ticker coverage table and
persists the result to ``data/out/ticker_resolution.json`` (used by the live adapters).

Requires MUNS_TOKEN. Run it manually or as a workflow step to refresh coverage:

    python scripts/resolve_tickers.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import muns as muns_mod  # noqa: E402
from lib import tickers as tk  # noqa: E402
from lib.config import has_secret, tickers_config  # noqa: E402
from lib.logging_util import get_logger, redact_text  # noqa: E402

log = get_logger("resolve")


def main():
    if not has_secret("MUNS_TOKEN"):
        log.error("MUNS_TOKEN not set — cannot probe ticker resolution.")
        return 1
    tickers = (tickers_config().get("tickers") or {})
    client = muns_mod.MunsClient()
    to_d = date.today()
    froms = (to_d - timedelta(days=45)).strftime("%Y%m%d")
    tos = to_d.strftime("%Y%m%d")

    rows = []
    for oem, meta in tickers.items():
        used, count, last_err = None, 0, None
        for sym in tk.candidates(oem, meta):
            try:
                anns = client.corp_announcements(sym, froms, tos)
                used = sym
                # count flattened announcements as a rough "has data" signal
                from sources.muns_announcements import _flatten_announcements  # noqa: PLC0415
                count = len(_flatten_announcements(anns))
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.info("  %s: '%s' did not resolve (%s)", oem, sym, redact_text(str(e))[:120])
        tk.record(oem, used, used is not None, via="resolve_tickers",
                  note="" if used else redact_text(str(last_err)))
        rows.append((oem, used or "—", count))
        log.info("  %-24s -> %-14s (%d filings)", oem, used or "UNRESOLVED", count)

    ok = sum(1 for _, s, _ in rows if s != "—")
    print("\n  ticker resolution coverage")
    print("  " + "-" * 52)
    for oem, sym, count in rows:
        print(f"  {oem:26s} {sym:16s} {count:>4d} filings")
    print("  " + "-" * 52)
    print(f"  resolved {ok}/{len(rows)} tickers — written to {tk.RESOLUTION_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
