#!/usr/bin/env python3
"""
scripts/selftest.py — hermetic checks for the pipeline invariants (no secrets / network needed).
==============================================================================================

Exercises the acceptance items that don't require live APIs, on a throwaway temp store:
  * live-month append into an existing series, then re-run -> ZERO duplicates (idempotent)
  * Company flash rows are provisional; SIAM confirmation flips them (revision bump)
  * SIAM market share recomputes to ~100% per category
  * arithmetic (domestic+export≠total) -> audit HARD flag -> PR gate
  * a deliberately broken source -> lane isolated (status=error), run continues
  * store round-trip build reproduces the committed dashboard JSON (delegated to verify_identity)

Exits non-zero if any invariant fails.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib import build as build_mod  # noqa: E402
from lib import model as M  # noqa: E402
from lib import normalize  # noqa: E402
from lib.audit import audit  # noqa: E402
from lib.store import Store, make_record  # noqa: E402
from sources.base import Adapter, AdapterResult  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def siam_pv_records(period, values, provisional=False):
    """values: {oem: {'Production':n,'Domestic':n,'Exports':n,'Total':n}} incl '__industry__'."""
    recs = []
    for oem, mm in values.items():
        for metric, v in mm.items():
            recs.append(make_record(M.SRC_SIAM, "pv", M.SEG_ALL, oem, metric, M.FREQ_M, period, v,
                                    provisional=provisional))
    return recs


def test_live_append_and_idempotency(tmp):
    print("\n[A] live-month append + idempotency")
    store = Store(tmp)
    # seed two prior months so finalize has a series
    for per in ("2026-04", "2026-05"):
        base = {"Maruti Suzuki": dict(Production=100000, Domestic=90000, Exports=10000, Total=100000),
                "Hyundai Motor India": dict(Production=50000, Domestic=45000, Exports=5000, Total=50000),
                M.OEM_INDUSTRY: dict(Production=150000, Domestic=135000, Exports=15000, Total=150000)}
        store.extend_axis(M.SRC_SIAM, "pv", M.FREQ_M, [per])
        store.upsert_many(siam_pv_records(per, base))
    store.save_axis()

    # a NEW live month
    new = {"Maruti Suzuki": dict(Production=110000, Domestic=99000, Exports=11000, Total=110000),
           "Hyundai Motor India": dict(Production=52000, Domestic=47000, Exports=5000, Total=52000),
           M.OEM_INDUSTRY: dict(Production=162000, Domestic=146000, Exports=16000, Total=162000)}
    store.extend_axis(M.SRC_SIAM, "pv", M.FREQ_M, ["2026-06"]); store.save_axis()
    s1 = store.upsert_many(siam_pv_records("2026-06", new))
    check("new month added records", s1["added"] == 12, f"added={s1['added']} (3 entities × 4 metrics)")

    # re-run identical -> zero new (idempotent)
    s2 = store.upsert_many(siam_pv_records("2026-06", new))
    check("re-run appends nothing (idempotent)", s2["added"] == 0 and s2["restated"] == 0,
          f"added={s2['added']} restated={s2['restated']} skipped={s2['skipped']}")

    # a genuine restatement bumps revision (not a duplicate)
    # change 3 of Maruti's 4 metrics (Exports unchanged) -> exactly 3 restatements
    revised = dict(new); revised["Maruti Suzuki"] = dict(Production=111000, Domestic=100000,
                                                          Exports=11000, Total=111000)
    s3 = store.upsert_many(siam_pv_records("2026-06", revised))
    check("restatement bumps revision (only changed metrics)", s3["restated"] == 3 and s3["added"] == 0,
          f"restated={s3['restated']} (3 of 4 metrics changed)")

    # build includes the new month and picks the latest revision
    ds = build_mod.build_siam_datasets(store)["pv__siam"]
    check("build latest month = 2026-06", ds["latest"]["monthly"] == "2026-06",
          ds["latest"]["monthly"])
    mi = ds["series"]["monthly"]["periods"].index("2026-06")
    maruti = ds["series"]["monthly"]["metrics"]["total"]["entities"]["maruti_suzuki"][mi]
    check("latest revision wins in build", maruti == 111000, f"maruti total={maruti}")


def test_market_share(tmp):
    print("\n[B] SIAM market share recomputes to ~100%")
    totals = {"Maruti Suzuki": 99000, "Hyundai Motor India": 47000, "Tata Motors": 30000}
    shares = normalize.market_share(totals)
    s = sum(shares.values())
    check("shares sum ~100%", abs(s - 100.0) < 1e-6, f"sum={s:.4f}")
    check("no pre-computed share trusted (derived from totals)", round(shares["Maruti Suzuki"], 1) == 56.2,
          f"maruti share={shares['Maruti Suzuki']:.1f}%")


def test_provisional_wave(tmp):
    print("\n[C] Company flash provisional -> SIAM confirmation flips it")
    store = Store(os.path.join(tmp, "wave"))
    flash = [make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Maruti Suzuki", "Total", M.FREQ_M,
                         "2026-06", 110000, provisional=True, confidence=0.9)]
    store.upsert_many(flash)
    latest = [r for r in store.latest_records(M.SRC_COMPANY) if r["oem"] == "Maruti Suzuki"][0]
    check("flash row is provisional", latest["provisional"] is True)

    n = store.confirm_periods(M.SRC_COMPANY, "pv", ["2026-06"],
                              keys={("Maruti Suzuki", "Total")}, by_source=M.SRC_SIAM)
    check("confirmation flips one row", n == 1, f"confirmed={n}")
    latest = sorted([r for r in store.iter_records(M.SRC_COMPANY)], key=lambda r: r["revision"])[-1]
    check("confirmed row provisional=False, revision bumped",
          latest["provisional"] is False and latest["revision"] == 1,
          f"prov={latest['provisional']} rev={latest['revision']}")
    # append-only: the original provisional row is still there
    allrows = list(store.iter_records(M.SRC_COMPANY))
    check("history preserved (both revisions on disk)", len(allrows) == 2, f"rows={len(allrows)}")

    # provisional is monotonic: re-emitting the SAME flash (provisional=True) must NOT regress
    # the confirmed row back to provisional.
    s = store.upsert_many(flash)
    check("re-emit flash does not restate confirmed row",
          s["added"] == 0 and s["restated"] == 0 and s["skipped"] == 1,
          f"added={s['added']} restated={s['restated']} skipped={s['skipped']}")
    latest = sorted(list(store.iter_records(M.SRC_COMPANY)), key=lambda r: r["revision"])[-1]
    check("row stays confirmed (False), revision unchanged",
          latest["provisional"] is False and latest["revision"] == 1,
          f"prov={latest['provisional']} rev={latest['revision']}")
    check("no extra revision written", len(list(store.iter_records(M.SRC_COMPANY))) == 2)

    # a genuine value change still restates (monotonic guard only blocks pure prov False->True)
    changed = [make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Maruti Suzuki", "Total", M.FREQ_M,
                           "2026-06", 111000, provisional=True, confidence=0.9)]
    s = store.upsert_many(changed)
    check("genuine value change still restates", s["restated"] == 1, f"restated={s['restated']}")

    # over-confirmation guard: only (oem, metric) SIAM reported get confirmed
    store2 = Store(os.path.join(os.path.dirname(store.root), "wave2"))
    store2.upsert_many([
        make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Maruti Suzuki", "Total", M.FREQ_M, "2026-06", 110000, provisional=True),
        make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Tata Motors", "Total", M.FREQ_M, "2026-06", 50000, provisional=True),
    ])
    n = store2.confirm_periods(M.SRC_COMPANY, "pv", ["2026-06"],
                               keys={("Maruti Suzuki", "Total")}, by_source=M.SRC_SIAM)
    check("only SIAM-reported (oem,metric) confirmed", n == 1, f"confirmed={n}")
    tata = [r for r in store2.latest_records(M.SRC_COMPANY) if r["oem"] == "Tata Motors"][0]
    check("OEM SIAM never reported stays provisional", tata["provisional"] is True)


def test_audit_hard_flag(tmp):
    print("\n[D] arithmetic mismatch -> audit HARD flag -> PR gate")
    store = Store(os.path.join(tmp, "audit"))
    res = AdapterResult("company_announcements", "A")
    # domestic+export = 120 but total = 200 -> arithmetic failure
    res.records = [
        make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Maruti Suzuki", "Domestic", M.FREQ_M, "2026-06", 100),
        make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Maruti Suzuki", "Exports", M.FREQ_M, "2026-06", 20),
        make_record(M.SRC_COMPANY, "pv", M.SEG_ALL, "Maruti Suzuki", "Total", M.FREQ_M, "2026-06", 200),
    ]
    store.upsert_many(res.records)
    rep = audit(store, [res], run_ts="test", store_stats=store.write_stats(), tally={})
    check("audit raises a HARD flag", rep.hard is True, f"flags={dict(rep.flags)}")
    check("arithmetic flag present", "arithmetic" in rep.flags)


def test_broken_source_isolated():
    print("\n[E] a broken source is isolated (run continues)")

    class BrokenAdapter(Adapter):
        name = "broken"; lane = "X"; store_source = "Broken"; requires_secret = None
        def fetch(self, period):
            raise RuntimeError("simulated bad token / URL")
        def extract(self, raw, res):
            pass

    res = BrokenAdapter(cfg={"enabled": True}).run()
    check("broken lane returns status=error (no crash)", res.status == "error", res.reason)
    check("broken lane produced no records", len(res.records) == 0)


def test_log_redaction():
    print("\n[F] secret redaction in logs (Scrape.do token must never leak)")
    import io
    import logging
    import requests as _rq
    from lib import http_util
    from lib.logging_util import setup
    setup()

    TOKEN = "SEKRET_TOKEN_ABC123XYZ"
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    root = logging.getLogger("oem")
    root.addHandler(handler)

    orig = http_util.requests.request

    def boom(*a, **k):  # simulate a timeout whose message embeds the token-bearing URL
        raise _rq.ConnectionError(
            "HTTPSConnectionPool(host='api.scrape.do', port=443): Max retries exceeded with "
            f"url: /?token={TOKEN}&url=https://siam.in (Caused by ConnectTimeoutError)")

    http_util.requests.request = boom
    err_msg = ""
    try:
        try:
            http_util.request("GET", "https://api.scrape.do",
                              params={"token": TOKEN, "url": "https://siam.in"},
                              max_retries=0, label="scrapedo.get")
        except http_util.NetworkError as e:
            err_msg = str(e)
    finally:
        http_util.requests.request = orig
        root.removeHandler(handler)

    logs = buf.getvalue()
    check("token absent from captured run logs", TOKEN not in logs)
    check("token absent from raised NetworkError message", TOKEN not in err_msg, err_msg[:70])
    he = http_util.HttpError(500, f"https://api.scrape.do/?token={TOKEN}", f"body token={TOKEN}")
    check("token absent from HttpError message", TOKEN not in str(he))


def main():
    tmp = tempfile.mkdtemp(prefix="oem_selftest_")
    try:
        test_live_append_and_idempotency(os.path.join(tmp, "siam"))
        test_market_share(tmp)
        test_provisional_wave(tmp)
        test_audit_hard_flag(tmp)
        test_broken_source_isolated()
        test_log_redaction()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + ("SELFTEST FAILED: " + ", ".join(FAILS) if FAILS else "SELFTEST PASSED ✓"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
