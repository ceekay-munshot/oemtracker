#!/usr/bin/env python3
"""
Auto OEM Trends Tracker — data pipeline (build-time).
====================================================

Reads the two source Excel workbooks and emits clean, compact JSON into ``/data``
for the static dashboard front-end. The browser NEVER parses ``.xlsx`` — all of the
messy spreadsheet wrangling happens here, once, at build time.

Sources (kept strictly separate — never blended in one table/series):
  * FILE A  Monthly_SIAM_Industry_Data_Jun26.xlsx  -> source id ``siam``
            Industry-wide, deep monthly history (Apr-1992+), 5 vehicle categories.
  * FILE B  Auto_Database_Summary__Spark.xlsx      -> source id ``internal``
            Internal OEM database, granular from Apr-2012, with EV splits.

Output:
  data/manifest.json          -> catalogue: categories, sources, datasets, entities,
                                  coverage, latest/provisional periods, attribution.
  data/<category>__<source>.json -> one file per (category, source), lazy-loaded per tab.

Design principles honoured here:
  * One source per file/series. SIAM numbers and internal-DB numbers never mix.
  * Frequencies re-aggregated on the Indian fiscal year (Apr-Mar):
        Quarterly = sum of 3 fiscal months (Q1=Apr-Jun ... Q4=Jan-Mar)
        Yearly    = sum of 12 fiscal months, labelled by ENDING calendar year (FY26 = Apr'25-Mar'26)
    Only complete periods are rolled up as final; the in-progress period is marked partial+provisional.
  * Never fabricate/interpolate. Missing -> null (renders as a gap). Trailing 0/blank from a
    non-reporting OEM is treated as MISSING (null), not a real crash-to-zero.
  * Defunct/all-zero OEMs are dropped from the JSON (never active) or flagged inactive.
  * Market share is recomputed in the browser from these raw numbers (single-sourced); the
    workbook's pre-computed share blocks are intentionally ignored.

The parser is intentionally structure-driven (it locates header rows / group headers rather
than trusting fixed column indices) so it survives the column drift these files exhibit.
It is idempotent: re-running overwrites /data deterministically.
"""

from __future__ import annotations

import json
import os
import re
from collections import OrderedDict, defaultdict
from datetime import datetime

import openpyxl

# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "data")
SIAM_XLSX = os.path.join(RAW, "Monthly_SIAM_Industry_Data_Jun26.xlsx")
SPARK_XLSX = os.path.join(RAW, "Auto_Database_Summary__Spark.xlsx")

# Number of trailing months flagged "provisional" (subject to revision / non-reporting).
PROVISIONAL_MONTHS = 2
# An entity is "active" if it has any positive value within this trailing window.
ACTIVE_WINDOW_MONTHS = 24
# Default entity set size (top-N by trailing-12-month volume) exposed to the front-end.
DEFAULT_TOP_N = 12

# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

def slug(name: str) -> str:
    """Stable id from a display name."""
    s = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())
    return s.strip("_")


def num(v):
    """Coerce a cell to float, or None if it is not a real number."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f
    s = str(v).strip().replace(",", "")
    if s == "" or s in {"-", "NA", "N/A", "na"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fy_of(dt: datetime) -> int:
    """Indian fiscal year (ending calendar year). Apr'25-Mar'26 -> 2026."""
    return dt.year + 1 if dt.month >= 4 else dt.year


def fq_of(dt: datetime) -> int:
    """Fiscal quarter 1..4. Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar."""
    return ((dt.month - 4) % 12) // 3 + 1


def month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def quarter_key(fy: int, q: int) -> str:
    return f"Q{q}FY{fy % 100:02d}"


def year_key(fy: int) -> str:
    return f"FY{fy % 100:02d}"


def parse_qfy(label: str):
    """Parse a workbook quarter label like '1QFY20' or 'Q1FY20' -> (fy_full, q). None if not matched."""
    if not isinstance(label, str):
        return None
    s = label.strip().upper().replace(" ", "")
    m = re.match(r"^(\d)QFY(\d{2})$", s) or re.match(r"^Q(\d)FY(\d{2})$", s)
    if not m:
        return None
    q = int(m.group(1))
    fy = 2000 + int(m.group(2))
    if q < 1 or q > 4:
        return None
    return fy, q


def clean_trailing_leading(values):
    """
    Convert a raw monthly value list into a 'missing-aware' list:
      * blanks (None) stay None.
      * a LEADING run of zeros/None (before the first strictly-positive value) -> None
        (the OEM had not entered the market / segment yet).
      * a TRAILING run of zeros/None (after the last strictly-positive value)  -> None
        (the OEM stopped reporting / is defunct — do not draw a crash to zero).
      * interior zeros are kept as real 0 (a genuine zero-sales month).
    Returns (cleaned_list, has_any_positive).
    """
    n = len(values)
    first_pos = None
    last_pos = None
    for i, v in enumerate(values):
        if v is not None and v > 0:
            if first_pos is None:
                first_pos = i
            last_pos = i
    if first_pos is None:
        return [None] * n, False
    out = []
    for i, v in enumerate(values):
        if i < first_pos or i > last_pos:
            out.append(None)
        else:
            out.append(None if v is None else float(v))
    return out, True


def rounded(v):
    """Round a numeric value to a compact integer (these are unit counts); pass None through."""
    if v is None:
        return None
    return int(round(v))


# --------------------------------------------------------------------------------------
# Frequency aggregation (monthly base -> quarterly / yearly on FY Apr-Mar)
# --------------------------------------------------------------------------------------

def build_month_axis(dates):
    """Given a list of datetime month-ends, return ordered month keys + index map."""
    keys = [month_key(d) for d in dates]
    return keys, {k: i for i, k in enumerate(keys)}


def aggregate_monthly_to(freq, dates, series_by_entity, industry=None):
    """
    Roll a set of monthly series up to 'quarterly' or 'yearly' on the fiscal calendar.

    series_by_entity: {entity_id: [monthly values aligned to `dates`]}  (already missing-aware)
    industry:         optional [monthly values] for the category total.

    Returns dict:
      { periods:[...], partial:[bool...], metrics_entities:{id:[...]}, industry:[...] or None }
    A period value is the sum of its member months' non-null values; if ALL member months are
    null the period is null. A period is 'partial' when it extends beyond the last data month
    (the in-progress quarter/FY) — those are shown but flagged provisional.
    """
    assert freq in ("quarterly", "yearly")
    # Group month indices by period key, preserving chronological order.
    order = []
    members = OrderedDict()
    for i, d in enumerate(dates):
        if freq == "quarterly":
            key = quarter_key(fy_of(d), fq_of(d))
            expected = 3
        else:
            key = year_key(fy_of(d))
            expected = 12
        if key not in members:
            members[key] = []
            order.append((key, expected))
        members[key].append(i)

    last_dt = dates[-1]

    def is_partial(key, expected):
        idxs = members[key]
        # Partial if fewer months than a full period are present AND it is the most recent
        # period (i.e. in-progress). Interior periods are always complete for contiguous data.
        return len(idxs) < expected and idxs[-1] == len(dates) - 1

    periods = [k for k, _ in order]
    partial = [is_partial(k, e) for k, e in order]

    def roll(monthly):
        out = []
        for k, _ in order:
            vals = [monthly[i] for i in members[k] if monthly[i] is not None]
            out.append(sum(vals) if vals else None)
        return out

    ent_out = {eid: roll(vals) for eid, vals in series_by_entity.items()}
    ind_out = roll(industry) if industry is not None else None
    return {"periods": periods, "partial": partial, "entities": ent_out, "industry": ind_out}


def provisional_month_keys(month_keys):
    return month_keys[-PROVISIONAL_MONTHS:] if len(month_keys) >= PROVISIONAL_MONTHS else list(month_keys)


# --------------------------------------------------------------------------------------
# Entity metadata (active / defunct / ttm) from a reference monthly "total" series
# --------------------------------------------------------------------------------------

def entity_meta(dates, ref_series_by_entity, names):
    """
    Compute per-entity metadata used for defaults & ranking:
      ttm     -> trailing-12-month sum of the reference series (volume proxy)
      active  -> any positive value within the trailing ACTIVE_WINDOW_MONTHS
    ref_series_by_entity values are missing-aware monthly lists.
    """
    n = len(dates)
    win = min(ACTIVE_WINDOW_MONTHS, n)
    ttm_win = min(12, n)
    metas = {}
    for eid, vals in ref_series_by_entity.items():
        recent = vals[-win:]
        active = any(v is not None and v > 0 for v in recent)
        ttm_vals = [v for v in vals[-ttm_win:] if v is not None]
        ttm = sum(ttm_vals) if ttm_vals else 0
        metas[eid] = {"id": eid, "name": names[eid], "active": active, "ttm": int(round(ttm))}
    return metas


# ======================================================================================
# FILE A — SIAM parser
# ======================================================================================

# Sheet name -> category id/label. (These are the five SIAM sheets.)
SIAM_SHEETS = OrderedDict([
    ("Passenger Vehicle", ("pv", "Passenger Vehicles")),
    ("Two Wheelers", ("2w", "Two-Wheelers")),
    ("Total 3 Wheelers", ("3w", "Three-Wheelers")),
    ("MHCV", ("mhcv", "M&HCV")),
    ("LCV", ("lcv", "LCV")),
])

SIAM_METRICS = OrderedDict([
    ("production", "Production"),
    ("domestic", "Domestic sales"),
    ("exports", "Exports sales"),
    ("total", "Total sales"),
])
# Reverse: workbook metric label -> our key
SIAM_METRIC_BY_LABEL = {v.lower(): k for k, v in SIAM_METRICS.items()}


def find_metric_row(ws_rows):
    """
    Detect header depth. Scan the first few rows for the one whose 2nd cell (col B) holds a
    SIAM metric label ('Production'). That is the metric row; the OEM row is directly above it
    and data begins directly below it. Handles the 2-row-header 'Total 3 Wheelers' sheet.
    """
    for r_idx in range(0, min(4, len(ws_rows))):
        row = ws_rows[r_idx]
        cell = row[1] if len(row) > 1 else None
        if isinstance(cell, str) and cell.strip().lower() in SIAM_METRIC_BY_LABEL:
            return r_idx  # 0-based metric row index
    raise RuntimeError("Could not locate SIAM metric header row")


def parse_siam_sheet(ws):
    """Parse one SIAM sheet into a normalized dataset dict for that category."""
    rows = list(ws.iter_rows(values_only=True))
    metric_ri = find_metric_row(rows)
    oem_ri = metric_ri - 1
    data_start = metric_ri + 1

    oem_row = rows[oem_ri]
    metric_row = rows[metric_ri]
    ncol = ws.max_column

    # Locate the appended "Industry" total group; everything at/after it is not a plain OEM
    # (Industry block + pre-computed market-share blocks which we deliberately ignore).
    industry_col = None
    for ci in range(1, ncol):
        v = oem_row[ci] if ci < len(oem_row) else None
        if isinstance(v, str) and v.strip().lower() == "industry":
            industry_col = ci
            break

    oem_region_end = industry_col if industry_col is not None else ncol

    # Walk OEM groups of 4 columns (Production/Domestic/Exports/Total). The group's name sits
    # in the OEM row at the first of its 4 columns (merged cell -> only first is filled).
    groups = []  # list of (name, {metric_key: col_index})
    ci = 1
    while ci < oem_region_end:
        name = oem_row[ci]
        if name is None or not str(name).strip():
            ci += 1
            continue
        name = str(name).strip()
        cols = {}
        for k in range(4):
            c = ci + k
            if c >= len(metric_row):
                break
            mlabel = metric_row[c]
            if isinstance(mlabel, str) and mlabel.strip().lower() in SIAM_METRIC_BY_LABEL:
                cols[SIAM_METRIC_BY_LABEL[mlabel.strip().lower()]] = c
        if cols:
            groups.append((name, cols))
        ci += 4

    # Industry block columns (4 metrics) if present.
    industry_cols = {}
    if industry_col is not None:
        for k in range(4):
            c = industry_col + k
            if c >= len(metric_row):
                break
            mlabel = metric_row[c]
            if isinstance(mlabel, str) and mlabel.strip().lower() in SIAM_METRIC_BY_LABEL:
                industry_cols[SIAM_METRIC_BY_LABEL[mlabel.strip().lower()]] = c

    # Read data rows: col A = month date. Stop at the last row that has a real date.
    dates = []
    raw_rows = []
    for r in rows[data_start:]:
        d = r[0]
        if not isinstance(d, datetime):
            continue
        dates.append(d)
        raw_rows.append(r)
    if not dates:
        raise RuntimeError("No dated rows in SIAM sheet")

    # Build raw monthly series per (entity, metric) and industry per metric.
    # Deduplicate entity names (some sheets repeat a maker) by summing into the same id.
    names = {}
    raw = defaultdict(lambda: defaultdict(lambda: [None] * len(dates)))  # eid -> metric -> [vals]

    def col_series(col):
        return [num(r[col]) if col < len(r) else None for r in raw_rows]

    for name, cols in groups:
        eid = slug(name)
        names.setdefault(eid, name)
        for mkey, col in cols.items():
            s = col_series(col)
            dst = raw[eid][mkey]
            for i, v in enumerate(s):
                if v is not None:
                    dst[i] = (dst[i] or 0) + v if dst[i] is not None else v

    industry_raw = {}
    for mkey, col in industry_cols.items():
        industry_raw[mkey] = col_series(col)

    # Clean each series (missing-aware) and drop entities that are never positive on ANY metric.
    cleaned = defaultdict(dict)  # eid -> metric -> cleaned list
    keep_ids = []
    for eid in list(raw.keys()):
        any_pos = False
        for mkey in SIAM_METRICS:
            vals = raw[eid].get(mkey, [None] * len(dates))
            cl, pos = clean_trailing_leading(vals)
            cleaned[eid][mkey] = cl
            any_pos = any_pos or pos
        if any_pos:
            keep_ids.append(eid)

    # Industry cleaned (keep interior/real; still missing-aware for trailing gaps).
    industry_clean = {}
    for mkey in SIAM_METRICS:
        vals = industry_raw.get(mkey)
        if vals is None:
            industry_clean[mkey] = None
        else:
            cl, _ = clean_trailing_leading(vals)
            industry_clean[mkey] = cl

    # Reference series for entity meta = 'total' metric (fallback to domestic).
    ref = {eid: cleaned[eid].get("total") or cleaned[eid].get("domestic") for eid in keep_ids}
    metas = entity_meta(dates, ref, names)

    month_keys, _ = build_month_axis(dates)
    prov_months = provisional_month_keys(month_keys)

    # Assemble frequency series for each metric.
    def series_block(freq):
        if freq == "monthly":
            metrics = {}
            for mkey in SIAM_METRICS:
                ents = {eid: [rounded(x) for x in cleaned[eid][mkey]] for eid in keep_ids}
                ind = [rounded(x) for x in industry_clean[mkey]] if industry_clean[mkey] else None
                metrics[mkey] = {"industry": ind, "entities": ents}
            return {"periods": month_keys, "partial": [False] * len(month_keys), "metrics": metrics}
        else:
            metrics = {}
            periods = partial = None
            for mkey in SIAM_METRICS:
                ent_series = {eid: cleaned[eid][mkey] for eid in keep_ids}
                agg = aggregate_monthly_to(freq, dates, ent_series, industry_clean[mkey])
                periods = agg["periods"]
                partial = agg["partial"]
                ents = {eid: [rounded(x) for x in agg["entities"][eid]] for eid in keep_ids}
                ind = [rounded(x) for x in agg["industry"]] if agg["industry"] is not None else None
                metrics[mkey] = {"industry": ind, "entities": ents}
            return {"periods": periods, "partial": partial, "metrics": metrics}

    series = {f: series_block(f) for f in ("monthly", "quarterly", "yearly")}

    # Provisional period keys per frequency.
    prov = {"monthly": prov_months}
    for f in ("quarterly", "yearly"):
        blk = series[f]
        prov_set = set()
        for i, key in enumerate(blk["periods"]):
            if blk["partial"][i]:
                prov_set.add(key)
        # also mark period holding the latest provisional month
        for d in dates:
            if month_key(d) in set(prov_months):
                if f == "quarterly":
                    prov_set.add(quarter_key(fy_of(d), fq_of(d)))
                else:
                    prov_set.add(year_key(fy_of(d)))
        prov[f] = sorted(prov_set)

    entities = [metas[eid] for eid in keep_ids]
    entities.sort(key=lambda m: m["ttm"], reverse=True)

    dataset = {
        "category": None,  # filled by caller
        "source": "siam",
        "source_label": "SIAM",
        "frequencies": ["monthly", "quarterly", "yearly"],
        "metrics": [{"id": k, "label": v} for k, v in SIAM_METRICS.items()],
        "default_metric": "total",
        "entities": entities,
        "series": series,
        "coverage": {"monthly": {"start": month_keys[0], "end": month_keys[-1]}},
        "latest": {f: (series[f]["periods"][-1] if series[f]["periods"] else None) for f in series},
        "provisional": prov,
        "has_industry": bool(industry_cols),
    }
    return dataset


def parse_siam():
    wb = openpyxl.load_workbook(SIAM_XLSX, data_only=True, read_only=True)
    datasets = {}
    for sheet, (cat_id, cat_label) in SIAM_SHEETS.items():
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        ds = parse_siam_sheet(ws)
        ds["category"] = cat_id
        ds["category_label"] = cat_label
        datasets[f"{cat_id}__siam"] = ds
        print(f"  [SIAM] {sheet:20s} -> {cat_id:5s}  entities={len(ds['entities'])}  "
              f"months={len(ds['series']['monthly']['periods'])}  latest={ds['latest']['monthly']}")
    wb.close()
    return datasets


# ======================================================================================
# FILE B — Internal DB parser (Spark)
# ======================================================================================
# We only ever read the MONTHLY (or, for CV, the QUARTERLY) raw columns of each sheet and
# recompute quarterly/yearly/share ourselves. The workbook's own FY / quarter / market-share
# aggregate columns are detected and skipped.


def spark_monthly_columns(header_row):
    """Return [(col_index, datetime)] for the contiguous run of monthly date columns."""
    out = []
    for ci, v in enumerate(header_row):
        if isinstance(v, datetime):
            out.append((ci, v))
    return out


# --- Sheet 1: 'OEM - Summary - 2W, PV, 3W' -------------------------------------------
# Structural label vocabulary used by the walker (parse by Col-A group headers).
S1_GROUPS = {"TWO WHEELERS", "FOUR WHEELERS", "THREE WHEELERS"}
S1_TOTAL_LABELS = {
    "total", "total domestic two wheelers", "total exports two wheelers",
    "pc volumes", "uv volumes", "total vans", "total domestic pv",
    "total export passenger cars", "total export uv", "total export vans", "total export pv",
    "passenger total", "goods total", "total exports passenger", "yoy%",
}


def parse_spark_sheet1(ws):
    """
    Parse the nested 2W / PV / 3W summary sheet into three internal datasets.
    Returns dict {cat_id: dataset_partial} with raw monthly series grouped into:
      * entities  (OEM-combined per category domestic)
      * segments  (Scooter / Motorcycle / Moped / Electric ; PC / UV / Vans ; Passenger / Goods)
      * ev        (Electric-2W total & makers ; 3W EV makers etc.)
      * exports   (segment/category export totals)
    Only the monthly columns are read.
    """
    rows = list(ws.iter_rows(values_only=True))
    header = rows[1]  # Row 2 holds the month dates
    mcols = spark_monthly_columns(header)
    dates = [d for _, d in mcols]
    col_idx = [ci for ci, _ in mcols]

    def row_series(row):
        return [num(row[ci]) if ci < len(row) else None for ci in col_idx]

    # Context-tracking walk.
    ctx_group = None       # TWO WHEELERS / FOUR WHEELERS / THREE WHEELERS
    ctx_segment = None     # e.g. '2W Domestic', 'Domestic PC', 'Passenger 3W', '2W Exports', ...
    ctx_sub = None         # e.g. 'Scooter', 'Motor cycles', 'Mopeds', 'Electric 2W'
    export_mode = False

    # Collections (raw monthly lists keyed by name).
    coll = {
        "2w": {"scooter": {}, "motorcycle": {}, "moped": {}, "electric": {},
               "seg_total": {}, "ev_total": None, "dom_total": None, "exp_total": None},
        "pv": {"pc": {}, "uv": {}, "vans": {}, "seg_total": {},
               "dom_total": None, "exp_total": None},
        "3w": {"passenger": {}, "goods": {}, "seg_total": {},
               "dom_total": None, "exp_total": None, "ev_makers": set()},
    }
    # EV maker name sets (to flag entities as EV where the workbook lists them under EV blocks).
    ev_2w_makers = set()

    def norm(lbl):
        return str(lbl).strip()

    for row in rows:
        a = row[0]
        if a is None or not str(a).strip():
            continue
        label = norm(a)
        low = label.lower()

        # Group headers
        if label in S1_GROUPS:
            ctx_group = {"TWO WHEELERS": "2w", "FOUR WHEELERS": "pv", "THREE WHEELERS": "3w"}[label]
            ctx_segment = None
            ctx_sub = None
            export_mode = False
            continue

        # Segment / sub-segment headers (set context; header rows carry no data)
        if low in ("2w domestic",):
            ctx_segment = "domestic"; ctx_sub = None; export_mode = False; continue
        if low in ("2w exports",):
            ctx_segment = "exports"; ctx_sub = None; export_mode = True; continue
        if low == "electric two wheelers":
            ctx_segment = "ev"; ctx_sub = None; export_mode = False; continue
        if low in ("scooter",):
            ctx_sub = "scooter"; continue
        if low in ("motor cycles", "motorcycles", "motorcycle"):
            ctx_sub = "motorcycle"; continue
        if low in ("mopeds", "moped"):
            ctx_sub = "moped"; continue
        if low == "electric 2w":
            ctx_sub = "ev_export"; continue
        if low in ("domestic pc",):
            ctx_group = "pv"; ctx_segment = "pc"; ctx_sub = "pc"; export_mode = False; continue
        if low in ("domestic uv",):
            ctx_group = "pv"; ctx_segment = "uv"; ctx_sub = "uv"; export_mode = False; continue
        if low == "vans":
            ctx_group = "pv"; ctx_segment = "vans"; ctx_sub = "vans"; export_mode = False; continue
        if low in ("passenger cars (export)", "utility vehicles (export)", "vans (export)"):
            ctx_group = "pv"; ctx_segment = "export"; ctx_sub = None; export_mode = True; continue
        if low in ("passenger 3w",):
            ctx_group = "3w"; ctx_segment = "passenger"; ctx_sub = "passenger"; export_mode = False; continue
        if low in ("goods 3w",):
            ctx_group = "3w"; ctx_segment = "goods"; ctx_sub = "goods"; export_mode = False; continue
        if low in ("exports - passenger 3w",):
            ctx_group = "3w"; ctx_segment = "export"; ctx_sub = None; export_mode = True; continue

        vals = row_series(row)
        has_data = any(v is not None for v in vals)

        # Total / aggregate rows -> capture segment or category totals.
        if low in S1_TOTAL_LABELS:
            if low == "yoy%":
                continue
            if ctx_group == "2w":
                if low == "total" and ctx_sub in ("scooter", "motorcycle", "moped") and not export_mode:
                    coll["2w"]["seg_total"][ctx_sub] = vals
                elif low == "total" and ctx_segment == "ev":
                    coll["2w"]["ev_total"] = vals
                elif low == "total domestic two wheelers":
                    coll["2w"]["dom_total"] = vals
                elif low == "total exports two wheelers":
                    coll["2w"]["exp_total"] = vals
            elif ctx_group == "pv":
                if low == "pc volumes":
                    coll["pv"]["seg_total"]["pc"] = vals
                elif low == "uv volumes":
                    coll["pv"]["seg_total"]["uv"] = vals
                elif low == "total vans":
                    coll["pv"]["seg_total"]["vans"] = vals
                elif low == "total domestic pv":
                    coll["pv"]["dom_total"] = vals
                elif low == "total export pv":
                    coll["pv"]["exp_total"] = vals
            elif ctx_group == "3w":
                if low == "passenger total":
                    coll["3w"]["seg_total"]["passenger"] = vals
                elif low == "goods total":
                    coll["3w"]["seg_total"]["goods"] = vals
                elif low == "total exports passenger":
                    coll["3w"]["exp_total"] = vals
            continue

        # Member OEM rows (skip export members for the domestic-focused entity view, but keep
        # export totals which are handled above).
        if not has_data and label.lower() not in ("bmw",):  # some members legitimately all-blank
            # still record structure but with all-None (dropped later if never positive)
            pass

        if ctx_group == "2w" and not export_mode:
            if ctx_segment == "ev":
                _acc(coll["2w"]["electric"], label, vals)
                ev_2w_makers.add(slug(label))
            elif ctx_sub in ("scooter", "motorcycle", "moped"):
                _acc(coll["2w"][ctx_sub], label, vals)
        elif ctx_group == "pv" and not export_mode:
            if ctx_sub in ("pc", "uv", "vans"):
                _acc(coll["pv"][ctx_sub], label, vals)
        elif ctx_group == "3w" and not export_mode:
            if ctx_sub in ("passenger", "goods"):
                _acc(coll["3w"][ctx_sub], label, vals)

    return dates, coll, ev_2w_makers


def _acc(store, name, vals):
    """Accumulate a raw monthly list into store[name] (sum on duplicate names)."""
    key = name.strip()
    if key not in store:
        store[key] = list(vals)
    else:
        cur = store[key]
        for i, v in enumerate(vals):
            if v is not None:
                cur[i] = (cur[i] or 0) + v if cur[i] is not None else v


# --------------------------------------------------------------------------------------
# Assemble internal datasets from Sheet-1 collections.
# --------------------------------------------------------------------------------------

def _combine_oem(*stores):
    """Combine several {name:[vals]} stores into one {name:[summed vals]} across sub-segments."""
    out = {}
    for st in stores:
        for name, vals in st.items():
            _acc(out, name, vals)
    return out


def _finalize_internal(cat_id, cat_label, dates, entity_store, seg_defs, ev_block, exports,
                       default_metric="domestic", freq_base="monthly", ev_maker_ids=None):
    """
    Turn raw stores into a normalized internal dataset (mirrors the SIAM dataset shape) with:
      metrics: 'domestic' (+ 'exports' if provided) built from entities
      segments: stacked mix groups over time
      ev: penetration + maker shares
    """
    # Clean entity series (missing-aware) and drop never-positive.
    names = {}
    cleaned = {}
    keep = []
    for name, vals in entity_store.items():
        eid = slug(name)
        cl, pos = clean_trailing_leading(vals)
        if pos:
            names[eid] = name
            cleaned[eid] = cl
            keep.append(eid)

    metas = entity_meta(dates, {eid: cleaned[eid] for eid in keep}, names)
    ev_maker_ids = set(ev_maker_ids or [])
    for eid in keep:
        metas[eid]["ev"] = eid in ev_maker_ids

    month_keys, _ = build_month_axis(dates)
    prov_months = provisional_month_keys(month_keys)

    # Domestic total (category) = sum of entities per period, or provided seg totals.
    def entity_total_series(monthly_dict):
        tot = []
        n = len(dates)
        for i in range(n):
            acc = None
            for eid in keep:
                v = monthly_dict[eid][i]
                if v is not None:
                    acc = (acc or 0) + v
            tot.append(acc)
        return tot

    dom_total = entity_total_series(cleaned)

    def series_block(freq):
        if freq == "monthly":
            metrics = {"domestic": {
                "industry": [rounded(x) for x in dom_total],
                "entities": {eid: [rounded(x) for x in cleaned[eid]] for eid in keep},
            }}
            if exports is not None:
                exp_cl, _ = clean_trailing_leading(exports)
                metrics["exports"] = {"industry": [rounded(x) for x in exp_cl], "entities": {}}
            return {"periods": month_keys, "partial": [False] * len(month_keys), "metrics": metrics}
        agg = aggregate_monthly_to(freq, dates, {eid: cleaned[eid] for eid in keep}, dom_total)
        metrics = {"domestic": {
            "industry": [rounded(x) for x in agg["industry"]],
            "entities": {eid: [rounded(x) for x in agg["entities"][eid]] for eid in keep},
        }}
        if exports is not None:
            exp_cl, _ = clean_trailing_leading(exports)
            eagg = aggregate_monthly_to(freq, dates, {}, exp_cl)
            metrics["exports"] = {"industry": [rounded(x) for x in eagg["industry"]], "entities": {}}
        return {"periods": agg["periods"], "partial": agg["partial"], "metrics": metrics}

    series = {f: series_block(f) for f in ("monthly", "quarterly", "yearly")}

    # Segment mix: for each freq, aggregate each segment's total series.
    segments = {}
    for freq in ("monthly", "quarterly", "yearly"):
        groups = []
        periods = series[freq]["periods"]
        for seg in seg_defs:
            raw = seg["series"]
            if freq == "monthly":
                cl, _ = clean_trailing_leading(raw)
                vals = [rounded(x) for x in cl]
            else:
                cl, _ = clean_trailing_leading(raw)
                agg = aggregate_monthly_to(freq, dates, {}, cl)
                vals = [rounded(x) for x in agg["industry"]]
            groups.append({"id": seg["id"], "label": seg["label"], "ev": seg.get("ev", False), "values": vals})
        segments[freq] = {"periods": periods, "groups": groups}

    # EV block: penetration = ev_total / segment_denominator; maker series + shares.
    ev = None
    if ev_block is not None:
        ev = {}
        for freq in ("monthly", "quarterly", "yearly"):
            periods = series[freq]["periods"]
            def agg_one(raw):
                cl, _ = clean_trailing_leading(raw)
                if freq == "monthly":
                    return [rounded(x) for x in cl]
                a = aggregate_monthly_to(freq, dates, {}, cl)
                return [rounded(x) for x in a["industry"]]
            makers = {}
            for name, raw in ev_block["makers"].items():
                makers[slug(name)] = {"name": name, "values": agg_one(raw)}
            ev[freq] = {
                "periods": periods,
                "ev_total": agg_one(ev_block["ev_total"]),
                "segment_total": agg_one(ev_block["segment_total"]),
                "makers": makers,
            }

    entities = [metas[eid] for eid in keep]
    entities.sort(key=lambda m: m["ttm"], reverse=True)

    metrics_meta = [{"id": "domestic", "label": "Domestic sales"}]
    if exports is not None:
        metrics_meta.append({"id": "exports", "label": "Exports"})

    prov = {"monthly": prov_months}
    for f in ("quarterly", "yearly"):
        prov_set = set()
        blk = series[f]
        for i, key in enumerate(blk["periods"]):
            if blk["partial"][i]:
                prov_set.add(key)
        for d in dates:
            if month_key(d) in set(prov_months):
                prov_set.add(quarter_key(fy_of(d), fq_of(d)) if f == "quarterly" else year_key(fy_of(d)))
        prov[f] = sorted(prov_set)

    return {
        "category": cat_id,
        "category_label": cat_label,
        "source": "internal",
        "source_label": "Internal DB",
        "frequencies": ["monthly", "quarterly", "yearly"],
        "metrics": metrics_meta,
        "default_metric": default_metric,
        "entities": entities,
        "series": series,
        "segments": segments,
        "ev": ev,
        "coverage": {"monthly": {"start": month_keys[0], "end": month_keys[-1]}},
        "latest": {f: (series[f]["periods"][-1] if series[f]["periods"] else None) for f in series},
        "provisional": prov,
        "has_industry": True,
    }


def build_internal_from_sheet1(dates, coll, ev_2w_makers):
    datasets = {}

    # ---- 2W internal ----
    entity_2w = _combine_oem(coll["2w"]["scooter"], coll["2w"]["motorcycle"], coll["2w"]["moped"])
    seg_defs_2w = []
    for sid, label in [("scooter", "Scooter"), ("motorcycle", "Motorcycle"), ("moped", "Moped")]:
        s = coll["2w"]["seg_total"].get(sid)
        if s is not None:
            seg_defs_2w.append({"id": sid, "label": label, "series": s})
    ev_makers = {name: vals for name, vals in coll["2w"]["electric"].items()}
    # EV segment denominator = total domestic 2W (for penetration).
    ev_block_2w = None
    if coll["2w"]["ev_total"] is not None:
        denom = coll["2w"]["dom_total"] or [None] * len(dates)
        ev_block_2w = {"ev_total": coll["2w"]["ev_total"], "segment_total": denom, "makers": ev_makers}
    ev_ids = {slug(n) for n in coll["2w"]["electric"].keys()}
    datasets["2w__internal"] = _finalize_internal(
        "2w", "Two-Wheelers", dates, entity_2w, seg_defs_2w, ev_block_2w,
        exports=coll["2w"]["exp_total"], ev_maker_ids=ev_ids)

    # ---- PV internal ----
    entity_pv = _combine_oem(coll["pv"]["pc"], coll["pv"]["uv"], coll["pv"]["vans"])
    seg_defs_pv = []
    for sid, label in [("pc", "Passenger Cars"), ("uv", "Utility Vehicles"), ("vans", "Vans")]:
        s = coll["pv"]["seg_total"].get(sid)
        if s is not None:
            seg_defs_pv.append({"id": sid, "label": label, "series": s})
    datasets["pv__internal"] = _finalize_internal(
        "pv", "Passenger Vehicles", dates, entity_pv, seg_defs_pv, None,
        exports=coll["pv"]["exp_total"])

    # ---- 3W internal ----
    entity_3w = _combine_oem(coll["3w"]["passenger"], coll["3w"]["goods"])
    seg_defs_3w = []
    for sid, label in [("passenger", "Passenger 3W"), ("goods", "Goods 3W")]:
        s = coll["3w"]["seg_total"].get(sid)
        if s is not None:
            seg_defs_3w.append({"id": sid, "label": label, "series": s})
    # 3W EV makers: TI Clean Mobility & Pinnacle Mobility (electric 3W) — flag + build EV block.
    ev_name_hints = ["ti clean", "pinnacle", "mahindra electric"]
    ev3_makers = {}
    for name, vals in coll["3w"]["passenger"].items():
        if any(h in name.lower() for h in ev_name_hints):
            ev3_makers[name] = vals
    for name, vals in coll["3w"]["goods"].items():
        if any(h in name.lower() for h in ev_name_hints):
            _acc(ev3_makers, name, vals)
    ev_block_3w = None
    if ev3_makers:
        n = len(dates)
        ev_total = [None] * n
        for vals in ev3_makers.values():
            for i, v in enumerate(vals):
                if v is not None:
                    ev_total[i] = (ev_total[i] or 0) + v
        denom = []
        pas = coll["3w"]["seg_total"].get("passenger") or [None] * n
        good = coll["3w"]["seg_total"].get("goods") or [None] * n
        for i in range(n):
            a, b = pas[i], good[i]
            denom.append((a or 0) + (b or 0) if (a is not None or b is not None) else None)
        ev_block_3w = {"ev_total": ev_total, "segment_total": denom, "makers": ev3_makers}
    ev3_ids = {slug(n) for n in ev3_makers.keys()}
    datasets["3w__internal"] = _finalize_internal(
        "3w", "Three-Wheelers", dates, entity_3w, seg_defs_3w, ev_block_3w,
        exports=coll["3w"]["exp_total"], ev_maker_ids=ev3_ids)

    return datasets


# --- Sheet 'Tractors' -----------------------------------------------------------------

def parse_spark_tractors(ws):
    """Monthly tractor sales by player with HP-band split; domestic section only for entities."""
    rows = list(ws.iter_rows(values_only=True))
    header = rows[1]  # Row 2: Player | Segment | dates...
    mcols = spark_monthly_columns(header)
    dates = [d for _, d in mcols]
    col_idx = [ci for ci, _ in mcols]

    def row_series(row):
        return [num(row[ci]) if ci < len(row) else None for ci in col_idx]

    players = {}          # player_name -> [monthly totals]
    hp_bands = defaultdict(dict)  # band_label -> {player: [vals]}  (for segment mix at player-agg)
    band_totals = defaultdict(lambda: [None] * len(dates))  # band -> [vals] across players

    section = None  # 'domestic' / 'exports'
    for row in rows[2:]:
        a = row[0]
        if a is None:
            continue
        label = str(a).strip()
        low = label.lower()
        if "domestic sales" in low and "company-wise" in low:
            section = "domestic"; continue
        if "exports" in low and "company-wise" in low:
            section = "exports"; continue
        if "grand total" in low:
            continue
        if section != "domestic":
            continue
        band = row[1]
        vals = row_series(row)
        if label.lower().endswith(" total") and band is None:
            # Player total row -> authoritative per-player monthly total.
            pname = label[:-6].strip()
            _acc(players, pname, vals)
        elif band is not None:
            bname = str(band).strip()
            _acc(hp_bands[bname], label, vals)
            for i, v in enumerate(vals):
                if v is not None:
                    bt = band_totals[bname]
                    bt[i] = (bt[i] or 0) + v if bt[i] is not None else v

    # If player-total rows were sparse, fall back to summing HP bands per player.
    if not players:
        agg = defaultdict(lambda: [None] * len(dates))
        for band, pdict in hp_bands.items():
            for p, vals in pdict.items():
                for i, v in enumerate(vals):
                    if v is not None:
                        agg[p][i] = (agg[p][i] or 0) + v if agg[p][i] is not None else v
        players = dict(agg)

    # Segment mix = HP bands (canonical order).
    band_order = ["Upto 30 hp", "31-40 hp", "41-50 hp", "51 hp and above"]
    seg_defs = []
    for b in band_order:
        if b in band_totals:
            seg_defs.append({"id": slug(b), "label": b, "series": band_totals[b]})
    # any extra bands
    for b, s in band_totals.items():
        if b not in band_order:
            seg_defs.append({"id": slug(b), "label": b, "series": s})

    ds = _finalize_internal("tractors", "Tractors", dates, players, seg_defs, None, exports=None)
    return ds


# --- Sheet 'CV' (quarterly) -----------------------------------------------------------
CV_SEGMENTS = OrderedDict([
    ("mhcv_passenger", ("M&HCV Passenger", "Total M&HCV (P)")),
    ("mhcv_goods", ("M&HCV Goods", "Total M&HCV (G)")),
    ("lcv_passenger", ("LCV - Passenger", "Total LCV (P)")),
    ("lcv_goods", ("LCV - Goods", "Total LCV (G)")),
])
CV_EV_HINTS = ["olectra", "pmi electro", "switch mobility", "jbm", "pinnacle", "ti clean"]


def parse_spark_cv(ws):
    """
    Parse the quarterly CV sheet. Base frequency is QUARTERLY (no monthly). We read only the
    first contiguous run of quarter-labelled columns (1QFY20..), then recompute FY yearly rollups.
    """
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]  # Row 1: 'Domestic Sales' | 1QFY20 | 2QFY20 | ...
    # First contiguous run of quarter columns.
    qcols = []
    started = False
    for ci, v in enumerate(header):
        pq = parse_qfy(v) if isinstance(v, str) else None
        if pq:
            qcols.append((ci, pq))
            started = True
        elif started:
            break  # stop at first non-quarter header after the run
    quarters = [pq for _, pq in qcols]  # list of (fy,q)
    col_idx = [ci for ci, _ in qcols]
    q_keys = [quarter_key(fy, q) for fy, q in quarters]

    def row_series(row):
        return [num(row[ci]) if ci < len(row) else None for ci in col_idx]

    # Walk domestic segments only (Domestic Sales section, before 'Domestic Sales - Overall').
    seg_members = {sid: {} for sid in CV_SEGMENTS}       # sid -> {oem:[q vals]}
    seg_totals = {sid: None for sid in CV_SEGMENTS}      # sid -> [q vals]
    cur_seg = None
    header_to_sid = {v[0].lower(): k for k, v in CV_SEGMENTS.items()}
    total_to_sid = {v[1].lower(): k for k, v in CV_SEGMENTS.items()}
    stop = False
    for row in rows[1:]:
        a = row[0]
        if a is None:
            continue
        label = str(a).strip()
        low = label.lower()
        if low in ("domestic sales - overall", "exports", "export sales - overall", "production"):
            break  # only parse the first Domestic-Sales detail block
        if low in header_to_sid:
            cur_seg = header_to_sid[low]; continue
        if low in total_to_sid:
            seg_totals[total_to_sid[low]] = row_series(row); cur_seg = None; continue
        if low in ("total m&hcvs", "total lcvs", "total cvs"):
            cur_seg = None; continue
        if cur_seg is not None:
            _acc(seg_members[cur_seg], label, row_series(row))

    # Build combined OEM entities across all four segments.
    entity_store = {}
    for sid in CV_SEGMENTS:
        _acc  # noop ref
        for name, vals in seg_members[sid].items():
            _acc(entity_store, name, vals)

    # We reuse the internal finalizer, but the base frequency is quarterly. To keep one code
    # path, we assemble the dataset directly here (no monthly).
    names, cleaned, keep = {}, {}, []
    for name, vals in entity_store.items():
        eid = slug(name)
        cl, pos = clean_trailing_leading(vals)
        if pos:
            names[eid] = name; cleaned[eid] = cl; keep.append(eid)

    # Entity meta on quarterly reference: ttm = last 4 quarters.
    metas = {}
    n = len(q_keys)
    win = min(8, n); ttmw = min(4, n)
    ev_ids = set()
    for eid in keep:
        recent = cleaned[eid][-win:]
        active = any(v is not None and v > 0 for v in recent)
        ttm = sum(v for v in cleaned[eid][-ttmw:] if v is not None)
        is_ev = any(h in names[eid].lower() for h in CV_EV_HINTS)
        if is_ev:
            ev_ids.add(eid)
        metas[eid] = {"id": eid, "name": names[eid], "active": active, "ttm": int(round(ttm)), "ev": is_ev}

    def q_total(dic):
        out = []
        for i in range(n):
            acc = None
            for eid in keep:
                v = dic[eid][i]
                if v is not None:
                    acc = (acc or 0) + v
            out.append(acc)
        return out

    dom_total = q_total(cleaned)

    # FY yearly rollup from quarters (group by fy).
    fy_order = []
    fy_members = OrderedDict()
    for i, (fy, q) in enumerate(quarters):
        yk = year_key(fy)
        if yk not in fy_members:
            fy_members[yk] = []; fy_order.append((yk, fy))
        fy_members[yk].append(i)

    def roll_year(qvals):
        out = []
        for yk, _ in fy_order:
            idxs = fy_members[yk]
            vv = [qvals[i] for i in idxs if qvals[i] is not None]
            out.append(sum(vv) if vv else None)
        return out
    y_keys = [yk for yk, _ in fy_order]
    y_partial = [len(fy_members[yk]) < 4 and fy_members[yk][-1] == n - 1 for yk, _ in fy_order]

    def block(freq):
        if freq == "quarterly":
            return {
                "periods": q_keys,
                "partial": [False] * n,  # all listed quarters are complete in this sheet
                "metrics": {"domestic": {
                    "industry": [rounded(x) for x in dom_total],
                    "entities": {eid: [rounded(x) for x in cleaned[eid]] for eid in keep},
                }},
            }
        return {
            "periods": y_keys,
            "partial": y_partial,
            "metrics": {"domestic": {
                "industry": [rounded(x) for x in roll_year(dom_total)],
                "entities": {eid: [rounded(x) for x in roll_year(cleaned[eid])] for eid in keep},
            }},
        }

    series = {"quarterly": block("quarterly"), "yearly": block("yearly")}

    # Segment mix (quarterly + yearly).
    segments = {}
    for freq in ("quarterly", "yearly"):
        groups = []
        for sid, (label, _tot) in CV_SEGMENTS.items():
            tot = seg_totals[sid]
            if tot is None:
                # fall back to summing members
                tot = [None] * n
                for name, vals in seg_members[sid].items():
                    for i, v in enumerate(vals):
                        if v is not None:
                            tot[i] = (tot[i] or 0) + v if tot[i] is not None else v
            cl, _ = clean_trailing_leading(tot)
            vals = cl if freq == "quarterly" else roll_year(cl)
            groups.append({"id": sid, "label": label, "ev": False, "values": [rounded(x) for x in vals]})
        segments[freq] = {"periods": series[freq]["periods"], "groups": groups}

    # EV block: e-bus / electric CV makers ÷ total CV.
    ev_makers_raw = {}
    for sid in CV_SEGMENTS:
        for name, vals in seg_members[sid].items():
            if any(h in name.lower() for h in CV_EV_HINTS):
                _acc(ev_makers_raw, name, vals)
    ev = None
    if ev_makers_raw:
        ev_total = [None] * n
        for vals in ev_makers_raw.values():
            for i, v in enumerate(vals):
                if v is not None:
                    ev_total[i] = (ev_total[i] or 0) + v if ev_total[i] is not None else v
        ev = {}
        for freq in ("quarterly", "yearly"):
            def conv(x):
                return x if freq == "quarterly" else roll_year(x)
            makers = {slug(name): {"name": name, "values": [rounded(v) for v in conv(vals)]}
                      for name, vals in ev_makers_raw.items()}
            ev[freq] = {
                "periods": series[freq]["periods"],
                "ev_total": [rounded(v) for v in conv(ev_total)],
                "segment_total": [rounded(v) for v in conv(dom_total)],
                "makers": makers,
            }

    entities = [metas[eid] for eid in keep]
    entities.sort(key=lambda m: m["ttm"], reverse=True)

    prov = {
        "quarterly": [q_keys[-1]] if q_keys else [],
        "yearly": [y_keys[i] for i in range(len(y_keys)) if y_partial[i]],
    }

    return {
        "category": "cv",
        "category_label": "Commercial Vehicles",
        "source": "internal",
        "source_label": "Internal DB",
        "frequencies": ["quarterly", "yearly"],
        "metrics": [{"id": "domestic", "label": "Domestic sales"}],
        "default_metric": "domestic",
        "entities": entities,
        "series": series,
        "segments": segments,
        "ev": ev,
        "coverage": {"quarterly": {"start": q_keys[0] if q_keys else None,
                                   "end": q_keys[-1] if q_keys else None}},
        "latest": {"quarterly": q_keys[-1] if q_keys else None,
                   "yearly": y_keys[-1] if y_keys else None},
        "provisional": prov,
        "has_industry": True,
    }


def parse_internal():
    wb = openpyxl.load_workbook(SPARK_XLSX, data_only=True, read_only=True)
    datasets = {}

    dates, coll, ev2w = parse_spark_sheet1(wb["OEM - Summary - 2W, PV, 3W"])
    datasets.update(build_internal_from_sheet1(dates, coll, ev2w))

    datasets["tractors__internal"] = parse_spark_tractors(wb["Tractors"])
    datasets["cv__internal"] = parse_spark_cv(wb["CV"])

    wb.close()
    for k, ds in datasets.items():
        base = ds["frequencies"][0]
        print(f"  [INTERNAL] {k:18s} entities={len(ds['entities'])}  "
              f"periods={len(ds['series'][base]['periods'])}  latest={ds['latest'].get(base)}  "
              f"ev={'yes' if ds.get('ev') else 'no'}  segs={len(ds.get('segments',{}).get(base,{}).get('groups',[]))}")
    return datasets


# ======================================================================================
# Manifest + emit
# ======================================================================================

CATEGORY_ORDER = ["2w", "pv", "3w", "cv", "tractors", "mhcv", "lcv"]
CATEGORY_LABELS = {
    "2w": "Two-Wheelers", "pv": "Passenger Vehicles", "3w": "Three-Wheelers",
    "cv": "Commercial Vehicles", "tractors": "Tractors", "mhcv": "M&HCV", "lcv": "LCV",
}


def emit(datasets):
    os.makedirs(OUT, exist_ok=True)

    # Build manifest.
    cats = OrderedDict()
    dmeta = OrderedDict()
    for key, ds in datasets.items():
        cat = ds["category"]
        src = ds["source"]
        base = ds["frequencies"][0]
        cats.setdefault(cat, {"id": cat, "label": CATEGORY_LABELS.get(cat, cat), "sources": []})
        if src not in cats[cat]["sources"]:
            cats[cat]["sources"].append(src)
        dmeta[key] = {
            "category": cat,
            "category_label": ds.get("category_label", CATEGORY_LABELS.get(cat, cat)),
            "source": src,
            "source_label": ds["source_label"],
            "file": f"{key}.json",
            "frequencies": ds["frequencies"],
            "metrics": ds["metrics"],
            "default_metric": ds["default_metric"],
            "coverage": ds["coverage"],
            "latest": ds["latest"],
            "provisional": ds["provisional"],
            "n_entities": len(ds["entities"]),
            "n_active": sum(1 for e in ds["entities"] if e.get("active")),
            "has_ev": bool(ds.get("ev")),
            "has_segments": bool(ds.get("segments")),
            "top_default": [e["id"] for e in ds["entities"] if e.get("active")][:DEFAULT_TOP_N],
        }

    # Order categories.
    ordered_cats = [cats[c] for c in CATEGORY_ORDER if c in cats]

    # As-of per source (max latest across that source's datasets).
    as_of = {}
    for key, ds in datasets.items():
        src = ds["source"]
        base = ds["frequencies"][0]
        latest = ds["latest"].get(base)
        as_of.setdefault(src, {"label": ds["source_label"], "latest": {}})
        as_of[src]["latest"][ds["category"]] = latest

    manifest = {
        "generated_by": "scripts/build.py",
        "sources": {
            "siam": {"label": "SIAM", "note": "Society of Indian Automobile Manufacturers — industry data"},
            "internal": {"label": "Internal DB", "note": "Internal OEM database (Spark) — OEM-granular, EV splits"},
        },
        "as_of": as_of,
        "categories": ordered_cats,
        "datasets": dmeta,
        "fiscal_year": "April-March (FY labelled by ending year, e.g. FY26 = Apr-2025..Mar-2026)",
        "provisional_months": PROVISIONAL_MONTHS,
        "default_top_n": DEFAULT_TOP_N,
    }

    # Canonical JSON artifacts (deliverables + automation seed).
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, separators=(",", ":"))
    # JS wrapper so the site loads with zero server (file:// fetch is blocked by browsers).
    # The front-end injects these as <script> tags; each registers its payload on a global.
    with open(os.path.join(OUT, "manifest.js"), "w") as f:
        f.write("window.__OEM_MANIFEST=" + json.dumps(manifest, separators=(",", ":")) + ";"
                "window.dispatchEvent(new Event('oem-manifest'));")

    total_bytes = 0
    for key, ds in datasets.items():
        payload = json.dumps(ds, separators=(",", ":"))
        with open(os.path.join(OUT, f"{key}.json"), "w") as f:
            f.write(payload)
        with open(os.path.join(OUT, f"{key}.js"), "w") as f:
            f.write(f'window.__OEM_SET&&window.__OEM_SET("{key}",' + payload + ");")
        total_bytes += len(payload)
    print(f"\n  Wrote manifest.json/.js + {len(datasets)} dataset files (json+js) "
          f"({total_bytes/1024:.0f} KB data) to {OUT}")


def main():
    print("Building Auto OEM Trends data ...")
    print("SIAM (industry):")
    siam = parse_siam()
    print("Internal DB (OEM-granular):")
    internal = parse_internal()

    datasets = OrderedDict()
    datasets.update(siam)
    datasets.update(internal)
    emit(datasets)
    print("Done.")


if __name__ == "__main__":
    main()
