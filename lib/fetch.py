#!/usr/bin/env python3
"""
lib/fetch.py — web fetching with pluggable providers (Firecrawl / Scrape.do / Muns Web Reader).
==============================================================================================

Public pages (SIAM / FADA press releases) are fetched to markdown + link lists so an adapter
can discover the latest release PDF, then ``download`` grabs the PDF bytes for OCR.

Each provider self-skips when its API key is absent; ``fetch_page`` tries them in the order
from config until one succeeds. A plain ``requests`` download is the last-resort for direct
PDF links. Everything is logged (secret-safe) via http_util.
"""

from __future__ import annotations

import re
import urllib.parse

from lib import http_util as http
from lib.config import secret, sources_config
from lib.logging_util import get_logger

log = get_logger("fetch")

FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
SCRAPEDO_URL = "https://api.scrape.do"
# Muns Web Reader — exact schema to be confirmed at build time; kept as a best-effort backup.
MUNS_WEB_READER_URL = "https://devde.muns.io/web/reader"


class FetchResult:
    def __init__(self, url, markdown="", html="", links=None, provider=None, raw=None):
        self.url = url
        self.markdown = markdown
        self.html = html
        self.links = links or []
        self.provider = provider
        self.raw = raw

    def pdf_links(self):
        return [l for l in self.links if str(l).lower().split("?")[0].endswith(".pdf")]


# -- providers -------------------------------------------------------------------------

def _firecrawl(url):
    key = secret("FIRECRAWL_API_KEY")
    if not key:
        log.info("firecrawl: skipped — no FIRECRAWL_API_KEY")
        return None
    resp = http.post(FIRECRAWL_URL, headers={"Authorization": f"Bearer {key}"},
                     json_body={"url": url, "formats": ["markdown", "links"]},
                     accept="application/json", label="firecrawl.scrape")
    data = resp.json().get("data", {})
    return FetchResult(url, markdown=data.get("markdown", ""), html=data.get("html", ""),
                       links=data.get("links", []) or _extract_links(data.get("markdown", "")),
                       provider="firecrawl", raw=data)


def _scrapedo(url):
    key = secret("SCRAPEDO_API_KEY")
    if not key:
        log.info("scrapedo: skipped — no SCRAPEDO_API_KEY")
        return None
    resp = http.get(SCRAPEDO_URL, params={"token": key, "url": url, "render": "true"},
                    label="scrapedo.get")
    html = resp.text
    return FetchResult(url, html=html, links=_extract_links(html), provider="scrapedo", raw=html)


def _muns_web_reader(url):
    token = secret("MUNS_TOKEN")
    if not token:
        log.info("muns_web_reader: skipped — no MUNS_TOKEN")
        return None
    try:
        resp = http.post(MUNS_WEB_READER_URL, headers={"Authorization": f"Bearer {token}"},
                         json_body={"url": url}, accept="application/json",
                         label="muns.web_reader")
    except http.HttpError as e:
        log.warning("muns_web_reader: endpoint returned %s (schema may need confirming) — skipping",
                    getattr(e, "status", "?"))
        return None
    try:
        data = resp.json()
    except ValueError:
        data = {"markdown": resp.text}
    md = data.get("markdown") or data.get("content") or data.get("text") or ""
    return FetchResult(url, markdown=md, links=data.get("links", []) or _extract_links(md),
                       provider="muns_web_reader", raw=data)


_PROVIDERS = {"firecrawl": _firecrawl, "scrapedo": _scrapedo, "muns_web_reader": _muns_web_reader}


def fetch_page(url, providers=None):
    """Fetch a page as markdown+links, trying providers in config order. None if all fail."""
    order = providers or sources_config().get("fetch_providers", list(_PROVIDERS))
    for name in order:
        fn = _PROVIDERS.get(name)
        if not fn:
            continue
        try:
            res = fn(url)
        except http.AuthError:
            log.warning("%s: auth failed — check its API key", name)
            continue
        except Exception as e:  # noqa: BLE001 — a flaky provider must not abort the run
            log.warning("%s: error (%s) — trying next provider", name, e)
            continue
        if res:
            log.info("fetched %s via %s (%d links, %d md-chars)", url, name,
                     len(res.links), len(res.markdown or ""))
            return res
    log.error("all fetch providers failed/absent for %s", url)
    return None


def download(url, timeout=120):
    """Download raw bytes (e.g. a PDF) directly. Returns bytes or None on failure."""
    try:
        resp = http.get(url, timeout=timeout, accept="*/*", label="download")
        return resp.content
    except Exception as e:  # noqa: BLE001
        log.error("download failed for %s: %s", url, e)
        return None


def _extract_links(text):
    if not text:
        return []
    md = re.findall(r"\]\((https?://[^)\s]+)\)", text)
    html = re.findall(r'href=["\'](https?://[^"\']+)["\']', text)
    seen, out = set(), []
    for l in md + html:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out


def absolutize(base, link):
    return urllib.parse.urljoin(base, link)
