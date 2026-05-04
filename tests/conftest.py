"""Shared pytest configuration."""

from __future__ import annotations

import os

# Force a deterministic dev env for tests so Settings doesn't pick up a host
# .env that points at a real database. Per-test overrides happen via
# monkeypatch in the relevant fixtures.
os.environ.setdefault("HAWIYA_ENV", "dev")
os.environ.setdefault("HAWIYA_LOG_LEVEL", "WARNING")
os.environ.setdefault("HAWIYA_DEV_BEARER_TOKEN", "dev")
