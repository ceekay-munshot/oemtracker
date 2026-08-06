#!/usr/bin/env python3
"""
lib/ocr.py — Mistral OCR for scanned / complex PDFs, cached by file sha256.
==========================================================================

Turns a PDF (bytes) into text/markdown. Results are cached by the sha256 of the PDF, so an
unchanged filing is never OCR'd (or paid for) twice. Missing MISTRAL_API_KEY -> the caller's
lane skips + flags; OCR itself just returns None and logs why.
"""

from __future__ import annotations

import base64

from lib import cache
from lib import http_util as http
from lib.config import secret
from lib.logging_util import get_logger

log = get_logger("ocr")

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
OCR_MODEL = "mistral-ocr-latest"


def ocr_pdf(pdf_bytes, *, filename="document.pdf"):
    """
    OCR a PDF -> {"text": <all-pages markdown>, "pages": [...], "sha256": ...} or None.
    Cached by sha256(pdf_bytes).
    """
    if not pdf_bytes:
        return None
    sha = cache.sha256_bytes(pdf_bytes)
    cached = cache.get("ocr", sha)
    if cached is not None:
        return cached

    key = secret("MISTRAL_API_KEY")
    if not key:
        log.warning("MISTRAL_API_KEY not set — cannot OCR %s (%d bytes). Lane will flag+skip.",
                    filename, len(pdf_bytes))
        return None

    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    body = {
        "model": OCR_MODEL,
        "document": {"type": "document_url",
                     "document_url": f"data:application/pdf;base64,{b64}"},
        "include_image_base64": False,
    }
    try:
        resp = http.post(MISTRAL_OCR_URL, headers={"Authorization": f"Bearer {key}"},
                         json_body=body, accept="application/json", timeout=180,
                         label=f"mistral.ocr[{filename}]")
    except http.AuthError:
        log.error("Mistral OCR auth failed — check MISTRAL_API_KEY.")
        return None
    except Exception as e:  # noqa: BLE001 — never abort the run on a flaky OCR call
        log.error("Mistral OCR failed for %s: %s", filename, e)
        return None

    data = resp.json()
    pages = data.get("pages", [])
    text = "\n\n".join(p.get("markdown", "") or p.get("text", "") for p in pages) if pages \
        else (data.get("markdown") or data.get("text") or "")
    result = {"sha256": sha, "text": text, "pages": pages, "model": OCR_MODEL}
    cache.put("ocr", sha, result)
    log.info("OCR %s -> %d chars across %d pages (cached under %s)",
             filename, len(text), len(pages), sha[:12])
    return result
