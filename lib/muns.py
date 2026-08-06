#!/usr/bin/env python3
"""
lib/muns.py — client for the Muns APIs (devde.muns.io + fastapi.muns.io).
========================================================================

All calls send ``Authorization: Bearer $MUNS_TOKEN``. A 401 is surfaced in plain English as
an expired/invalid token. Endpoints implemented (per the build brief):

  * Corporate Announcements  GET  /filings/corp/announcements/{ticker}?fromDate=YYYYMMDD&toDate=YYYYMMDD
  * Combined Filings         POST /filings/combined_filings_announcements   (dates YYYY-MM-DD)
  * Filings — Domestic       POST /filings/domestic
  * Financial Tables (MD)    GET  /filings/financial_tables/markdown/{ticker}?form=consolidated|standalone
  * Get Financials           POST https://fastapi.muns.io/financials/{ticker}   (period annual|quarterly)

Every call logs endpoint + params (token redacted) + status + truncated body via http_util.
Note the two different date formats: announcements use YYYYMMDD, combined filings use YYYY-MM-DD.
"""

from __future__ import annotations

from lib import http_util as http
from lib.config import secret
from lib.logging_util import get_logger

log = get_logger("muns")

DEVDE = "https://devde.muns.io"
FASTAPI = "https://fastapi.muns.io"


class MunsError(Exception):
    pass


class MunsClient:
    def __init__(self, token=None):
        self.token = token or secret("MUNS_TOKEN")
        if not self.token:
            raise MunsError("MUNS_TOKEN is not set — cannot call Muns APIs.")

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    # -- Corporate Announcements (BSE primary, NSE fallback) ---------------------------
    def corp_announcements(self, ticker, from_date, to_date, country="India"):
        """
        from_date/to_date are ``YYYYMMDD`` strings. ``country`` MUST be "India" (capital I) so
        the yfinance-backed resolver picks the Indian listing. Returns the parsed JSON.
        """
        url = f"{DEVDE}/filings/corp/announcements/{ticker}"
        try:
            resp = http.get(url, headers=self._headers,
                            params={"fromDate": from_date, "toDate": to_date, "country": country},
                            accept="application/json",
                            label=f"muns.corp_announcements[{ticker}]")
        except http.AuthError as e:
            raise MunsError(f"401 from Muns — MUNS_TOKEN looks expired/invalid ({e.url}).") from e
        return _json(resp)

    # -- Combined Filings & Announcements ---------------------------------------------
    def combined_filings(self, ticker, forms, start_date, end_date, country="India"):
        """
        forms: e.g. ["concalls"] | ["all"] | ["annual_report"] | ["earnings_report"].
        start_date/end_date are ``YYYY-MM-DD`` strings. Returns parsed JSON (array, newest first).
        """
        url = f"{DEVDE}/filings/combined_filings_announcements"
        body = {"ticker": ticker, "country": country, "form": forms,
                "start_date": start_date, "end_date": end_date}
        try:
            resp = http.post(url, headers=self._headers, json_body=body,
                             accept="application/json",
                             label=f"muns.combined_filings[{ticker},{forms}]")
        except http.AuthError as e:
            raise MunsError(f"401 from Muns — MUNS_TOKEN looks expired/invalid ({e.url}).") from e
        return _json(resp)

    # -- Filings — Domestic ------------------------------------------------------------
    def domestic_filings(self, ticker, form="all", country="India"):
        url = f"{DEVDE}/filings/domestic"
        body = {"ticker": ticker, "form": form, "country": country}
        try:
            resp = http.post(url, headers=self._headers, json_body=body,
                             accept="application/json", label=f"muns.domestic[{ticker},{form}]")
        except http.AuthError as e:
            raise MunsError(f"401 from Muns — MUNS_TOKEN looks expired/invalid ({e.url}).") from e
        return _json(resp)

    # -- Financial Tables (markdown) ---------------------------------------------------
    def financial_tables_markdown(self, ticker, form="consolidated", country="India"):
        url = f"{DEVDE}/filings/financial_tables/markdown/{ticker}"
        try:
            resp = http.get(url, headers=self._headers, params={"form": form, "country": country},
                            accept="text/plain", label=f"muns.financial_tables[{ticker},{form}]")
        except http.AuthError as e:
            raise MunsError(f"401 from Muns — MUNS_TOKEN looks expired/invalid ({e.url}).") from e
        return resp.text

    # -- Get Financials (JSON) ---------------------------------------------------------
    def get_financials(self, ticker, period="quarterly", country="India"):
        url = f"{FASTAPI}/financials/{ticker}"
        try:
            resp = http.post(url, headers=self._headers,
                             json_body={"period": period, "country": country},
                             accept="application/json", label=f"muns.get_financials[{ticker},{period}]")
        except http.AuthError as e:
            raise MunsError(f"401 from Muns — MUNS_TOKEN looks expired/invalid ({e.url}).") from e
        return _json(resp)


def _json(resp):
    try:
        return resp.json()
    except ValueError:
        log.warning("Muns response was not JSON (content-type=%s); returning raw text.",
                    resp.headers.get("content-type"))
        return {"_raw_text": resp.text}
