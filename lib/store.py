#!/usr/bin/env python3
"""
lib/store.py — the canonical, append-only, long-format data store.
==================================================================

Everything the pipeline learns lands here first, as one **immutable record per figure**.
The dashboard JSON in ``data/`` is *derived* from this store (see ``lib/build.py``); the
store itself is the single source of truth and the audit trail.

Golden rules enforced here:
  * **Append-only history — never overwrite.** New months are appended. Past records are
    never mutated in place. A restatement (a changed value, or a provisional→confirmed
    flip) is written as a NEW record with ``revision = prev + 1``; the dashboard build takes
    the highest revision per key ("latest wins"). Nothing is ever lost.
  * **Idempotent upsert.** Re-running the same month/seed appends nothing — a record whose
    payload signature ``(value, provisional)`` already matches the latest revision is skipped.
  * **One source per record.** ``source`` is part of the natural key, so SIAM, FADA,
    Company(BSE/NSE), Muns-Financials and Internal-DB(historical) never collide or blend.

Natural (upsert) key:  ``(source, category, segment, oem, metric, frequency, period)``

On-disk layout (all git-committable, diff-friendly plain text):
  data/store/<source_slug>.jsonl   one JSON record per line, append-only
  data/store/_axis.json            explicit ordered period axis per (source, category, freq)
  data/store/_stats.json           lightweight summary (record counts) refreshed on write

Records are stored *lean*: fields equal to their default are omitted and re-filled on read
(``unit="units"``, ``oem_raw=oem``, ``confidence=1.0``, ``revision=0``, ``provisional=False``).
Values are stored as ``int`` when integral. This keeps a 34-year monthly OEM history compact.
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict, defaultdict

from lib.pipeline_core import slug

# Fields that make up the natural key (idempotent upsert key).
KEY_FIELDS = ("source", "category", "segment", "oem", "metric", "frequency", "period")

# Per-record defaults; a field equal to its default is omitted on disk and re-filled on load.
DEFAULTS = {
    "unit": "units",
    "confidence": 1.0,
    "revision": 0,
    "provisional": False,
    "source_ref": None,
    "ingested_at": None,
}


def _compact_value(v):
    """Store integral numbers as int (compact + readable); pass floats / None through."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        if f.is_integer():
            return int(f)
        return f
    return v


def _record_key(rec):
    return tuple(rec[f] for f in KEY_FIELDS)


def _signature(rec):
    """Payload signature used to detect restatements. A change here => new revision."""
    val = rec.get("value")
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    return (val, bool(rec.get("provisional", False)))


def make_record(source, category, segment, oem, metric, frequency, period, value,
                *, oem_raw=None, unit="units", provisional=False, confidence=1.0,
                source_ref=None, ingested_at=None):
    """Construct a full (defaults-filled) record dict. ``revision`` is assigned by the store."""
    return {
        "source": source,
        "category": category,
        "segment": segment,
        "oem": oem,
        "oem_raw": oem_raw if oem_raw is not None else oem,
        "metric": metric,
        "frequency": frequency,
        "period": period,
        "value": _compact_value(value),
        "unit": unit,
        "revision": 0,
        "provisional": bool(provisional),
        "confidence": confidence,
        "source_ref": source_ref,
        "ingested_at": ingested_at,
    }


def _to_disk(rec):
    """Lean serialisation: drop fields equal to their default; default oem_raw==oem."""
    out = {}
    for f in KEY_FIELDS:
        out[f] = rec[f]
    out["value"] = _compact_value(rec.get("value"))
    if rec.get("oem_raw") not in (None, rec["oem"]):
        out["oem_raw"] = rec["oem_raw"]
    for f, dflt in DEFAULTS.items():
        v = rec.get(f, dflt)
        if f == "confidence":
            if v is not None and abs(float(v) - 1.0) < 1e-9:
                continue
        if v != dflt and v is not None:
            out[f] = v
    return out


def _from_disk(obj):
    """Re-fill defaults dropped by _to_disk."""
    rec = dict(obj)
    if "oem_raw" not in rec:
        rec["oem_raw"] = rec["oem"]
    for f, dflt in DEFAULTS.items():
        rec.setdefault(f, dflt)
    return rec


class Store:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.axis_path = os.path.join(root, "_axis.json")
        self.stats_path = os.path.join(root, "_stats.json")
        self._axis = self._load_axis()

    # -- source files ------------------------------------------------------------------
    def source_file(self, source):
        return os.path.join(self.root, f"{slug(source)}.jsonl")

    def sources(self):
        out = []
        for fn in sorted(os.listdir(self.root)):
            if fn.endswith(".jsonl"):
                out.append(fn[:-6])
        return out

    def iter_records(self, source=None):
        """Yield every stored record (all revisions) for one source or all sources."""
        files = [self.source_file(source)] if source else [
            os.path.join(self.root, fn) for fn in sorted(os.listdir(self.root)) if fn.endswith(".jsonl")
        ]
        for path in files:
            if not os.path.exists(path):
                continue
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield _from_disk(json.loads(line))

    def _latest_index(self, source):
        """Map natural key -> the record with the highest revision (latest wins)."""
        idx = {}
        for rec in self.iter_records(source):
            k = _record_key(rec)
            cur = idx.get(k)
            if cur is None or rec["revision"] >= cur["revision"]:
                idx[k] = rec
        return idx

    def latest_records(self, source=None, category=None):
        """Deduped view: highest-revision record per natural key (what the dashboard reads)."""
        idx = {}
        for rec in self.iter_records(source):
            if category is not None and rec["category"] != category:
                continue
            k = _record_key(rec)
            cur = idx.get(k)
            if cur is None or rec["revision"] >= cur["revision"]:
                idx[k] = rec
        return list(idx.values())

    # -- writes ------------------------------------------------------------------------
    def upsert_many(self, records, *, ingested_at=None):
        """
        Idempotently append a batch of records (grouped internally by source).

        Returns a summary dict {added, restated, skipped}. A record is:
          * skipped   if an existing latest revision has the same (value, provisional);
          * restated  (revision+1) if the key exists but the payload changed;
          * added     (revision 0) if the key is new.
        Nothing already on disk is ever modified.
        """
        by_source = defaultdict(list)
        for rec in records:
            by_source[rec["source"]].append(rec)

        summary = {"added": 0, "restated": 0, "skipped": 0}
        for source, recs in by_source.items():
            idx = self._latest_index(source)
            to_append = []
            for rec in recs:
                if ingested_at is not None and rec.get("ingested_at") is None:
                    rec["ingested_at"] = ingested_at
                k = _record_key(rec)
                prev = idx.get(k)
                if prev is None:
                    rec["revision"] = 0
                    to_append.append(rec)
                    idx[k] = rec
                    summary["added"] += 1
                elif _signature(prev) == _signature(rec):
                    summary["skipped"] += 1
                else:
                    rec["revision"] = prev["revision"] + 1
                    to_append.append(rec)
                    idx[k] = rec
                    summary["restated"] += 1
            if to_append:
                self._append(source, to_append)
        return summary

    def confirm_periods(self, source, category, periods, *, by_source, ingested_at=None):
        """
        Wave behaviour: when a backbone source (e.g. SIAM) confirms a month, flip the earlier
        provisional rows of ``source`` (e.g. Company flash) for those periods to
        ``provisional=False`` via a revision bump. Values are unchanged; only the flag flips.
        Returns the number of rows confirmed.
        """
        periods = set(periods)
        idx = self._latest_index(source)
        to_append = []
        for k, rec in idx.items():
            if rec["category"] != category or rec["period"] not in periods:
                continue
            if not rec.get("provisional", False):
                continue
            bumped = dict(rec)
            bumped["provisional"] = False
            bumped["revision"] = rec["revision"] + 1
            bumped["ingested_at"] = ingested_at
            bumped["source_ref"] = f"confirmed-by:{by_source}"
            to_append.append(bumped)
        if to_append:
            self._append(source, to_append)
        return len(to_append)

    def _append(self, source, records):
        path = self.source_file(source)
        with open(path, "a") as f:
            for rec in records:
                f.write(json.dumps(_to_disk(rec), separators=(",", ":")) + "\n")

    # -- period axis -------------------------------------------------------------------
    def _load_axis(self):
        if os.path.exists(self.axis_path):
            with open(self.axis_path) as f:
                return json.load(f)
        return {}

    def extend_axis(self, source, category, frequency, periods):
        """Append-only: add any new periods (in given, chronological order) to the axis."""
        node = self._axis.setdefault(source, {}).setdefault(category, {})
        cur = node.get(frequency, [])
        seen = set(cur)
        for p in periods:
            if p not in seen:
                cur.append(p)
                seen.add(p)
        node[frequency] = cur

    def get_axis(self, source, category, frequency):
        return self._axis.get(source, {}).get(category, {}).get(frequency)

    def save_axis(self):
        tmp = self.axis_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._axis, f, indent=0, separators=(",", ":"))
        os.replace(tmp, self.axis_path)

    # -- housekeeping ------------------------------------------------------------------
    def write_stats(self):
        counts = defaultdict(lambda: {"records": 0, "latest_keys": 0})
        latest = defaultdict(set)
        for rec in self.iter_records():
            counts[rec["source"]]["records"] += 1
            latest[rec["source"]].add(_record_key(rec))
        for src, keys in latest.items():
            counts[src]["latest_keys"] = len(keys)
        stats = {"sources": dict(counts)}
        with open(self.stats_path, "w") as f:
            json.dump(stats, f, indent=2)
        return stats
