#!/usr/bin/env python3
"""
scripts/verify_identity.py — prove the store round-trip reproduces the dashboard JSON.
=====================================================================================

Compares every ``data/*.json`` produced by ``lib/build.py`` (store -> JSON) against a
reference directory (the committed / workbook-built JSON). Reports:

  * BYTE-identical files, and
  * SEMANTIC differences (parsed + normalized: object key order ignored, arrays compared
    in order). Any semantic difference is a real regression and exits non-zero.

    python3 scripts/verify_identity.py <reference_dir> [<candidate_dir=data>]
"""

from __future__ import annotations

import json
import os
import sys


def norm(x):
    """Canonicalize for semantic comparison (sort dict keys; keep list order)."""
    if isinstance(x, dict):
        return {k: norm(x[k]) for k in sorted(x)}
    if isinstance(x, list):
        return [norm(v) for v in x]
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a), set(b)
        if ka != kb:
            out.append(f"{path}: keys only-new={sorted(ka - kb)} only-ref={sorted(kb - ka)}")
        for k in sorted(ka & kb):
            out += diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length new={len(a)} ref={len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    else:
        if a != b:
            out.append(f"{path}: new={a!r} ref={b!r}")
    return out


def main():
    ref_dir = sys.argv[1]
    cand_dir = sys.argv[2] if len(sys.argv) > 2 else "data"
    ref_files = sorted(f for f in os.listdir(ref_dir) if f.endswith(".json"))

    byte_ok = semantic_ok = 0
    problems = []
    for fn in ref_files:
        rp, cp = os.path.join(ref_dir, fn), os.path.join(cand_dir, fn)
        if not os.path.exists(cp):
            problems.append(f"MISSING candidate: {fn}")
            continue
        rb, cb = open(rp, "rb").read(), open(cp, "rb").read()
        if rb == cb:
            byte_ok += 1
            semantic_ok += 1
            continue
        d = diff(norm(json.loads(cb)), norm(json.loads(rb)))
        if not d:
            semantic_ok += 1
            print(f"  ~ {fn}: byte-differs but SEMANTICALLY IDENTICAL (key order only)")
        else:
            problems.append(f"SEMANTIC DIFF in {fn} ({len(d)} diffs):")
            problems += ["      " + line for line in d[:15]]

    print(f"\n  {len(ref_files)} reference files: byte-identical={byte_ok}  semantic-identical={semantic_ok}")
    # candidate-only files (e.g. new datasets) are informational, not failures
    cand_only = sorted(set(f for f in os.listdir(cand_dir) if f.endswith(".json")) - set(ref_files))
    if cand_only:
        print(f"  candidate-only files (new, informational): {cand_only}")
    if problems:
        print("\n  PROBLEMS:")
        for p in problems:
            print("   " + p)
        sys.exit(1)
    print("  ✓ store round-trip reproduces the dashboard JSON (semantically identical).")


if __name__ == "__main__":
    main()
