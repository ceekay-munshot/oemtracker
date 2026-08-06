#!/usr/bin/env python3
"""
lib/cache.py — content-addressed cache (sha256) so we never re-pay for an unchanged input.
=========================================================================================

OCR and LLM results are cached by the sha256 of their input. Re-running a month only
processes genuinely NEW artifacts; unchanged PDFs / prompts are served from cache for free.
"""

from __future__ import annotations

import hashlib
import json
import os

from lib.config import CACHE_DIR
from lib.logging_util import get_logger

log = get_logger("cache")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _path(namespace, key):
    d = os.path.join(CACHE_DIR, namespace)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.json")


def get(namespace, key):
    p = _path(namespace, key)
    if os.path.exists(p):
        try:
            with open(p) as f:
                log.info("cache HIT  %s/%s", namespace, key[:12])
                return json.load(f)
        except Exception:
            return None
    log.info("cache MISS %s/%s", namespace, key[:12])
    return None


def put(namespace, key, value):
    p = _path(namespace, key)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(value, f)
    os.replace(tmp, p)
    return value
