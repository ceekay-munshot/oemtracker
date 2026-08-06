#!/usr/bin/env python3
"""
sources/fada.py — Lane C (Retail): FADA monthly retail-registration press release.
=================================================================================

FADA reports RETAIL registrations (a different definition from SIAM wholesale) — so it lives in
its own lane and is never blended with SIAM (golden rule #3). Flow: fetch the FADA press page
-> latest release PDF -> OCR -> Claude -> category + top-OEM retail. Stored as ``source="FADA"``
with metric ``Retail``.
"""

from __future__ import annotations

import re

from lib import fetch as fetch_mod
from lib import model as M
from lib.normalize import canonical
from lib.store import make_record
from sources._common import min_confidence, pdf_to_json
from sources.base import Adapter, register

FADA_CATEGORIES = {"pv", "2w", "3w", "cv", "tractors", "mhcv", "lcv"}

EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "period": {"type": "string", "description": "The retail month, YYYY-MM."},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "enum": sorted(FADA_CATEGORIES)},
                    "oem": {"type": "string",
                            "description": "OEM name as printed, or 'Total' for the category total."},
                    "value": {"type": "number", "description": "Retail registrations (units)."},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_label": {"type": "string"},
                },
                "required": ["category", "oem", "value", "confidence"],
            },
        },
    },
    "required": ["period", "rows"],
}

INSTRUCTION = (
    "This is a FADA monthly RETAIL registration press release for India. Extract retail "
    "registration counts by category (pv, 2w, 3w, cv, tractors) and, where given, by OEM. "
    "Use oem='Total' for a category total. Set 'period' to the retail MONTH as YYYY-MM. Each "
    "figure needs a confidence and its source line. These are RETAIL (not wholesale) numbers.")


@register
class FadaAdapter(Adapter):
    name = "fada"
    lane = "C"
    store_source = M.SRC_FADA
    requires_secret = None

    def fetch(self, period):
        press_urls = self.cfg.get("press_urls") or ([self.cfg["press_url"]] if self.cfg.get("press_url") else [])
        if not press_urls:
            return None
        pdf_url = None
        for purl in press_urls:
            page = fetch_mod.fetch_page(purl)
            if not page:
                continue
            pdfs = page.pdf_links()
            if pdfs:
                pdf_url = fetch_mod.absolutize(purl, pdfs[0])  # newest first, best-effort
                break
        if not pdf_url:
            self.log.warning("no PDF links on FADA press page(s) — scrape/URL may need tuning")
            return None
        data = fetch_mod.download(pdf_url)
        if not data:
            return None
        fname = pdf_url.rsplit("/", 1)[-1].split("?")[0] or "fada_release.pdf"
        _, sha = self.save_raw("release", fname, data)
        return {"pdf": data, "filename": fname, "url": pdf_url, "sha": sha}

    def extract(self, raw, res):
        minc = min_confidence()
        data, meta = pdf_to_json(raw["pdf"], raw["filename"], EXTRACT_SCHEMA, INSTRUCTION,
                                 hint="FADA retail registrations by category and OEM.")
        if data is None:
            res.flag("extract_failed", str(meta))
            return
        period = data.get("period")
        if not period or not re.match(r"^\d{4}-\d{2}$", str(period)):
            res.flag("bad_period", f"FADA period '{period}' not YYYY-MM")
            return
        for row in data.get("rows", []):
            cat = (row.get("category") or "").lower()
            if cat not in FADA_CATEGORIES:
                continue
            conf = float(row.get("confidence", 0))
            if conf < minc:
                res.flag("low_confidence", f"FADA {cat}/{row.get('oem')} conf={conf:.2f}")
                continue
            oem_raw = row.get("oem") or ""
            if oem_raw.strip().lower() in ("total", "industry"):
                oem = M.OEM_INDUSTRY
            else:
                oem, mapped = canonical(oem_raw)
                if not mapped:
                    res.flag("unmapped_oem", f"FADA: '{oem_raw}' not in alias map (kept)")
                    oem = oem_raw
            res.records.append(make_record(
                M.SRC_FADA, cat, M.SEG_ALL, oem, M.METRIC_RETAIL, M.FREQ_M, period, row["value"],
                oem_raw=oem_raw or oem, provisional=True, confidence=conf,
                source_ref=f"{raw['url']}#sha={raw['sha'][:12]}"))
        res.stats = {"period": period, "rows": len(data.get("rows", []))}
