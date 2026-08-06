#!/usr/bin/env python3
"""
lib/http_util.py — one hardened HTTP entry point for every external call.
========================================================================

* Exponential backoff + retry on 429 / 5xx / network errors (rules from the build prompt).
* Verbose, secret-safe logging of endpoint, params, status and a truncated body.
* Raises typed errors so callers can degrade gracefully (a flaky API never aborts the run):
    - ``AuthError``   401/403  -> surfaced in plain English ("expired token")
    - ``HttpError``   other non-2xx after retries
    - ``NetworkError`` connection/timeout after retries
"""

from __future__ import annotations

import time

import requests

from lib.logging_util import get_logger, redact_headers, redact_params, redact_text, truncate

log = get_logger("http")

RETRY_STATUSES = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, status, url, body):
        super().__init__(f"HTTP {status} from {url}: {truncate(body, 300)}")
        self.status = status
        self.url = url
        self.body = body


class AuthError(HttpError):
    """401/403 — usually an expired or missing credential."""


class NetworkError(Exception):
    pass


def request(method, url, *, headers=None, params=None, json_body=None, data=None,
            timeout=60, max_retries=4, backoff_base=2.0, accept=None, label=None):
    """
    Perform an HTTP request with retry/backoff and verbose logging.

    Returns the ``requests.Response`` on 2xx. Raises AuthError/HttpError/NetworkError
    otherwise (after exhausting retries for transient failures).
    """
    headers = dict(headers or {})
    if accept:
        headers["Accept"] = accept
    tag = label or f"{method} {url}"

    attempt = 0
    while True:
        attempt += 1
        log.info("→ %s params=%s headers=%s", tag, redact_params(params), redact_headers(headers))
        try:
            resp = requests.request(method, url, headers=headers, params=params,
                                    json=json_body, data=data, timeout=timeout)
        except requests.RequestException as e:
            if attempt <= max_retries:
                wait = backoff_base ** attempt
                log.warning("  network error (%s) — retry %d/%d in %.0fs", e, attempt, max_retries, wait)
                time.sleep(wait)
                continue
            log.error("  network error (%s) — giving up after %d attempts", e, attempt)
            raise NetworkError(str(e)) from e

        body_preview = truncate(redact_text(resp.text), 1000)
        log.info("← %s status=%s bytes=%d body=%s", tag, resp.status_code,
                 len(resp.content or b""), body_preview)

        if 200 <= resp.status_code < 300:
            return resp

        if resp.status_code in (401, 403):
            raise AuthError(resp.status_code, url, resp.text)

        if resp.status_code in RETRY_STATUSES and attempt <= max_retries:
            wait = backoff_base ** attempt
            log.warning("  status %s — retry %d/%d in %.0fs", resp.status_code, attempt, max_retries, wait)
            time.sleep(wait)
            continue

        raise HttpError(resp.status_code, url, resp.text)


def get(url, **kw):
    return request("GET", url, **kw)


def post(url, **kw):
    return request("POST", url, **kw)
