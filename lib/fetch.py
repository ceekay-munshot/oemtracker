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

import requests

from lib import http_util as http
from lib.config import secret, sources_config
from lib.logging_util import get_logger, redact_text

log = get_logger("fetch")

# Many sources (notably NSE archives) reject non-browser clients — the request just hangs until
# it read-times-out. Send browser-like headers so downloads actually return.
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept": "application/pdf,application/octet-stream,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
_nse_session = None

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
                     json_body={"url": url, "formats": ["markdown", "links", "html"]},
                     accept="application/json", label="firecrawl.scrape")
    data = resp.json().get("data", {})
    md, html = data.get("markdown", ""), data.get("html", "")
    # Combine every link source — some listing pages (FADA) put the PDF only in the HTML, as a
    # relative href with spaces that the markdown/links views miss.
    links = _merge_links(data.get("links", []), _extract_links(md), _extract_links(html))
    return FetchResult(url, markdown=md, html=html, links=links, provider="firecrawl", raw=data)


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
            log.warning("%s: error (%s) — trying next provider", name, redact_text(str(e)))
            continue
        if res:
            log.info("fetched %s via %s (%d links, %d md-chars)", url, name,
                     len(res.links), len(res.markdown or ""))
            return res
    log.error("all fetch providers failed/absent for %s", url)
    return None


def _nse_download(url, timeout, attempts=2):
    """
    NSE (nseindia.com / nsearchives) blocks non-browser clients and needs cookies from the main
    site. Prime a session once, then fetch the archive with a browser UA + Referer. Kept fast
    (short timeout, few attempts) so a still-blocked host fails in seconds, not minutes.
    """
    global _nse_session
    if _nse_session is None:
        s = requests.Session()
        s.headers.update(BROWSER_HEADERS)
        try:
            s.get("https://www.nseindia.com/", timeout=15)  # sets the cookies NSE requires
        except requests.RequestException as e:
            log.info("NSE cookie priming failed (%s) — proceeding without", redact_text(str(e)))
        _nse_session = s
    last = None
    for i in range(attempts):
        try:
            resp = _nse_session.get(url, headers={"Referer": "https://www.nseindia.com/"},
                                    timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            last = e
            log.info("  NSE download attempt %d/%d failed (%s)", i + 1, attempts,
                     redact_text(str(e))[:120])
    raise last


def _scrapedo_download(url, timeout):
    """Proxy fallback: fetch bytes via Scrape.do (rotating IPs) when a host bot-blocks the runner."""
    key = secret("SCRAPEDO_API_KEY")
    if not key:
        return None
    resp = http.get(SCRAPEDO_URL, params={"token": key, "url": url}, timeout=timeout,
                    max_retries=1, accept="*/*", label="scrapedo.download")
    return resp.content


def download(url, timeout=45, max_retries=1):
    """
    Download raw bytes (e.g. a PDF). Sends browser-like headers because sources such as NSE
    archives reject non-browser clients (the connection hangs until read-timeout). Short timeout
    + few retries so a blocked host fails FAST instead of grinding through minutes of retries.
    If the direct fetch fails (or a host bot-blocks the runner IP), falls back to the Scrape.do
    proxy. Returns bytes, or None on failure (the caller flags it and continues).
    """
    url = url.replace(" ", "%20")   # FADA (and other) PDF filenames contain spaces
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    try:
        if host.endswith("nseindia.com"):
            log.info("→ download[nse] %s", redact_text(url))
            data = _nse_download(url, timeout)
            log.info("← download[nse] %d bytes", len(data or b""))
            return data
        resp = http.get(url, headers=dict(BROWSER_HEADERS), timeout=timeout,
                        max_retries=max_retries, label="download")
        return resp.content
    except Exception as e:  # noqa: BLE001
        log.warning("direct download failed for %s: %s — trying Scrape.do proxy",
                    redact_text(url), redact_text(str(e))[:120])
    try:
        data = _scrapedo_download(url, timeout)
        if data:
            log.info("← download[scrapedo] %d bytes", len(data))
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("proxy download also failed for %s: %s", redact_text(url), redact_text(str(e))[:120])
        return None


def _extract_links(text):
    """Pull links from markdown OR html — absolute or relative, INCLUDING ones with spaces
    (FADA's PDF filenames contain spaces). Callers absolutize + space-encode before fetching."""
    if not text:
        return []
    found = []
    found += re.findall(r"\]\(\s*([^)]+?\.pdf[^)]*)\)", text, re.I)   # markdown links to a .pdf (allows spaces)
    found += re.findall(r"\]\((https?://[^)\s]+)\)", text)             # any other absolute markdown link
    found += re.findall(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', text, re.I)  # any html href/src (rel/abs/spaces)
    seen, out = set(), []
    for l in (x.strip() for x in found):
        if l and l not in seen:
            seen.add(l)
            out.append(l)
    return out


def _merge_links(*lists):
    seen, out = set(), []
    for lst in lists:
        for l in (lst or []):
            l = str(l).strip()
            if l and l not in seen:
                seen.add(l)
                out.append(l)
    return out


def absolutize(base, link):
    return urllib.parse.urljoin(base, link)
