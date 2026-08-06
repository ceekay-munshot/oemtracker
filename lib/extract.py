#!/usr/bin/env python3
"""
lib/extract.py — the extraction brain: Claude on Bedrock turns OCR/markdown into strict JSON.
============================================================================================

* Forces schema-valid output by giving Claude a single tool whose ``input_schema`` IS the
  caller's JSON Schema and requiring ``tool_choice`` = that tool.
* Validates the returned object against the schema; on failure, retries with the validation
  error fed back to Claude (up to a small cap).
* Caches every result by sha256(text + schema + instruction + model) so an unchanged input is
  never re-charged. Keeps a per-run token/$ tally and honours a per-run call cap.
* Never fabricates: the wrapper instruction tells Claude to return a per-figure ``confidence``
  and the source line/label it read each number from, and to lower confidence rather than guess.

Auth: uses Bedrock via boto3. Works with either standard AWS creds
(AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION) or a Bedrock API key
(BEDROCK_API_KEY, exported as AWS_BEARER_TOKEN_BEDROCK). Model id from BEDROCK_CLAUDE_MODEL_ID.
"""

from __future__ import annotations

import json
import os

from lib import cache
from lib.config import secret
from lib.logging_util import get_logger, truncate

log = get_logger("extract")

# Rough Bedrock Claude pricing (USD per 1K tokens) for a ballpark $ tally only.
_PRICE_IN = 0.003
_PRICE_OUT = 0.015

_TALLY = {"calls": 0, "in_tokens": 0, "out_tokens": 0, "usd": 0.0}


def run_tally():
    return dict(_TALLY)


def reset_tally():
    for k in _TALLY:
        _TALLY[k] = 0 if k != "usd" else 0.0


class ExtractionUnavailable(Exception):
    """Raised when no Bedrock credential is configured (lane should skip + flag)."""


class LLMExtractor:
    def __init__(self, model_id=None, max_calls=200):
        self.model_id = model_id or secret("BEDROCK_CLAUDE_MODEL_ID")
        self.max_calls = max_calls
        self._client = None

    def _bedrock(self):
        if self._client is not None:
            return self._client
        try:
            import boto3  # noqa: PLC0415 — lazy so import never crashes without the dep
        except ImportError as e:
            raise ExtractionUnavailable("boto3 not installed — cannot reach Bedrock.") from e

        api_key = secret("BEDROCK_API_KEY")
        if api_key and not os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key
        region = secret("AWS_REGION", "us-east-1")

        if not (api_key or secret("AWS_ACCESS_KEY_ID")):
            raise ExtractionUnavailable(
                "No Bedrock credential (need BEDROCK_API_KEY or AWS_ACCESS_KEY_ID). Lane will flag+skip.")
        if not self.model_id:
            raise ExtractionUnavailable("BEDROCK_CLAUDE_MODEL_ID is not set.")

        self._client = boto3.client("bedrock-runtime", region_name=region)
        return self._client

    def extract(self, text, schema, instruction, *, hint=None, max_tokens=4096, retries=2):
        """
        Extract strict JSON matching ``schema`` from ``text``. Returns the validated dict.
        Raises ExtractionUnavailable if no credential; other failures raise ValueError.
        """
        key = cache.sha256_text(self.model_id or "?", instruction, json.dumps(schema, sort_keys=True), text)
        cached = cache.get("llm", key)
        if cached is not None:
            return cached

        if _TALLY["calls"] >= self.max_calls:
            raise ValueError(f"LLM call cap reached ({self.max_calls}/run) — skipping to stay in budget.")

        client = self._bedrock()
        system = (
            "You are a meticulous financial-data extraction engine for Indian auto-industry "
            "filings. Extract ONLY figures that are explicitly present. Never guess or "
            "interpolate. For every figure include a confidence in [0,1] and the exact source "
            "line/label you read it from. If a value is unclear, lower its confidence rather "
            "than inventing a number. Respond ONLY by calling the `emit` tool.")
        user = instruction.strip()
        if hint:
            user += f"\n\nContext hint: {hint}"
        user += "\n\n=== SOURCE TEXT START ===\n" + text + "\n=== SOURCE TEXT END ==="

        messages = [{"role": "user", "content": [{"type": "text", "text": user}]}]
        tool = {"name": "emit", "description": "Return the extracted, schema-valid data.",
                "input_schema": schema}

        last_err = None
        for attempt in range(retries + 1):
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
                "tools": [tool],
                "tool_choice": {"type": "tool", "name": "emit"},
            }
            log.info("bedrock invoke model=%s attempt=%d (in≈%d chars)",
                     self.model_id, attempt + 1, len(user))
            resp = client.invoke_model(modelId=self.model_id, body=json.dumps(body))
            payload = json.loads(resp["body"].read())
            _account(payload)

            data = _first_tool_input(payload)
            if data is None:
                last_err = "model did not call the emit tool"
                messages += _retry_turn(payload, "You must call the `emit` tool with valid JSON.")
                continue

            ok, err = _validate(data, schema)
            if ok:
                cache.put("llm", key, data)
                log.info("extraction OK (tally: %d calls, ~$%.3f)", _TALLY["calls"], _TALLY["usd"])
                return data
            last_err = err
            log.warning("schema-invalid output (%s) — retrying with the error", truncate(err, 200))
            messages += _retry_turn(payload, f"Your output failed schema validation: {err}. "
                                             f"Fix it and call `emit` again.")

        raise ValueError(f"extraction failed after {retries + 1} attempts: {last_err}")


# -- helpers ---------------------------------------------------------------------------

def _first_tool_input(payload):
    for block in payload.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "emit":
            return block.get("input")
    return None


def _retry_turn(assistant_payload, correction):
    return [
        {"role": "assistant", "content": assistant_payload.get("content", [])},
        {"role": "user", "content": [{"type": "text", "text": correction}]},
    ]


def _validate(data, schema):
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:
        # Fail CLOSED: never accept/cache unvalidated LLM output just because the validator
        # is missing (jsonschema is a hard dependency in requirements.txt).
        return False, "jsonschema not installed — cannot validate; rejecting (fail closed)"
    try:
        jsonschema.validate(data, schema)
        return True, None
    except jsonschema.ValidationError as e:
        return False, e.message


def _account(payload):
    usage = payload.get("usage", {}) or {}
    it = usage.get("input_tokens", 0)
    ot = usage.get("output_tokens", 0)
    _TALLY["calls"] += 1
    _TALLY["in_tokens"] += it
    _TALLY["out_tokens"] += ot
    _TALLY["usd"] += it / 1000.0 * _PRICE_IN + ot / 1000.0 * _PRICE_OUT
