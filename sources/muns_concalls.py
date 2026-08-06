#!/usr/bin/env python3
"""
sources/muns_concalls.py — Lane E (Commentary): concall transcript summaries via Muns.
=====================================================================================

For each listed ticker: Combined Filings (form=["concalls"]) -> the latest transcript -> Claude
summary (volume guidance, EV outlook, margin/demand commentary; 3-5 bullets + any quantified
guidance). Keyed by ``oem + quarter``. COMMENTARY ONLY — never mixed into numeric tables.

Output goes to staging ``data/out/_concalls.json`` which ``lib/build.py`` promotes to
``data/out/concalls.json``.
"""

from __future__ import annotations

from datetime import date, timedelta

from lib import fetch as fetch_mod
from lib import model as M
from lib import muns as muns_mod
from lib import ocr as ocr_mod
from lib import tickers as tk
from lib.extract import ExtractionUnavailable
from lib.logging_util import redact_text
from sources._common import get_extractor
from sources.base import Adapter, register

SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "quarter": {"type": ["string", "null"], "description": "e.g. Q1FY27"},
        "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
        "volume_guidance": {"type": ["string", "null"]},
        "ev_outlook": {"type": ["string", "null"]},
        "margin_demand": {"type": ["string", "null"]},
        "quantified_guidance": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["bullets", "confidence"],
}

INSTRUCTION = (
    "Summarize this earnings-call transcript for an Indian automaker. Give 3-5 crisp bullets, "
    "then volume_guidance, ev_outlook and margin_demand commentary, and list any QUANTIFIED "
    "guidance (numbers management gave) in quantified_guidance. Identify the quarter (e.g. "
    "Q1FY27). Do not invent numbers — only quote what is said. Add a confidence.")


@register
class MunsConcallsAdapter(Adapter):
    name = "concalls"
    lane = "E"
    store_source = M.SRC_CONCALLS
    requires_secret = "MUNS_TOKEN"

    def fetch(self, period):
        from lib.config import tickers_config
        tickers = (tickers_config().get("tickers") or {})
        client = muns_mod.MunsClient()
        lookback = int(self.cfg.get("lookback_days", 200))
        end = date.today()
        start = end - timedelta(days=lookback)
        out = []
        for oem, meta in tickers.items():
            items = None
            for sym in tk.candidates(oem, meta):
                try:
                    items = client.combined_filings(sym, ["concalls"],
                                                    start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
                    break
                except Exception as e:  # noqa: BLE001 — isolate every per-ticker failure
                    self.log.info("  %s: symbol '%s' concalls failed (%s) — trying next",
                                  oem, sym, redact_text(str(e))[:140])
            if items is None:
                continue
            items = items if isinstance(items, list) else (items.get("data") if isinstance(items, dict) else [])
            if not items:
                continue
            latest = items[0]  # newest first
            out.append({"oem": oem, "symbol": meta.get("nse") or oem, "item": latest})
        return out or None

    def extract(self, raw, res):
        overlay = {"source": M.SRC_CONCALLS,
                   "note": "Qualitative concall guidance (commentary only — never in numeric tables).",
                   "entries": []}
        extractor = get_extractor()
        for rec in raw:
            text = self._transcript_text(rec, res)
            if not text:
                res.flag("no_transcript", f"{rec['symbol']}: no readable transcript")
                continue
            try:
                summary = extractor.extract(text, SUMMARY_SCHEMA, INSTRUCTION,
                                            hint=f"Company {rec['oem']} ({rec['symbol']})")
            except ExtractionUnavailable as e:
                res.flag("extract_unavailable", f"{rec['symbol']}: {e}")
                continue
            except ValueError as e:
                res.flag("extract_failed", f"{rec['symbol']}: {e}")
                continue
            overlay["entries"].append({
                "oem": rec["oem"], "nse": rec["symbol"],
                "quarter": summary.get("quarter"), "summary": summary})
        res.overlay_name = "_concalls.json"
        res.overlay = overlay
        res.stats = {"entries": len(overlay["entries"])}

    def _transcript_text(self, rec, res):
        item = rec["item"]
        for k in ("transcript", "text", "content", "body"):
            if isinstance(item, dict) and item.get(k):
                return item[k]
        url = None
        if isinstance(item, dict):
            for k in ("attachment", "pdf", "fileUrl", "file_url", "link", "url"):
                if item.get(k):
                    url = item[k]
                    break
        if not url:
            return None
        pdf = fetch_mod.download(url)
        if not pdf:
            return None
        fname = f"{rec['symbol']}_concall.pdf"
        self.save_raw("concalls", fname, pdf, res)
        ocr_res = ocr_mod.ocr_pdf(pdf, filename=fname)
        return ocr_res.get("text") if ocr_res else None
