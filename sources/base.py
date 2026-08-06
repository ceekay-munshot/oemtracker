#!/usr/bin/env python3
"""
sources/base.py — the uniform adapter interface + registry + shared helpers.
===========================================================================

Every lane is an ``Adapter`` exposing ``fetch(period) -> raw`` and ``extract(raw) -> records``.
``run(period)`` wraps them in one try/except so a flaky source can NEVER abort the whole run
(golden rule #4): it returns an ``AdapterResult`` with ``status`` in {ok, skipped, error} and a
plain-English reason. The orchestrator (scripts/run.py) is responsible for storing records,
applying provisional-confirmations, writing overlays and collecting review flags.

Raw artifacts are saved immutably under ``data/raw/<source>/<date>/…`` (the audit trail — lets
us re-extract without re-fetching). Nothing here writes to the canonical store directly.
"""

from __future__ import annotations

import os

from lib import cache
from lib.config import RAW_DIR, has_secret
from lib.logging_util import get_logger
from lib.pipeline_core import slug


class AdapterResult:
    def __init__(self, name, lane):
        self.name = name
        self.lane = lane
        self.status = "ok"          # ok | skipped | error
        self.reason = ""
        self.records = []           # store records (volume lanes)
        self.overlay_name = None    # staging file name under data/out/ (financials/concalls)
        self.overlay = None         # overlay dict
        self.confirms = []          # [{category, periods, by_source}] — provisional->confirmed
        self.flags = []             # review flags for the audit
        self.artifacts = []         # saved raw artifact paths
        self.stats = {}

    def flag(self, ftype, detail, **extra):
        self.flags.append({"lane": self.name, "type": ftype, "detail": detail, **extra})

    def skip(self, reason):
        self.status = "skipped"
        self.reason = reason
        return self

    def error(self, reason):
        self.status = "error"
        self.reason = reason
        return self

    def summary(self):
        return (f"[{self.name}] {self.status}"
                + (f" — {self.reason}" if self.reason else "")
                + f" (records={len(self.records)}, flags={len(self.flags)}, "
                  f"artifacts={len(self.artifacts)})")


class Adapter:
    name = "base"
    lane = "?"
    store_source = None
    requires_secret = None  # env var name required, or None

    def __init__(self, cfg=None, store=None):
        self.cfg = cfg or {}
        self.store = store
        self.log = get_logger(self.name)

    # ---- lifecycle -------------------------------------------------------------------
    def enabled(self):
        return self.cfg.get("enabled", True)

    def credential_ok(self):
        req = self.requires_secret or self.cfg.get("requires_secret")
        if not req:
            return True, None
        if isinstance(req, (list, tuple)):
            ok = any(has_secret(r) for r in req)
            return ok, (None if ok else f"none of {list(req)} set")
        return (has_secret(req), None if has_secret(req) else f"{req} not set")

    def run(self, period=None):
        res = AdapterResult(self.name, self.lane)
        if not self.enabled():
            return res.skip("disabled in config/sources.yaml")
        cred_ok, why = self.credential_ok()
        if not cred_ok:
            self.log.warning("skipped — %s", why)
            return res.skip(f"missing/invalid credential — {why}")
        try:
            raw = self.fetch(period)
            if raw is None:
                return res.skip("no source data available (fetch returned nothing)")
            self.extract(raw, res)
            self.log.info(res.summary())
            return res
        except Exception as e:  # noqa: BLE001 — isolate every lane failure
            self.log.exception("lane errored — keeping last good data, continuing")
            return res.error(f"{type(e).__name__}: {e}")

    # ---- to be implemented by each lane ----------------------------------------------
    def fetch(self, period):
        raise NotImplementedError

    def extract(self, raw, res):
        raise NotImplementedError

    # ---- shared helpers --------------------------------------------------------------
    def save_raw(self, subdir, filename, content, res=None):
        """Persist a fetched artifact immutably under data/raw/<source>/<subdir>/filename."""
        d = os.path.join(RAW_DIR, slug(self.store_source or self.name), subdir)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, filename)
        mode = "wb" if isinstance(content, (bytes, bytearray)) else "w"
        with open(path, mode) as f:
            f.write(content)
        sha = cache.sha256_bytes(content if isinstance(content, (bytes, bytearray))
                                 else content.encode("utf-8"))
        if res is not None:
            res.artifacts.append(path)
        self.log.info("saved raw artifact %s (sha256=%s)", path, sha[:12])
        return path, sha


# ---- registry ------------------------------------------------------------------------
_REGISTRY = {}


def register(cls):
    _REGISTRY[cls.name] = cls
    return cls


def get_adapters():
    return dict(_REGISTRY)
