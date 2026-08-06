#!/usr/bin/env python3
"""
lib/model.py — the shared canonical vocabulary of the store.
============================================================

Source ids, reserved structural row ids, metric name maps and segment tokens live here so
the seeder (``scripts/seed_history.py``), the store-driven build (``lib/build.py``) and the
live adapters all agree on exactly how a figure is addressed. Changing a token here changes
it everywhere consistently.
"""

from __future__ import annotations

# ---- Source ids (the ``source`` field / natural-key component) -----------------------
# Each is a distinct lane. They never blend in one dashboard table (golden rule #3).
SRC_SIAM = "SIAM"                              # backbone: industry + all OEMs (wholesale)
SRC_INTERNAL_HIST = "Internal-DB(historical)"  # seeded OEM-granular history (not live-updated)
SRC_COMPANY = "Company(BSE/NSE)"               # flash: listed-OEM monthly disclosures
SRC_FADA = "FADA"                              # retail registrations
SRC_FINANCIALS = "Muns-Financials"             # revenue/margin/valuation overlay
SRC_CONCALLS = "Concalls"                      # qualitative commentary (non-numeric)

# The two seeded (backfill) sources map onto the dashboard's two existing source ids.
DASHBOARD_SOURCE_ID = {SRC_SIAM: "siam", SRC_INTERNAL_HIST: "internal"}

# ---- Reserved structural row ids (never a real OEM; excluded from entity lists) -------
OEM_INDUSTRY = "__industry__"      # SIAM industry-total block
OEM_SEG_TOTAL = "__seg_total__"    # a segment's own total (disambiguated by `segment`)
OEM_EV_TOTAL = "__ev_total__"      # EV total for a category
OEM_DOM_TOTAL = "__dom_total__"    # explicit total-domestic (EV denominator)
OEM_EXP_TOTAL = "__exp_total__"    # explicit total-exports
OEM_BAND_TOTAL = "__band_total__"  # tractor HP-band total (band carried in `segment`)

RESERVED_OEMS = {
    OEM_INDUSTRY, OEM_SEG_TOTAL, OEM_EV_TOTAL, OEM_DOM_TOTAL, OEM_EXP_TOTAL, OEM_BAND_TOTAL,
}

# ---- Metric name maps ----------------------------------------------------------------
# SIAM uses four metrics internally keyed production/domestic/exports/total; the store
# carries the human-canonical form. These maps convert both ways losslessly.
SIAM_KEY_TO_METRIC = {"production": "Production", "domestic": "Domestic",
                      "exports": "Exports", "total": "Total"}
SIAM_METRIC_TO_KEY = {v: k for k, v in SIAM_KEY_TO_METRIC.items()}

METRIC_DOMESTIC = "Domestic"
METRIC_EXPORTS = "Exports"
METRIC_RETAIL = "Retail"

# ---- Segment tokens (the ``segment`` field) ------------------------------------------
SEG_ALL = "__all__"                # source has no segment split (e.g. SIAM)
# Internal sheet-1 sub-segments:
SEG_2W = ["scooter", "motorcycle", "moped"]
SEG_2W_EV = "electric"
SEG_PV = ["pc", "uv", "vans"]
SEG_3W = ["passenger", "goods"]
# CV quarterly segments (same ids as pipeline_core.CV_SEGMENTS):
SEG_CV = ["mhcv_passenger", "mhcv_goods", "lcv_passenger", "lcv_goods"]

# ---- Frequencies ---------------------------------------------------------------------
FREQ_M = "M"
FREQ_Q = "Q"
FREQ_FY = "FY"
