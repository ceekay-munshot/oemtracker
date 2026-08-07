#!/usr/bin/env python3
"""
lib/build.py — derive the dashboard JSON from the canonical store.
=================================================================

This is the production build step: it reads the append-only store (``data/store/``) and
writes exactly the ``/data`` artifacts the front-end already consumes — same shape, same
files, byte-for-byte compatible with the legacy workbook build.

How it stays identical: it reconstructs the *same* in-memory raw structures the workbook
parsers produced (per ``lib/pipeline_core``) and calls the *same* ``finalize_*`` functions.
The store round-trips through one code path, so seeded history re-derives identically and new
live months simply extend it.

It also writes **sidecar overlays** for the newer lanes (Company flash, FADA retail,
financials, concall commentary) into ``data/out/`` — kept out of the dashboard's core source
contract so the existing UI is untouched, but available (and audit-visible) for later use.
"""

from __future__ import annotations

import json
import os
import sys
from collections import OrderedDict, defaultdict

# Allow ``python3 lib/build.py`` as well as ``from lib import build`` (repo root on path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import model as M  # noqa: E402
from lib import pipeline_core as pc  # noqa: E402
from lib.normalize import canonical  # noqa: E402
from lib.store import Store  # noqa: E402


# ======================================================================================
# Reconstruct raw structures from the store, then finalize (identical to workbook path)
# ======================================================================================

def _axis_dates(store, source, category, freq):
    periods = store.get_axis(source, category, freq) or []
    return periods, {p: i for i, p in enumerate(periods)}


def build_siam_datasets(store):
    """One dataset per SIAM category, in the legacy sheet order."""
    out = OrderedDict()
    for _sheet, (cat, label) in pc.SIAM_SHEETS.items():
        periods, pidx = _axis_dates(store, M.SRC_SIAM, cat, M.FREQ_M)
        if not periods:
            continue
        n = len(periods)
        dates = [pc.month_dt(p) for p in periods]
        names = {}
        raw = OrderedDict()
        industry_raw = OrderedDict()
        for rec in store.latest_records(M.SRC_SIAM, cat):
            i = pidx.get(rec["period"])
            if i is None:
                continue
            mkey = M.SIAM_METRIC_TO_KEY.get(rec["metric"])
            if mkey is None:
                continue
            if rec["oem"] == M.OEM_INDUSTRY:
                industry_raw.setdefault(mkey, [None] * n)[i] = rec["value"]
            else:
                eid = pc.slug(rec["oem"])
                names.setdefault(eid, rec["oem"])
                raw.setdefault(eid, OrderedDict()).setdefault(mkey, [None] * n)[i] = rec["value"]
        ds = pc.finalize_siam(cat, label, dates, names, dict(raw), dict(industry_raw))
        out[f"{cat}__siam"] = ds
    return out


def _empty_coll():
    return {
        "2w": {"scooter": OrderedDict(), "motorcycle": OrderedDict(), "moped": OrderedDict(),
               "electric": OrderedDict(), "seg_total": {}, "ev_total": None,
               "dom_total": None, "exp_total": None},
        "pv": {"pc": OrderedDict(), "uv": OrderedDict(), "vans": OrderedDict(),
               "seg_total": {}, "dom_total": None, "exp_total": None},
        "3w": {"passenger": OrderedDict(), "goods": OrderedDict(), "seg_total": {},
               "dom_total": None, "exp_total": None, "ev_makers": set()},
    }


def build_internal_sheet1_datasets(store):
    """Reconstruct the shared coll for 2W/PV/3W and finalize them together."""
    # All three categories share the same monthly axis (sheet-1 header columns).
    periods, pidx = _axis_dates(store, M.SRC_INTERNAL_HIST, "2w", M.FREQ_M)
    if not periods:
        return OrderedDict()
    n = len(periods)
    dates = [pc.month_dt(p) for p in periods]
    coll = _empty_coll()

    for cat in ("2w", "pv", "3w"):
        for rec in store.latest_records(M.SRC_INTERNAL_HIST, cat):
            i = pidx.get(rec["period"])
            if i is None:
                continue
            seg = rec["segment"]
            oem = rec["oem"]
            val = rec["value"]
            slot = coll[cat]
            if oem == M.OEM_SEG_TOTAL:
                slot["seg_total"].setdefault(seg, [None] * n)[i] = val
            elif oem == M.OEM_EV_TOTAL:
                if slot.get("ev_total") is None:
                    slot["ev_total"] = [None] * n
                slot["ev_total"][i] = val
            elif oem == M.OEM_DOM_TOTAL:
                if slot.get("dom_total") is None:
                    slot["dom_total"] = [None] * n
                slot["dom_total"][i] = val
            elif oem == M.OEM_EXP_TOTAL:
                if slot.get("exp_total") is None:
                    slot["exp_total"] = [None] * n
                slot["exp_total"][i] = val
            else:  # a real member OEM under its sub-segment
                if seg in slot and isinstance(slot[seg], dict):
                    slot[seg].setdefault(oem, [None] * n)[i] = val

    return pc.build_internal_from_sheet1(dates, coll)


def build_tractors_dataset(store):
    periods, pidx = _axis_dates(store, M.SRC_INTERNAL_HIST, "tractors", M.FREQ_M)
    if not periods:
        return None
    n = len(periods)
    dates = [pc.month_dt(p) for p in periods]
    players = OrderedDict()
    band_totals = OrderedDict()
    for rec in store.latest_records(M.SRC_INTERNAL_HIST, "tractors"):
        i = pidx.get(rec["period"])
        if i is None:
            continue
        if rec["oem"] == M.OEM_BAND_TOTAL:
            band_totals.setdefault(rec["segment"], [None] * n)[i] = rec["value"]
        else:
            players.setdefault(rec["oem"], [None] * n)[i] = rec["value"]
    return pc.finalize_tractors(dates, players, dict(band_totals))


def build_cv_dataset(store):
    periods, pidx = _axis_dates(store, M.SRC_INTERNAL_HIST, "cv", M.FREQ_Q)
    if not periods:
        return None
    n = len(periods)
    quarters = [pc.parse_qfy(p) for p in periods]
    seg_members = {sid: OrderedDict() for sid in pc.CV_SEGMENTS}
    seg_totals = {sid: None for sid in pc.CV_SEGMENTS}
    for rec in store.latest_records(M.SRC_INTERNAL_HIST, "cv"):
        i = pidx.get(rec["period"])
        if i is None:
            continue
        sid = rec["segment"]
        if sid not in seg_members:
            continue
        if rec["oem"] == M.OEM_SEG_TOTAL:
            if seg_totals[sid] is None:
                seg_totals[sid] = [None] * n
            seg_totals[sid][i] = rec["value"]
        else:
            seg_members[sid].setdefault(rec["oem"], [None] * n)[i] = rec["value"]
    return pc.finalize_cv(quarters, seg_members, seg_totals)


def build_core_datasets(store):
    """Assemble every dashboard dataset in the exact legacy order."""
    datasets = OrderedDict()
    datasets.update(build_siam_datasets(store))
    datasets.update(build_internal_sheet1_datasets(store))
    tractors = build_tractors_dataset(store)
    if tractors is not None:
        datasets["tractors__internal"] = tractors
    cv = build_cv_dataset(store)
    if cv is not None:
        datasets["cv__internal"] = cv
    return datasets


# ======================================================================================
# Sidecar overlays for the newer lanes (NOT part of the dashboard source contract)
# ======================================================================================

def build_overlays(store, out_dir):
    """
    Emit derived JSON for the lanes the current UI does not (yet) read: Company flash,
    FADA retail, financials, concall commentary. Written under ``data/out/`` so the existing
    dashboard's source contract (``data/<cat>__siam|internal.json``) is untouched, while the
    data is derived, versioned and audit-visible for future front-end work.
    """
    os.makedirs(out_dir, exist_ok=True)
    written = []

    # ---- Company(BSE/NSE) flash — per-OEM monthly sales, kept in its own lane ---------
    company = defaultdict(lambda: defaultdict(dict))  # category -> oem -> {period: {metric,value,...}}
    for rec in store.latest_records(M.SRC_COMPANY):
        # Canonicalize the live OEM name so the overlay lines up with the seeded SIAM entity —
        # e.g. the post-demerger "Tata Motors Passenger Vehicles Limited" / "Tata Motors CV" both
        # fold onto "Tata Motors". Unmapped names pass through unchanged (still shown, just no
        # overlay match). Done at build time so already-stored raw names render without a re-run.
        oem = canonical(rec["oem"])[0]
        company[rec["category"]][oem].setdefault(rec["period"], {})[rec["metric"]] = {
            "value": rec["value"], "provisional": rec.get("provisional", False),
            "confidence": rec.get("confidence", 1.0), "source_ref": rec.get("source_ref"),
        }
    overlay = {"source": M.SRC_COMPANY, "lane": "flash",
               "note": "Listed-OEM monthly disclosures (BSE/NSE). Provisional until SIAM confirms.",
               "categories": {c: {o: dict(pers) for o, pers in oems.items()} for c, oems in company.items()}}
    written.append(_write_json(out_dir, "company_flash.json", overlay))
    # JSONP twin so the dashboard can load the overlay offline (file://), like data/*.js.
    written.append(_write_js_twin(out_dir, "company_flash", overlay, "__OEM_FLASH", "oem-flash"))

    # ---- FADA retail ------------------------------------------------------------------
    fada = defaultdict(lambda: defaultdict(dict))
    for rec in store.latest_records(M.SRC_FADA):
        oem = canonical(rec["oem"])[0]  # same canonicalization as the flash lane
        fada[rec["category"]][oem][rec["period"]] = {
            "value": rec["value"], "provisional": rec.get("provisional", False),
            "confidence": rec.get("confidence", 1.0)}
    written.append(_write_json(out_dir, "fada_retail.json", {
        "source": M.SRC_FADA, "lane": "retail", "metric": M.METRIC_RETAIL,
        "note": "FADA retail registrations. Separate lane — never blended with SIAM wholesale.",
        "categories": {c: {o: dict(p) for o, p in oems.items()} for c, oems in fada.items()}}))

    # ---- Financials overlay (promoted from adapter staging; last-good preserved) ------
    # These lanes run less often than the flash lane, so a run where they are skipped must
    # NOT clobber the previously-published overlay with an empty one (keep last good data).
    fin = _read_staging(out_dir, "_financials.json")
    if fin is not None:
        written.append(_write_json(out_dir, "financials.json", fin))
    elif not os.path.exists(os.path.join(out_dir, "financials.json")):
        written.append(_write_json(out_dir, "financials.json", {
            "source": M.SRC_FINANCIALS, "note": "Revenue / margin / valuation overlay by ticker.",
            "tickers": {}}))

    # ---- Concall commentary (same last-good-preserving promotion) ---------------------
    con = _read_staging(out_dir, "_concalls.json")
    if con is not None:
        written.append(_write_json(out_dir, "concalls.json", con))
    elif not os.path.exists(os.path.join(out_dir, "concalls.json")):
        written.append(_write_json(out_dir, "concalls.json", {
            "source": M.SRC_CONCALLS, "note": "Qualitative guidance from concall transcripts.",
            "entries": []}))

    return written


def _read_staging(out_dir, name):
    p = os.path.join(out_dir, name)
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _write_json(out_dir, name, obj):
    path = os.path.join(out_dir, name)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    return path


def _write_js_twin(out_dir, name, obj, glob, event):
    """Offline-safe JSONP twin: registers the payload on a global and fires a DOM event."""
    path = os.path.join(out_dir, f"{name}.js")
    with open(path, "w") as f:
        f.write(f"window.{glob}=" + json.dumps(obj, separators=(",", ":")) + ";"
                f"window.dispatchEvent(new Event('{event}'));")
    return path


# ======================================================================================
# Entry point
# ======================================================================================

def run_build(store_dir, out_dir):
    store = Store(store_dir)
    datasets = build_core_datasets(store)
    n, total_bytes = pc.emit(datasets, out_dir)
    overlays = build_overlays(store, os.path.join(out_dir, "out"))
    return datasets, n, total_bytes, overlays


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    store_dir = os.path.join(root, "data", "store")
    out_dir = os.path.join(root, "data")
    print("Building dashboard JSON from the canonical store ...")
    datasets, n, total_bytes, overlays = run_build(store_dir, out_dir)
    for key, ds in datasets.items():
        base = ds["frequencies"][0]
        print(f"  {key:20s} entities={len(ds['entities']):>3d}  "
              f"periods={len(ds['series'][base]['periods']):>4d}  latest={ds['latest'].get(base)}")
    print(f"\n  Wrote manifest + {n} datasets ({total_bytes/1024:.0f} KB) to {out_dir}")
    print(f"  Wrote {len(overlays)} sidecar overlays to {os.path.join(out_dir, 'out')}")
    print("Done.")


if __name__ == "__main__":
    main()
