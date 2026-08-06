#!/usr/bin/env python3
"""
sources/muns_financials.py — Lane D: financials overlay via Muns (kept out of the volume lanes).
==============================================================================================

For each listed ticker: pull Financial Tables (markdown) + Get Financials (JSON) and distill a
compact overlay — revenue, EBITDA margin, PAT, a few key ratios and the latest valuation. This
is an OVERLAY only (``source="Muns-Financials"``); it never mixes with the volume tables.

Output goes to the staging file ``data/out/_financials.json`` which ``lib/build.py`` promotes to
``data/out/financials.json``.
"""

from __future__ import annotations

from lib import model as M
from lib import muns as muns_mod
from lib.extract import ExtractionUnavailable
from sources._common import get_extractor
from sources.base import Adapter, register

OVERLAY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "revenue": {"type": ["number", "null"]},
        "ebitda_margin_pct": {"type": ["number", "null"]},
        "pat": {"type": ["number", "null"]},
        "period_label": {"type": ["string", "null"]},
        "key_ratios": {"type": "object"},
        "valuation": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["confidence"],
}

INSTRUCTION = (
    "From these company financial tables, extract the latest-period headline financials: "
    "revenue, EBITDA margin (%), PAT, the reporting period label, a few key ratios "
    "(e.g. ROE, ROCE, debt/equity, P/E) in key_ratios, and any latest valuation figures "
    "(market cap, EV) in valuation. Use null where a figure is not present. Add a confidence.")


@register
class MunsFinancialsAdapter(Adapter):
    name = "financials"
    lane = "D"
    store_source = M.SRC_FINANCIALS
    requires_secret = "MUNS_TOKEN"

    def fetch(self, period):
        from lib.config import tickers_config
        tickers = (tickers_config().get("tickers") or {})
        client = muns_mod.MunsClient()
        form = self.cfg.get("form", "consolidated")
        per = self.cfg.get("period", "quarterly")
        out = {}
        for oem, meta in tickers.items():
            symbol = meta.get("nse")
            if not symbol:
                continue
            entry = {"oem": oem, "nse": symbol}
            try:
                entry["tables_markdown"] = client.financial_tables_markdown(symbol, form)
            except muns_mod.MunsError as e:
                self.log.warning("financial_tables failed for %s: %s", symbol, e)
                entry["tables_markdown"] = None
            try:
                entry["financials"] = client.get_financials(symbol, per)
            except muns_mod.MunsError as e:
                self.log.warning("get_financials failed for %s: %s", symbol, e)
                entry["financials"] = None
            if entry["tables_markdown"] or entry["financials"]:
                out[symbol] = entry
        return out or None

    def extract(self, raw, res):
        overlay = {"source": M.SRC_FINANCIALS,
                   "note": "Revenue / margin / valuation overlay by ticker (separate lane).",
                   "tickers": {}}
        extractor = get_extractor()
        for symbol, entry in raw.items():
            self.save_raw("financials", f"{symbol}.md",
                          entry.get("tables_markdown") or "", res)
            headline = None
            md = entry.get("tables_markdown")
            if md:
                try:
                    headline = extractor.extract(md, OVERLAY_SCHEMA, INSTRUCTION,
                                                 hint=f"Ticker {symbol}")
                except ExtractionUnavailable as e:
                    res.flag("extract_unavailable", f"{symbol}: {e}")
                except ValueError as e:
                    res.flag("extract_failed", f"{symbol}: {e}")
            overlay["tickers"][symbol] = {
                "oem": entry["oem"],
                "headline": headline,
                "financials": entry.get("financials"),
            }
        res.overlay_name = "_financials.json"
        res.overlay = overlay
        res.stats = {"tickers": len(overlay["tickers"])}
