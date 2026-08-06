#!/usr/bin/env python3
"""
lib/logging_util.py — verbose, secret-safe logging for the whole pipeline.
=========================================================================

Every external call logs its endpoint, params (minus secrets), HTTP status and a truncated
body so failures are diagnosable at a glance (the user pastes these logs to debug the APIs).
Secrets are never printed: tokens, keys and Authorization headers are redacted here.
"""

from __future__ import annotations

import logging
import os
import re
import sys

_CONFIGURED = False

# Substrings that mark an env var / header / query param as secret -> redact its value.
_SECRET_HINTS = ("token", "key", "secret", "password", "authorization", "bearer", "passwd")


def setup(level=None):
    global _CONFIGURED
    if _CONFIGURED:
        return
    lvl = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-22s %(message)s", "%H:%M:%S"))
    root = logging.getLogger("oem")
    root.setLevel(getattr(logging, lvl, logging.INFO))
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name):
    setup()
    return logging.getLogger(f"oem.{name}")


def redact(value):
    """Redact a secret-ish string, keeping only a short fingerprint for correlation."""
    if value is None:
        return None
    s = str(value)
    if len(s) <= 8:
        return "***"
    return f"{s[:4]}…{s[-2:]} (len={len(s)})"


def redact_headers(headers):
    if not headers:
        return {}
    out = {}
    for k, v in headers.items():
        if any(h in k.lower() for h in _SECRET_HINTS):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def redact_params(params):
    if not params:
        return {}
    out = {}
    for k, v in params.items():
        if any(h in str(k).lower() for h in _SECRET_HINTS):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def redact_text(text):
    """Best-effort scrub of bearer tokens / api keys that may appear inside a body/URL."""
    if not text:
        return text
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9\-\._~\+/=]+", r"\1***", text)
    text = re.sub(r"([?&](?:api[_-]?key|token|key|secret)=)[^&\s]+", r"\1***", text, flags=re.I)
    return text


def truncate(text, n=1200):
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    return s if len(s) <= n else s[:n] + f" …[+{len(s) - n} chars]"
