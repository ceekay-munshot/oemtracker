#!/usr/bin/env python3
"""
sources/siam.py — Lane B (Backbone): the SIAM monthly release.
=============================================================

SIAM is the PRIMARY source for the core trend & market-share tables: it covers all OEMs plus
industry totals. Flow:
  1. Fetch the SIAM press-release page (Firecrawl/Scrape.do/Muns Web Reader) and find the
     latest monthly-data PDF. If per-OEM detail is member-only AND SIAM_USERNAME/PASSWORD are
     set, use the Playwright login path (kept behind a clearly-logged flag).
  2. OCR -> Claude -> per-OEM × category Production/Domestic/Exports/Total + industry totals.
  3. Store as ``source="SIAM"`` (provisional=False — the backbone confirms the month). Market
     share is recomputed later in the build from Total sales — never trusted from the file.

When SIAM confirms a month, the orchestrator flips the earlier Company(flash) rows for that
month to provisional=False (revision bump).
"""

from __future__ import annotations

from lib import fetch as fetch_mod
from lib import model as M
from lib.normalize import canonical
from lib.store import make_record
from sources._common import min_confidence, pdf_to_json
from sources.base import Adapter, register

SIAM_CATEGORIES = {"pv", "2w", "3w", "mhcv", "lcv"}

EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "period": {"type": "string", "description": "The data month, YYYY-MM."},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string", "enum": sorted(SIAM_CATEGORIES)},
                    "oem": {"type": "string",
                            "description": "OEM/manufacturer name exactly as printed, or 'Industry' for the total."},
                    "metric": {"type": "string",
                               "enum": ["Production", "Domestic", "Exports", "Total"]},
                    "value": {"type": "number"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_label": {"type": "string"},
                },
                "required": ["category", "oem", "metric", "value", "confidence"],
            },
        },
    },
    "required": ["period", "rows"],
}

INSTRUCTION = (
    "This is a SIAM (Society of Indian Automobile Manufacturers) monthly data release. Extract "
    "every manufacturer-wise figure for Production, Domestic sales, Exports and Total sales, "
    "across Passenger Vehicles (pv), Two-Wheelers (2w), Three-Wheelers (3w), M&HCV (mhcv) and "
    "LCV (lcv). Use oem='Industry' for the industry total rows. Set 'period' to the data MONTH "
    "as YYYY-MM. Every figure needs a confidence in [0,1] and its source line. Do NOT copy any "
    "pre-computed market-share block — only raw counts. Never infer a missing number.")


@register
class SiamAdapter(Adapter):
    name = "siam"
    lane = "B"
    store_source = M.SRC_SIAM
    requires_secret = None  # public path needs no secret; scraping keys are optional

    def fetch(self, period):
        # Member-only detail via Playwright login (optional, flag-gated).
        from lib.config import secret
        if self.cfg.get("member_only_detail") and secret("SIAM_USERNAME") and secret("SIAM_PASSWORD"):
            pdf = self._fetch_member_pdf()
            if pdf:
                return pdf

        press_url = self.cfg.get("press_url")
        if not press_url:
            self.log.warning("no press_url configured for SIAM — cannot fetch public release")
            return None
        page = fetch_mod.fetch_page(press_url)
        if not page:
            self.log.warning("SIAM press page fetch failed (no scraping provider available)")
            return None
        pdfs = page.pdf_links()
        if not pdfs:
            self.log.warning("no PDF links found on SIAM press page — schema/scrape may need tuning")
            return None
        pdf_url = fetch_mod.absolutize(press_url, pdfs[0])  # newest first, best-effort
        self.log.info("SIAM: chosen release PDF %s", pdf_url)
        data = fetch_mod.download(pdf_url)
        if not data:
            return None
        fname = pdf_url.rsplit("/", 1)[-1].split("?")[0] or "siam_release.pdf"
        _, sha = self.save_raw("release", fname, data)
        return {"pdf": data, "filename": fname, "url": pdf_url, "sha": sha}

    def _fetch_member_pdf(self):
        """Member-only per-OEM detail via Playwright login — behind a clearly-logged flag."""
        self.log.info("SIAM member login path enabled (SIAM_USERNAME/PASSWORD present).")
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError:
            self.log.warning("Playwright not installed — cannot use SIAM member login; "
                             "falling back to public path. (pip install playwright)")
            return None
        from lib.config import secret
        login_url = self.cfg.get("member_login_url")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                pg = browser.new_page()
                self.log.info("SIAM: navigating to member login %s", login_url)
                pg.goto(login_url, timeout=60000)
                # NOTE: selectors are best-effort and will need confirming against the live page.
                pg.fill("input[type=text], input[name*=user i]", secret("SIAM_USERNAME"))
                pg.fill("input[type=password]", secret("SIAM_PASSWORD"))
                pg.click("button[type=submit], input[type=submit]")
                pg.wait_for_load_state("networkidle", timeout=60000)
                self.log.warning("SIAM member area reached, but the download selector must be "
                                 "confirmed against the live portal — returning None for now.")
                browser.close()
        except Exception as e:  # noqa: BLE001
            self.log.warning("SIAM member login path failed (%s) — falling back to public path", e)
        return None

    def extract(self, raw, res):
        minc = min_confidence()
        data, meta = pdf_to_json(raw["pdf"], raw["filename"], EXTRACT_SCHEMA, INSTRUCTION,
                                 hint="SIAM monthly release; expect all OEMs across pv/2w/3w/mhcv/lcv.")
        if data is None:
            res.flag("extract_failed", str(meta))
            res.error(f"SIAM extraction failed: {meta}")
            return
        period = data.get("period")
        if not period or len(period) != 7:
            res.flag("bad_period", f"SIAM period '{period}' unparseable")
            return

        covered = set()
        for row in data.get("rows", []):
            cat = (row.get("category") or "").lower()
            if cat not in SIAM_CATEGORIES:
                continue
            conf = float(row.get("confidence", 0))
            if conf < minc:
                res.flag("low_confidence",
                         f"SIAM {cat}/{row.get('oem')}/{row.get('metric')} conf={conf:.2f}")
                continue
            oem_raw = row.get("oem") or ""
            if oem_raw.strip().lower() == "industry":
                oem = M.OEM_INDUSTRY
            else:
                oem, mapped = canonical(oem_raw)
                if not mapped:
                    res.flag("unmapped_oem", f"SIAM: '{oem_raw}' not in alias map (kept, not dropped)")
                    oem = oem_raw
            res.records.append(make_record(
                M.SRC_SIAM, cat, M.SEG_ALL, oem, row["metric"], M.FREQ_M, period, row["value"],
                oem_raw=oem_raw or oem, provisional=False, confidence=conf,
                source_ref=f"{raw['url']}#sha={raw['sha'][:12]}"))
            covered.add(cat)

        # SIAM confirms this month -> flip Company(flash) rows for it to provisional=False.
        for cat in covered:
            res.confirms.append({"category": cat, "periods": [period], "by_source": M.SRC_SIAM})
        res.stats = {"period": period, "categories": sorted(covered), "rows": len(data.get("rows", []))}
