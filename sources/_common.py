#!/usr/bin/env python3
"""
sources/_common.py — shared PDF -> strict-JSON helper used by the OCR+Claude lanes.
==================================================================================
"""

from __future__ import annotations

from lib import ocr as ocr_mod
from lib.config import sources_config
from lib.extract import ExtractionUnavailable, LLMExtractor
from lib.logging_util import get_logger

log = get_logger("extract.pdf")

_EXTRACTOR = None


def get_extractor():
    global _EXTRACTOR
    if _EXTRACTOR is None:
        ex_cfg = (sources_config().get("extract") or {})
        _EXTRACTOR = LLMExtractor(max_calls=ex_cfg.get("max_llm_calls_per_run", 200))
    return _EXTRACTOR


def min_confidence():
    return (sources_config().get("extract") or {}).get("min_confidence", 0.55)


def pdf_to_json(pdf_bytes, filename, schema, instruction, *, hint=None):
    """
    OCR a PDF then extract schema-valid JSON from it. Returns (data, meta) where meta carries
    the OCR sha + provenance, or (None, reason_string) on any recoverable failure.
    """
    ocr_res = ocr_mod.ocr_pdf(pdf_bytes, filename=filename)
    if not ocr_res or not ocr_res.get("text"):
        return None, "OCR unavailable or empty"
    try:
        data = get_extractor().extract(ocr_res["text"], schema, instruction, hint=hint)
    except ExtractionUnavailable as e:
        return None, f"LLM extraction unavailable: {e}"
    except ValueError as e:
        return None, f"LLM extraction failed: {e}"
    meta = {"ocr_sha256": ocr_res.get("sha256"), "ocr_model": ocr_res.get("model"),
            "filename": filename}
    return data, meta
