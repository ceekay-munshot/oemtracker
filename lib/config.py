#!/usr/bin/env python3
"""
lib/config.py — load YAML config + read secrets from the environment (never hardcoded).
======================================================================================
"""

from __future__ import annotations

import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
DATA_DIR = os.path.join(ROOT, "data")
STORE_DIR = os.path.join(DATA_DIR, "store")
RAW_DIR = os.path.join(DATA_DIR, "raw")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
INTAKE_DIR = os.path.join(DATA_DIR, "intake")
OUT_DIR = os.path.join(DATA_DIR, "out")


def load_yaml(name):
    path = os.path.join(CONFIG_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def sources_config():
    return load_yaml("sources.yaml")


def tickers_config():
    return load_yaml("tickers.yaml")


def aliases_config():
    return load_yaml("oem_aliases.yaml")


def secret(name, default=None):
    """Read a secret from env. Returns default (None) if unset or blank."""
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def has_secret(name):
    return secret(name) is not None


def ensure_dirs():
    for d in (STORE_DIR, RAW_DIR, CACHE_DIR, INTAKE_DIR, OUT_DIR):
        os.makedirs(d, exist_ok=True)
