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

from datetime import date, timedelta

from lib import model as M
from lib import muns as muns_mod
from lib.normalize import (canonical, check_domestic_export_total, month_to_quarter_key)
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
    "stock exchange. Extract every vehicle-sales figure it reports. Map each to a category "
    "(pv, 2w, 3w, mhcv, lcv, tractors, cv) and a metric (Domestic, Exports, Total, Production). "
    "Use 'segment' for any finer split the filing gives (e.g. UV, Scooter); leave it blank if "
    "none. Set 'period' to the sales MONTH as YYYY-MM. Give each figure a confidence in [0,1] "
    "and the exact source line in 'source_label'. Do not compute or infer values that are not "
    "printed; lower confidence instead.")


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
        for oem, meta in tickers.items():
            symbol = meta.get("nse")
            if not symbol:
                continue
            try:
                anns = client.corp_announcements(symbol, froms, tos)
            except muns_mod.MunsError as e:
                self.log.warning("announcements fetch failed for %s: %s", symbol, e)
                continue
            for ann in _as_list(anns):
                subject = _first(ann, ["subject", "headline", "title", "desc", "descriptor"], "")
                if not any(k in str(subject).lower() for k in keywords):
                    continue
                pdf_url = _first(ann, ["attachment", "pdf", "fileUrl", "file_url", "link", "url", "attachmentUrl"])
                if not pdf_url:
                    self.log.info("  %s: matching announcement has no PDF url — skipping", symbol)
                    continue
                items.append({"oem": oem, "symbol": symbol, "subject": subject,
                              "pdf_url": pdf_url, "category_hint": meta.get("category", []),
                              "ann_id": _first(ann, ["id", "announcementId", "nsdlId", "seqId"], pdf_url)})
        self.log.info("Lane A: %d matching sales announcements across %d tickers", len(items), len(tickers))
        return items or None

    def extract(self, raw, res):
        from lib import fetch as fetch_mod
        minc = min_confidence()
        for item in raw:
            pdf = fetch_mod.download(item["pdf_url"])
            if not pdf:
                res.flag("fetch_failed", f"{item['symbol']}: could not download {item['pdf_url']}")
                continue
            fname = f"{item['symbol']}_{item['ann_id']}".replace("/", "_")[:80] + ".pdf"
            _, sha = self.save_raw("announcements", fname, pdf, res)
            data, meta = pdf_to_json(pdf, fname, EXTRACT_SCHEMA, INSTRUCTION,
                                     hint=f"Company: {item['oem']}. Likely categories: {item['category_hint']}.")
            if data is None:
                res.flag("extract_failed", f"{item['symbol']}: {meta}")
                continue
            self._rows_to_records(item, data, meta, sha, res, minc)

    def _rows_to_records(self, item, data, meta, sha, res, minc):
        period = _month(data.get("period"))
        if not period:
            res.flag("bad_period", f"{item['symbol']}: could not parse period '{data.get('period')}'")
            return
        oem_name, mapped = canonical(data.get("company") or item["oem"])
        if not mapped:
            res.flag("unmapped_oem", f"{item['symbol']}: '{data.get('company')}' not in alias map")

        # collect for arithmetic validation per category
        by_cat = {}
        for row in data.get("rows", []):
            cat = (row.get("category") or "").lower()
            if cat not in VALID_CATEGORIES:
                continue
            conf = float(row.get("confidence", 0))
            if conf < minc:
                res.flag("low_confidence",
                         f"{item['symbol']} {cat}/{row.get('metric')}={row.get('value')} conf={conf:.2f}",
                         value=row.get("value"))
                continue
            metric = row.get("metric")
            val = row.get("value")
            seg = row.get("segment") or M.SEG_ALL
            by_cat.setdefault(cat, {}).setdefault(metric, val if seg == M.SEG_ALL else None)
            res.records.append(make_record(
                M.SRC_COMPANY, cat, seg, oem_name, metric, M.FREQ_M, period, val,
                oem_raw=data.get("company") or item["oem"], provisional=True,
                confidence=conf, source_ref=f"{item['pdf_url']}#sha={sha[:12]}"))

        # arithmetic sanity: domestic+export≈total per category (report-only; keep lanes intact)
        for cat, mm in by_cat.items():
            ok, detail = check_domestic_export_total(mm.get("Domestic"), mm.get("Exports"), mm.get("Total"))
            if not ok:
                res.flag("arithmetic", f"{item['symbol']} {cat}: {detail}")

        res.stats[item["symbol"]] = {"period": period, "rows": len(data.get("rows", []))}


# ---- small tolerant parsers ----------------------------------------------------------

def _as_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("data", "announcements", "results", "items", "filings"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []


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
