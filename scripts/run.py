#!/usr/bin/env python3
"""
scripts/run.py — the monthly orchestrator (fetch -> extract -> store -> audit -> build).
=======================================================================================

Runs every enabled adapter, each fully isolated (a flaky/broken source logs, flags and is
skipped — it never aborts the run or corrupts existing data). Then it normalizes, audits and
rebuilds the dashboard JSON from the canonical store.

Idempotent & re-runnable: re-running a month appends nothing new (the store dedups by natural
key), and the build is deterministic — so a no-op run leaves ``data/`` byte-identical.

Publish decision is written to ``data/audit_status.json`` for the workflow:
  * clean  -> commit ``data/`` (Cloudflare deploys)
  * flagged (hard) -> open a PR with ``data/audit_report.md`` (a bad file never hits main)

    python3 scripts/run.py [--only siam,fada] [--period 2026-06] [--skip-seed] [--no-build]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import build as build_mod  # noqa: E402
from lib import config as cfg  # noqa: E402
from lib import extract as extract_mod  # noqa: E402
from lib import model as M  # noqa: E402
from lib.audit import audit  # noqa: E402
from lib.logging_util import get_logger  # noqa: E402
from lib.store import Store  # noqa: E402

# Import adapters so they register.
from sources import (fada, manual_intake, muns_announcements,  # noqa: E402,F401
                     muns_concalls, muns_financials, siam)
from sources.base import get_adapters  # noqa: E402

log = get_logger("run")


def _store_is_empty(store_dir):
    if not os.path.isdir(store_dir):
        return True
    return not any(f.endswith(".jsonl") for f in os.listdir(store_dir))


def _maybe_seed(store_dir):
    """Auto-seed the full history the first time (so a fresh checkout has data)."""
    if not _store_is_empty(store_dir):
        return
    log.info("store is empty — running one-time history seed …")
    import scripts.seed_history as seeder  # noqa: PLC0415
    seeder.main()


def _extend_axis_for(store, records):
    """Extend the period axis so newly-appended live months appear in the build."""
    per = {}
    for r in records:
        per.setdefault((r["source"], r["category"], r["frequency"]), set()).add(r["period"])
    for (src, cat, freq), periods in per.items():
        store.extend_axis(src, cat, freq, sorted(periods))


def main():
    ap = argparse.ArgumentParser(description="Auto OEM Trends monthly pipeline")
    ap.add_argument("--only", help="comma-separated lane names to run (default: all enabled)")
    ap.add_argument("--period", help="target period hint (YYYY-MM); adapters mostly use lookbacks")
    ap.add_argument("--skip-seed", action="store_true", help="do not auto-seed if store is empty")
    ap.add_argument("--no-build", action="store_true", help="skip the dashboard build step")
    args = ap.parse_args()

    cfg.ensure_dirs()
    run_ts = datetime.now(timezone.utc).isoformat()
    extract_mod.reset_tally()

    if not args.skip_seed:
        _maybe_seed(cfg.STORE_DIR)

    store = Store(cfg.STORE_DIR)
    lanes_cfg = (cfg.sources_config().get("lanes") or {})
    only = set(s.strip() for s in args.only.split(",")) if args.only else None

    log.info("=" * 78)
    log.info("Auto OEM Trends run @ %s  (period hint=%s, only=%s)", run_ts, args.period, only or "all")
    log.info("=" * 78)

    results = []
    for name, acls in get_adapters().items():
        if only and name not in only:
            continue
        adapter = acls(cfg=lanes_cfg.get(name, {}), store=store)
        res = adapter.run(period=args.period)
        results.append(res)

        # --- store the outputs (orchestrator owns store writes) ---
        if res.records:
            summ = store.upsert_many(res.records, ingested_at=run_ts)
            _extend_axis_for(store, res.records)
            log.info("  [%s] store upsert: +%d added, %d restated, %d skipped",
                     name, summ["added"], summ["restated"], summ["skipped"])
        for conf in res.confirms:
            n = store.confirm_periods(M.SRC_COMPANY, conf["category"], conf["periods"],
                                      by_source=conf["by_source"], ingested_at=run_ts)
            if n:
                log.info("  [%s] confirmed %d flash rows for %s %s", name, n,
                         conf["category"], conf["periods"])
        if res.overlay is not None and res.overlay_name:
            path = os.path.join(cfg.OUT_DIR, res.overlay_name)
            with open(path, "w") as f:
                json.dump(res.overlay, f, separators=(",", ":"))
            log.info("  [%s] wrote overlay staging %s", name, path)

    store.save_axis()
    stats = store.write_stats()

    # --- audit gate ---
    tally = extract_mod.run_tally()
    report = audit(store, results, run_ts=run_ts, store_stats=stats, tally=tally)
    report_md = report.to_markdown(run_ts, stats, tally)
    with open(os.path.join(cfg.DATA_DIR, "audit_report.md"), "w") as f:
        f.write(report_md)
    status = {"hard": report.hard, "run_ts": run_ts,
              "flags": {k: len(v) for k, v in report.flags.items()},
              "lanes": {r.name: r.status for r in results}}
    with open(os.path.join(cfg.DATA_DIR, "audit_status.json"), "w") as f:
        json.dump(status, f, indent=2)

    # --- build the dashboard JSON from the (now updated) store ---
    if not args.no_build:
        datasets, n, total_bytes, overlays = build_mod.run_build(cfg.STORE_DIR, cfg.DATA_DIR)
        log.info("build: %d datasets (%.0f KB) + %d overlays", n, total_bytes / 1024, len(overlays))

    # --- summary ---
    log.info("-" * 78)
    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    errored = sum(1 for r in results if r.status == "error")
    log.info("Lanes: %d ok, %d skipped, %d errored", ok, skipped, errored)
    log.info("Audit: %s  (flags: %s)",
             "HARD FLAG → PR" if report.hard else "clean → commit",
             {k: len(v) for k, v in report.flags.items()} or "none")
    log.info("LLM tally: %d calls, ~$%.3f", tally["calls"], tally["usd"])
    log.info("Done. Publish gate: %s", "PR" if report.hard else "COMMIT")
    # Always exit 0 — a flagged run is a valid outcome (workflow opens a PR).
    return 0


if __name__ == "__main__":
    sys.exit(main())
