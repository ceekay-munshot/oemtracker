#!/usr/bin/env python3
"""
sources/muns_announcements.py — Lane A (Flash): listed-OEM monthly sales from BSE/NSE.
=====================================================================================

Flow (per ticker in config/tickers.yaml):
  1. Muns Corporate Announcements for the last ~45 days (dates in YYYYMMDD).
  2. Keep only sales/production announcements (subject keyword match).
  3. Download the attached PDF -> OCR (Mistral) -> Claude extracts strict JSON:
     per segment Domestic/Export/Total + a header total, with per-figure confidence.
  4. Validate domestic+export≈total and segment sums≈total; low-confidence -> flag, not write.

Output: store records with ``source="Company(BSE/NSE)"`` and ``provisional=True`` (flash). When
SIAM later confirms the month, the orchestrator flips these to provisional=False (revision bump).
This lane never blends into the SIAM tables — it lives in its own source (golden rule #3).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from lib import model as M
from lib import muns as muns_mod
from lib import tickers as tk
from lib.logging_util import redact_text
from lib.normalize import canonical, check_domestic_export_total
from lib.store import make_record
from sources._common import min_confidence, pdf_to_json
from sources.base import Adapter, register

VALID_CATEGORIES = {"pv", "2w", "3w", "mhcv", "lcv", "tractors", "cv"}

EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company": {"type": "string"},
        "period": {"type": "string",
                   "description": "The sales month these figures cover, as YYYY-MM."},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string",
                                 "enum": sorted(VALID_CATEGORIES) + ["total", "other"]},
                    "segment": {"type": "string"},
                    "metric": {"type": "string",
                               "enum": ["Domestic", "Exports", "Total", "Production"]},
                    "value": {"type": "number"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_label": {"type": "string"},
                },
                "required": ["category", "metric", "value", "confidence"],
            },
        },
    },
    "required": ["company", "period", "rows"],
}

INSTRUCTION = (
    "This is an Indian listed automaker's monthly sales/production disclosure filed with the "
    "stock exchange. Extract ONLY the headline MONTHLY TOTAL for each vehicle category "
    "(pv, 2w, 3w, mhcv, lcv, tractors, cv): the category's Domestic sales, Exports and Total "
    "sales. Do NOT extract sub-segment / model-wise rows (Scooter, UV, individual models) — "
    "leave 'segment' blank and give one row per (category, metric). Metrics: Domestic, Exports, "
    "Total (and Production ONLY if this is a production report). Total = Domestic + Exports; if "
    "the printed figures don't add up, extract what is printed but LOWER the confidence. Set "
    "'period' to the sales MONTH as YYYY-MM (if several months are shown, use the latest). Never "
    "infer or compute a figure that is not printed. Give each figure a confidence in [0,1] and "
    "the exact source line in 'source_label'.")


@register
class MunsAnnouncementsAdapter(Adapter):
    name = "company_announcements"
    lane = "A"
    store_source = M.SRC_COMPANY
    requires_secret = "MUNS_TOKEN"

    def fetch(self, period):
        from lib.config import tickers_config
        tickers = (tickers_config().get("tickers") or {})
        lookback = int(self.cfg.get("lookback_days", 45))
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback)
        froms, tos = from_d.strftime("%Y%m%d"), to_d.strftime("%Y%m%d")
        client = muns_mod.MunsClient()
        keywords = [k.lower() for k in self.cfg.get("subject_keywords", ["sales"])]

        items = []
        coverage = {}  # oem -> {"resolved": symbol|None, "matches": int}
        for oem, meta in tickers.items():
            if not meta.get("nse") and not meta.get("yf"):
                continue
            anns, used, last_err = None, None, None
            # PER-TICKER ISOLATION: try each candidate symbol; catch EVERY exception so one bad
            # symbol (404 -> HttpError, or 401 -> MunsError) never discards the good tickers.
            for sym in tk.candidates(oem, meta):
                try:
                    anns = client.corp_announcements(sym, froms, tos)
                    used = sym
                    break
                except Exception as e:  # noqa: BLE001 — isolate every per-ticker failure
                    last_err = e
                    self.log.info("  %s: symbol '%s' did not resolve (%s) — trying next",
                                  oem, sym, redact_text(str(e))[:140])
            if anns is None:
                tk.record(oem, None, False, via="corp_announcements", note=redact_text(str(last_err)))
                coverage[oem] = {"resolved": None, "matches": 0}
                self.log.warning("  %s: no candidate symbol resolved — skipping this ticker", oem)
                continue
            tk.record(oem, used, True, via="corp_announcements")

            matched = 0
            for ann in _flatten_announcements(anns):
                subject = _first(ann, ["subject", "headline", "title", "desc", "descriptor"], "")
                if not any(k in str(subject).lower() for k in keywords):
                    continue
                pdf_url = _first(ann, ["attachment", "pdf", "fileUrl", "file_url", "link", "url", "attachmentUrl"])
                if not pdf_url:
                    continue
                matched += 1
                items.append({"oem": oem, "symbol": used, "subject": subject,
                              "pdf_url": pdf_url, "category_hint": meta.get("category", []),
                              "ann_id": _first(ann, ["id", "announcementId", "nsdlId", "seqId"], pdf_url)})
            coverage[oem] = {"resolved": used, "matches": matched}

        resolved = sum(1 for c in coverage.values() if c["resolved"])
        self.log.info("Lane A: resolved %d/%d tickers; %d matching sales announcements",
                      resolved, len(coverage), len(items))
        return {"items": items, "coverage": coverage}

    def extract(self, raw, res):
        minc = min_confidence()
        items = raw.get("items", [])
        coverage = raw.get("coverage", {})
        res.stats["resolution"] = coverage
        for oem, cov in coverage.items():
            if not cov["resolved"]:
                res.flag("ticker_unresolved", f"{oem}: no candidate symbol resolved on Muns")

        # Group announcements by OEM so we can dedupe conflicting filings for the same OEM/month.
        by_oem = defaultdict(list)
        for item in items:
            by_oem[item["oem"]].append(item)

        cap = int(self.cfg.get("max_announcements_per_ticker", 3))
        for oem, its in by_oem.items():
            # Highest-authority filings first (a sales press release beats a production intimation),
            # so on a conflict the more authoritative value is the one we keep.
            its.sort(key=lambda it: _authority(it.get("subject", "")), reverse=True)
            self._extract_one_oem(oem, its[:cap], res, minc)

    def _extract_one_oem(self, oem, items, res, minc):
        """Extract, DEDUPE (one value per category/metric/month, highest-authority wins), then
        VALIDATE arithmetic and store only the rows that reconcile."""
        from lib import fetch as fetch_mod

        acc = {}          # (category, metric, period) -> {value, conf, oem_raw, source_ref}
        company_name = None
        for item in items:
            pdf = fetch_mod.download(item["pdf_url"])
            if not pdf:
                res.flag("fetch_failed", f"{item['symbol']}: could not download {item['pdf_url']}")
                continue
            fname = f"{item['symbol']}_{item['ann_id']}".replace("/", "_")[:80] + ".pdf"
            _, sha = self.save_raw("announcements", fname, pdf, res)
            data, meta = pdf_to_json(pdf, fname, EXTRACT_SCHEMA, INSTRUCTION,
                                     hint=f"Company: {oem}. Likely categories: {item['category_hint']}.")
            if data is None:
                res.flag("extract_failed", f"{item['symbol']}: {meta}")
                continue
            period = _month(data.get("period"))
            if not period:
                res.flag("bad_period", f"{item['symbol']}: could not parse period '{data.get('period')}'")
                continue
            company_name = company_name or data.get("company") or oem
            for row in data.get("rows", []):
                seg = (row.get("segment") or "").strip().lower()
                if seg not in ("", "total", "__all__"):
                    continue  # store only category-level totals — sub-segments are noise here
                cat = (row.get("category") or "").lower()
                if cat not in VALID_CATEGORIES:
                    continue
                conf = float(row.get("confidence", 0))
                if conf < minc:
                    res.flag("low_confidence",
                             f"{item['symbol']} {cat}/{row.get('metric')}={row.get('value')} conf={conf:.2f}")
                    continue
                key = (cat, row.get("metric"), period)
                if key not in acc:  # first (highest-authority) value wins
                    acc[key] = {"value": row.get("value"), "conf": conf,
                                "oem_raw": data.get("company") or oem,
                                "source_ref": f"{item['pdf_url']}#sha={sha[:12]}"}

        if not acc:
            return
        oem_name, mapped = canonical(company_name or oem)
        if not mapped:
            res.flag("unmapped_oem", f"{oem}: '{company_name}' not in alias map (kept, not dropped)")

        # VALIDATE-BEFORE-STORE: per (category, period), require domestic+export≈total. Drop the
        # whole category/month if it doesn't reconcile, so garbled extractions never enter the store.
        dropped = set()
        cats = defaultdict(dict)  # (cat, period) -> {metric: key}
        for key in acc:
            cat, metric, period = key
            cats[(cat, period)][metric] = key
        for (cat, period), metrics in cats.items():
            d = acc[metrics["Domestic"]]["value"] if "Domestic" in metrics else None
            e = acc[metrics["Exports"]]["value"] if "Exports" in metrics else None
            t = acc[metrics["Total"]]["value"] if "Total" in metrics else None
            if d is not None and e is not None and t is not None:
                ok, detail = check_domestic_export_total(d, e, t)
                if not ok:
                    res.flag("arithmetic_dropped",
                             f"{oem} {cat} {period}: {detail} — dropped, not stored")
                    dropped.update(metrics.values())

        stored = 0
        for key, v in acc.items():
            if key in dropped:
                continue
            cat, metric, period = key
            res.records.append(make_record(
                M.SRC_COMPANY, cat, M.SEG_ALL, oem_name, metric, M.FREQ_M, period, v["value"],
                oem_raw=v["oem_raw"], provisional=True, confidence=v["conf"], source_ref=v["source_ref"]))
            stored += 1
        res.stats[oem] = {"stored": stored, "dropped": len(dropped)}


# ---- small tolerant parsers ----------------------------------------------------------

def _as_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "announcements", "results", "items", "filings"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []


def _authority(subject):
    """Rank a filing for how authoritative its SALES totals are (higher = preferred on conflict).
    A monthly-sales press release beats a production intimation beats a generic update."""
    s = str(subject).lower()
    if "sales" in s and ("press release" in s or "provisional" in s):
        return 4
    if "sales" in s:
        return 3
    if "business update" in s:
        return 2
    if "production" in s:
        return 1
    return 2


def _flatten_announcements(anns):
    """
    Muns returns announcements SOURCE-GROUPED, e.g. ``[{"source":"NSE","data":[...]}, ...]``.
    Flatten each group's ``data`` into one list of announcement dicts. Also tolerates an
    already-flat list, or a dict wrapping the list under a ``data``-style key.
    """
    out = []
    for it in _as_list(anns):
        if isinstance(it, dict) and isinstance(it.get("data"), list):
            out.extend(it["data"])      # a {"source": .., "data": [...]} group
        elif isinstance(it, dict):
            out.append(it)              # already a flat announcement
    return out


def _first(d, keys, default=None):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if d.get(k):
            return d[k]
    return default


def _month(s):
    """Coerce a variety of period strings to YYYY-MM."""
    if not s:
        return None
    import re
    s = str(s).strip()
    m = re.match(r"(\d{4})[-/ ](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{1,2})[-/ ](\d{4})", s)
    if m:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    # e.g. "June 2026"
    months = {mn.lower(): i for i, mn in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August",
         "September", "October", "November", "December"], 1)}
    m = re.match(r"([A-Za-z]+)\s+(\d{4})", s)
    if m and m.group(1).lower() in months:
        return f"{int(m.group(2)):04d}-{months[m.group(1).lower()]:02d}"
    return None
