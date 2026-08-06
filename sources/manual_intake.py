#!/usr/bin/env python3
"""
sources/manual_intake.py — Manual lane: files dropped into data/intake/ get auto-parsed.
=======================================================================================

Low-frequency top-ups (e.g. ACMA half-yearly, or a one-off correction) are handled by dropping
a file into ``data/intake/``. Naming convention routes it:

    <source>__<label>.<ext>       e.g.  acma__h1fy26.pdf,  siam__jun26.pdf,  company__maruti_jun26.pdf

PDFs are OCR'd + extracted to the generic long-format schema below; the resulting records are
stored under the source implied by the prefix (default ``Manual``). After processing, the file
is moved to ``data/raw/manual/`` (immutable audit trail). Unrecognised/spreadsheet files are
flagged for a human rather than guessed.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone

from lib import model as M
from lib.config import INTAKE_DIR, RAW_DIR
from lib.normalize import canonical
from lib.store import make_record
from sources._common import min_confidence, pdf_to_json
from sources.base import Adapter, register

# Manual drops are ALWAYS stored under a dedicated, namespaced source so they can never restate
# (and thus corrupt) audited backbone series (SIAM / FADA / Company) via the natural key. The
# filename prefix is kept only as a provenance sub-label, not mapped onto a backbone source id.
MANUAL_SOURCE = "Manual"

GENERIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string"},
                    "segment": {"type": "string"},
                    "oem": {"type": "string"},
                    "metric": {"type": "string"},
                    "frequency": {"type": "string", "enum": ["M", "Q", "FY", "H"]},
                    "period": {"type": "string"},
                    "value": {"type": "number"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_label": {"type": "string"},
                },
                "required": ["category", "oem", "metric", "frequency", "period", "value", "confidence"],
            },
        },
    },
    "required": ["rows"],
}

INSTRUCTION = (
    "Extract every numeric data point from this industry document into long-format rows: "
    "category, segment (optional), oem, metric, frequency (M/Q/FY/H), period, value. Use the "
    "period exactly as reported (e.g. 2026-06, Q1FY27, FY26, H1FY26). Each figure needs a "
    "confidence and its source line. Never infer values that are not printed.")


@register
class ManualIntakeAdapter(Adapter):
    name = "manual"
    lane = "Manual"
    store_source = "Manual"
    requires_secret = None

    def fetch(self, period):
        if not os.path.isdir(INTAKE_DIR):
            return None
        files = [os.path.join(INTAKE_DIR, f) for f in sorted(os.listdir(INTAKE_DIR))
                 if not f.startswith(".")]
        files = [f for f in files if os.path.isfile(f)]
        if not files:
            self.log.info("manual intake: no files in %s", INTAKE_DIR)
            return None
        self.log.info("manual intake: %d file(s) to process", len(files))
        return files

    def extract(self, raw, res):
        minc = min_confidence()
        for path in raw:
            fname = os.path.basename(path)
            prefix = fname.split("__", 1)[0].lower() if "__" in fname else "manual"
            # Namespace by prefix for provenance, but keep it firmly inside the Manual source so
            # a mis-named file (e.g. siam__…) can never override the real SIAM/FADA/Company lanes.
            source = f"{MANUAL_SOURCE}:{prefix}" if prefix != "manual" else MANUAL_SOURCE
            ext = os.path.splitext(fname)[1].lower()

            if ext != ".pdf":
                res.flag("manual_unsupported",
                         f"{fname}: only PDF intake is auto-parsed; needs a dedicated adapter")
                self._archive(path, res)
                continue

            with open(path, "rb") as f:
                pdf = f.read()
            data, meta = pdf_to_json(pdf, fname, GENERIC_SCHEMA, INSTRUCTION,
                                     hint=f"Manual drop, source={source}")
            if data is None:
                res.flag("extract_failed", f"{fname}: {meta}")
                # leave the file in intake so it can be retried next run
                continue

            for row in data.get("rows", []):
                conf = float(row.get("confidence", 0))
                if conf < minc:
                    res.flag("low_confidence",
                             f"{fname}: {row.get('oem')}/{row.get('metric')} conf={conf:.2f}")
                    continue
                oem_raw = row.get("oem") or ""
                oem, mapped = canonical(oem_raw)
                if not mapped and oem_raw.strip().lower() not in ("total", "industry"):
                    res.flag("unmapped_oem", f"{fname}: '{oem_raw}' not in alias map (kept)")
                res.records.append(make_record(
                    source, (row.get("category") or "").lower(), row.get("segment") or M.SEG_ALL,
                    oem, row.get("metric"), row.get("frequency"), row.get("period"), row.get("value"),
                    oem_raw=oem_raw or oem, provisional=False, confidence=conf,
                    source_ref=f"manual:{fname}"))
            res.stats[fname] = {"source": source, "rows": len(data.get("rows", []))}
            self._archive(path, res)

    def _archive(self, path, res):
        dest_dir = os.path.join(RAW_DIR, "manual")
        os.makedirs(dest_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dest = os.path.join(dest_dir, f"{stamp}__{os.path.basename(path)}")
        try:
            shutil.move(path, dest)
            res.artifacts.append(dest)
            self.log.info("archived manual file -> %s", dest)
        except OSError as e:
            self.log.warning("could not archive %s: %s", path, e)
