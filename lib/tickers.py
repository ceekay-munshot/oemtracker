#!/usr/bin/env python3
"""
lib/tickers.py — resolve OEM tickers to the symbol Muns/yfinance actually accepts.
=================================================================================

The Muns backend resolves tickers via yfinance. Two gotchas the data team flagged:
  * calls must pass ``country:"India"`` (capital I) — lowercase errors, and without it a bare
    symbol can resolve to the wrong listing (e.g. RELIANCE -> US "RS" on NYSE);
  * the bare NSE symbol is not always the yfinance symbol — ``MARUTI`` resolves but
    ``TATAMOTORS`` does not (yfinance wants ``TATAMOTORS.NS``).

So instead of trusting one hard-coded symbol we probe candidate formats (bare, then ``.NS``,
plus an optional explicit ``yf`` override in config) and keep whichever actually resolves. The
outcome is cached in ``data/out/ticker_resolution.json`` (committed) so later runs skip probing
and we have a per-ticker coverage record. ``scripts/resolve_tickers.py`` is the one-shot probe.
"""

from __future__ import annotations

import json
import os

from lib.config import OUT_DIR
from lib.logging_util import get_logger

log = get_logger("tickers")

RESOLUTION_PATH = os.path.join(OUT_DIR, "ticker_resolution.json")

_cache = None  # {oem: {"symbol": str|None, "via": str, "ok": bool, "note": str}}


def symbol_candidates(meta):
    """Candidate symbols to try, in order: explicit yf override, bare NSE, then '<NSE>.NS'."""
    nse = meta.get("nse")
    out = []
    for c in (meta.get("yf"), nse, f"{nse}.NS" if nse else None):
        if c and c not in out:
            out.append(c)
    return out


def _load():
    global _cache
    if _cache is None:
        if os.path.exists(RESOLUTION_PATH):
            try:
                with open(RESOLUTION_PATH) as f:
                    _cache = json.load(f)
            except Exception:
                _cache = {}
        else:
            _cache = {}
    return _cache


def candidates(oem, meta):
    """Return candidates to try — a previously-resolved symbol first (with fallbacks behind it)."""
    _load()
    base = symbol_candidates(meta)
    hit = _cache.get(oem)
    if hit and hit.get("ok") and hit.get("symbol"):
        return [hit["symbol"]] + [c for c in base if c != hit["symbol"]]
    return base


def record(oem, symbol, ok, *, via="", note=""):
    """Persist a resolution outcome. A transient failure never downgrades a known-good symbol."""
    _load()
    prev = _cache.get(oem)
    if not ok and prev and prev.get("ok"):
        return
    _cache[oem] = {"symbol": symbol, "via": via, "ok": bool(ok), "note": note[:160]}
    _save()


def coverage():
    _load()
    return dict(_cache)


def _save():
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = RESOLUTION_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_cache, f, indent=2, sort_keys=True)
    os.replace(tmp, RESOLUTION_PATH)
