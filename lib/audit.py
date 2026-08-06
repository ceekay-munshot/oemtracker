#!/usr/bin/env python3
"""
lib/audit.py — QA gate. Runs after normalization; writes data/audit_report.md and decides
whether the run is safe to publish.
=========================================================================================

Checks (from the build brief):
  * Idempotency / dedup   — no duplicate (natural key, revision) in the store.
  * Arithmetic            — domestic+export≈total; segment sums (via adapter flags).
  * YoY / MoM sanity      — implausible swings (major OEM MoM > ±60% or YoY > ±100%).
  * Cross-source sanity   — company-disclosed OEM total vs SIAM total, same month (report only).
  * Completeness          — latest period present per live source/category (informational).
  * Unmapped OEMs & low-confidence — listed explicitly (from adapter flags).

Publish gate: a **hard** flag (data-integrity risk) means "do not commit to main — open a PR
with this report instead". Soft flags (unmapped names, low-confidence figures that were NOT
written, skipped lanes) are listed for review but do not block a clean publish.
"""

from __future__ import annotations

from collections import defaultdict

from lib import model as M
from lib import normalize
from lib.logging_util import get_logger

log = get_logger("audit")

# Flag types that BLOCK a clean publish (open a PR instead).
HARD_FLAG_TYPES = {"arithmetic", "yoy_mom", "dedup", "segment_sum"}

# Provisional flash lanes: their anomalies are review-only (sidecar overlay, revised by the
# backbone later), so a swing here never blocks publishing the core dashboard.
FLASH_SOURCES = {M.SRC_COMPANY}

# Plausibility thresholds.
MOM_LIMIT = 0.60   # ±60% month-on-month for a major OEM
YOY_LIMIT = 1.00   # ±100% year-on-year
MAJOR_TTM = 5000   # only sanity-check OEMs with a meaningful trailing volume
CROSS_SRC_TOL = 0.10  # 10% company-vs-SIAM divergence is worth reporting


class AuditReport:
    def __init__(self):
        self.sections = []          # (title, [lines])
        self.flags = defaultdict(list)  # type -> [detail]
        self.hard = False

    def add_flag(self, ftype, detail):
        self.flags[ftype].append(detail)
        if ftype in HARD_FLAG_TYPES:
            self.hard = True

    def section(self, title, lines):
        self.sections.append((title, lines))

    def to_markdown(self, run_ts, store_stats, tally):
        out = ["# Auto OEM Trends — Audit Report", "",
               f"- Run: `{run_ts}`",
               f"- Publish gate: {'❌ HARD FLAG — open PR for review' if self.hard else '✅ clean — safe to commit'}",
               f"- LLM tally: {tally.get('calls', 0)} calls, ~${tally.get('usd', 0):.3f} "
               f"({tally.get('in_tokens', 0)}+{tally.get('out_tokens', 0)} tok)", ""]
        out.append("## Store")
        for src, c in (store_stats.get("sources") or {}).items():
            out.append(f"- `{src}`: {c['records']} records, {c['latest_keys']} unique keys")
        out.append("")
        # flag summary
        out.append("## Flags")
        if not self.flags:
            out.append("- none")
        else:
            for ftype in sorted(self.flags):
                hard = " (HARD)" if ftype in HARD_FLAG_TYPES else ""
                items = self.flags[ftype]
                out.append(f"- **{ftype}**{hard}: {len(items)}")
                for d in items[:25]:
                    out.append(f"    - {d}")
                if len(items) > 25:
                    out.append(f"    - …and {len(items) - 25} more")
        out.append("")
        for title, lines in self.sections:
            out.append(f"## {title}")
            out += [f"- {l}" for l in lines] if lines else ["- (nothing to report)"]
            out.append("")
        return "\n".join(out)


def _series_index(store, sources):
    """Build {(source,category,oem,metric,freq): {period: value}} for the given sources."""
    idx = defaultdict(dict)
    for src in sources:
        for rec in store.latest_records(src):
            k = (rec["source"], rec["category"], rec["oem"], rec["metric"], rec["frequency"])
            idx[k][rec["period"]] = rec["value"]
    return idx


def _prev_month(period):
    y, m = int(period[:4]), int(period[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def _prev_year(period):
    return f"{int(period[:4]) - 1:04d}-{period[5:7]}"


def audit(store, results, *, run_ts="", store_stats=None, tally=None):
    rep = AuditReport()
    store_stats = store_stats or store.write_stats()
    tally = tally or {}

    # ---- 1. adapter flags (unmapped, low-confidence, arithmetic, extract failures, …) ----
    for res in results:
        for fl in res.flags:
            rep.add_flag(fl["type"], f"{fl.get('lane','?')}: {fl['detail']}")

    # ---- 2. lane status summary ------------------------------------------------------
    lane_lines = []
    for res in results:
        lane_lines.append(f"`{res.name}` (lane {res.lane}): {res.status}"
                          + (f" — {res.reason}" if res.reason else "")
                          + f" · records={len(res.records)} flags={len(res.flags)}")
    rep.section("Lane status", lane_lines)

    # Which sources got new/changed data this run (audit is scoped to these + their neighbours).
    delta = [r for res in results for r in res.records]
    live_sources = sorted({r["source"] for r in delta}) or []

    # ---- 3. idempotency / dedup (store-wide, cheap) ----------------------------------
    seen = defaultdict(set)
    dups = 0
    for rec in store.iter_records():
        k = (rec["source"], rec["category"], rec["segment"], rec["oem"],
             rec["metric"], rec["frequency"], rec["period"])
        if rec["revision"] in seen[k]:
            dups += 1
            if dups <= 10:
                rep.add_flag("dedup", f"duplicate revision {rec['revision']} for {k}")
        seen[k].add(rec["revision"])
    rep.section("Idempotency", [f"{dups} duplicate (key,revision) rows" if dups else
                                "no duplicate natural keys — store is idempotent"])

    if not delta:
        rep.section("New data", ["no new live records this run — last good data intact"])
        return rep

    # ---- 4. arithmetic on the delta (domestic+export≈total per source/cat/oem/period) --
    grp = defaultdict(dict)  # (src,cat,oem,period) -> {metric:value}
    for r in delta:
        grp[(r["source"], r["category"], r["oem"], r["period"])][r["metric"]] = r["value"]
    arith_bad = 0
    for (src, cat, oem, period), mm in grp.items():
        ok, detail = normalize.check_domestic_export_total(
            mm.get("Domestic"), mm.get("Exports"), mm.get("Total"))
        if not ok:
            arith_bad += 1
            rep.add_flag("arithmetic", f"{src} {cat}/{oem} {period}: {detail}")
    rep.section("Arithmetic", [f"{arith_bad} domestic+export≠total mismatches in new data"
                               if arith_bad else "new data arithmetic consistent"])

    # ---- 5. YoY / MoM sanity on the delta --------------------------------------------
    idx = _series_index(store, live_sources)
    swing_lines = []
    for r in delta:
        if r["metric"] not in ("Domestic", "Total", "Retail") or r["frequency"] != M.FREQ_M:
            continue
        series = idx.get((r["source"], r["category"], r["oem"], r["metric"], r["frequency"]), {})
        cur = r["value"]
        if not cur:
            continue
        pm = series.get(_prev_month(r["period"]))
        py = series.get(_prev_year(r["period"]))
        # A swing on the provisional FLASH lane (Company) is review-only, not a hard block: that
        # data is explicitly provisional, feeds only a sidecar overlay (not the core dashboard
        # charts), and gets confirmed/revised by the SIAM backbone later. Swings on the backbone
        # itself stay HARD. (Arithmetic is validated + dropped upstream, so it stays hard too.)
        ftype = "yoy_mom_review" if r["source"] in FLASH_SOURCES else "yoy_mom"
        # only sanity-check meaningful volumes
        if pm and abs(pm) >= MAJOR_TTM / 12 and abs(cur - pm) / abs(pm) > MOM_LIMIT:
            rep.add_flag(ftype,
                         f"{r['source']} {r['category']}/{r['oem']} {r['period']}: "
                         f"MoM {pm}->{cur} ({(cur-pm)/pm*100:+.0f}%)")
        if py and abs(py) >= MAJOR_TTM and abs(cur - py) / abs(py) > YOY_LIMIT:
            rep.add_flag(ftype,
                         f"{r['source']} {r['category']}/{r['oem']} {r['period']}: "
                         f"YoY {py}->{cur} ({(cur-py)/py*100:+.0f}%)")
    n_swings = len(rep.flags.get("yoy_mom", [])) + len(rep.flags.get("yoy_mom_review", []))
    swing_lines.append(f"{n_swings} implausible MoM/YoY swings flagged "
                       f"({len(rep.flags.get('yoy_mom', []))} hard / "
                       f"{len(rep.flags.get('yoy_mom_review', []))} flash-review)")
    rep.section("YoY / MoM sanity", swing_lines)

    # ---- 6. cross-source: Company vs SIAM OEM total, same month (report only) ---------
    cross_lines = []
    comp = defaultdict(dict)  # (cat,oem,period) -> value  (Company Total)
    siam = defaultdict(dict)
    for r in delta:
        if r["metric"] == "Total" and r["source"] == M.SRC_COMPANY:
            comp[(r["category"], r["oem"], r["period"])] = r["value"]
    for src in [M.SRC_SIAM]:
        for rec in store.latest_records(src):
            if rec["metric"] == "Total":
                siam[(rec["category"], rec["oem"], rec["period"])] = rec["value"]
    for k, cval in comp.items():
        sval = siam.get(k)
        if sval and cval and abs(cval - sval) / max(abs(sval), 1) > CROSS_SRC_TOL:
            cross_lines.append(f"{k[0]}/{k[1]} {k[2]}: company={cval} vs SIAM={sval} "
                               f"({(cval-sval)/sval*100:+.0f}%) — lanes kept separate")
    rep.section("Cross-source divergence (informational)",
                cross_lines or ["no material company-vs-SIAM divergence in new data"])

    # ---- 7. market-share sanity (recomputed from SIAM totals, sums ~100%) ------------
    share_lines = []
    siam_delta_periods = sorted({r["period"] for r in delta if r["source"] == M.SRC_SIAM
                                 and r["metric"] == "Total"})
    for period in siam_delta_periods:
        by_cat = defaultdict(dict)
        industry = {}
        for rec in store.latest_records(M.SRC_SIAM):
            if rec["metric"] == "Total" and rec["period"] == period:
                if rec["oem"] == M.OEM_INDUSTRY:
                    industry[rec["category"]] = rec["value"]
                else:
                    by_cat[rec["category"]][rec["oem"]] = rec["value"]
        for cat, totals in by_cat.items():
            ind = industry.get(cat)
            parts = sum(v for v in totals.values() if v)
            shares = normalize.market_share(totals, ind)  # denominator = independent industry total
            s = sum(shares.values())
            if ind and abs(parts - ind) / ind > 0.02:
                rep.add_flag("share_sum",
                             f"{cat} {period}: OEM parts {parts:.0f} vs SIAM industry {ind:.0f} "
                             f"({(parts - ind) / ind * 100:+.1f}%) — shares sum {s:.1f}% (OEMs may be missing)")
            elif shares and not ind and abs(s - 100.0) > 1.0:
                rep.add_flag("share_sum", f"{cat} {period}: shares sum to {s:.1f}% (expected ~100)")
            share_lines.append(f"{cat} {period}: {len(shares)} OEMs, shares sum {s:.1f}%"
                               + (f" (industry denom {ind:.0f})" if ind else " (no industry total)"))
    rep.section("Market share (recomputed from SIAM totals)",
                share_lines or ["no new SIAM totals to recompute share from"])

    log.info("audit complete — hard=%s, flag types=%s", rep.hard, sorted(rep.flags))
    return rep
