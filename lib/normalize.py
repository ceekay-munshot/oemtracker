#!/usr/bin/env python3
"""
lib/normalize.py — canonical OEM names, fiscal calendar, market share, arithmetic checks.
========================================================================================

* ``canonical(name)`` maps a live source's OEM string onto a stable canonical identity via
  ``config/oem_aliases.yaml`` (case/punctuation-insensitive). Unmapped names are returned
  unchanged and flagged so the audit can surface them — never silently dropped.
* Fiscal helpers (Apr-Mar) reuse ``pipeline_core``.
* ``market_share`` recomputes share from the single backbone source's totals (sums ~100%).
* ``check_*`` implement the arithmetic sanity gates (domestic+export≈total, segment sums).
"""

from __future__ import annotations

import re

from lib import pipeline_core as pc
from lib.config import aliases_config
from lib.logging_util import get_logger

log = get_logger("normalize")


def _norm_key(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


class AliasMap:
    def __init__(self, cfg=None):
        cfg = cfg if cfg is not None else aliases_config()
        self._map = {}
        for canonical, aliases in (cfg.get("aliases") or {}).items():
            self._map[_norm_key(canonical)] = canonical
            for a in (aliases or []):
                self._map[_norm_key(a)] = canonical

    def canonical(self, name):
        """Return (canonical_name, is_mapped). Unmapped -> (name, False)."""
        hit = self._map.get(_norm_key(name))
        if hit:
            return hit, True
        return name, False


_DEFAULT_ALIAS = None


def canonical(name):
    global _DEFAULT_ALIAS
    if _DEFAULT_ALIAS is None:
        _DEFAULT_ALIAS = AliasMap()
    return _DEFAULT_ALIAS.canonical(name)


# -- fiscal calendar -------------------------------------------------------------------

def month_to_quarter_key(period):
    """'2026-06' -> 'Q1FY27'."""
    dt = pc.month_dt(period)
    return pc.quarter_key(pc.fy_of(dt), pc.fq_of(dt))


def month_to_year_key(period):
    """'2026-06' -> 'FY27'."""
    dt = pc.month_dt(period)
    return pc.year_key(pc.fy_of(dt))


# -- market share (recomputed from a single source's totals) ---------------------------

def market_share(totals_by_oem, industry_total=None):
    """
    totals_by_oem: {oem: total_value}. Returns {oem: share_pct}. Never trusts a pre-computed
    share block.

    When ``industry_total`` (the independent SIAM ``__industry__`` total) is given it is used as
    the denominator, so the shares are NOT a tautology: if some OEMs are missing, the parts no
    longer sum to 100 and that gap is real signal (see the audit's share check). Without an
    industry total it falls back to the sum of the present parts.
    """
    parts = sum(v for v in totals_by_oem.values() if v)
    denom = industry_total if industry_total else parts
    if not denom:
        return {}
    return {oem: (100.0 * v / denom) for oem, v in totals_by_oem.items() if v}


# -- arithmetic sanity gates -----------------------------------------------------------

def approx_equal(a, b, *, rel=0.02, abs_tol=5):
    if a is None or b is None:
        return True  # missing side can't be checked; not a failure
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))


def check_domestic_export_total(domestic, export, total, *, rel=0.02):
    """domestic + export ≈ total. Returns (ok, detail)."""
    if domestic is None or export is None or total is None:
        return True, "one of domestic/export/total missing — not checked"
    lhs = domestic + export
    ok = approx_equal(lhs, total, rel=rel)
    return ok, f"domestic({domestic})+export({export})={lhs} vs total({total})"


def check_segment_sum(parts, total, *, rel=0.03):
    """sum(parts) ≈ total. Returns (ok, detail)."""
    parts = [p for p in parts if p is not None]
    if not parts or total is None:
        return True, "parts/total missing — not checked"
    s = sum(parts)
    ok = approx_equal(s, total, rel=rel)
    return ok, f"segment sum({s}) vs total({total})"
