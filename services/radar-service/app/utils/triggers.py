"""Trigger utilities for radar-service."""

from __future__ import annotations

import hashlib
import json


def stable_trigger_key(trigger_type: str, tier: str, trigger: dict) -> str:
    """Generate a stable trigger key."""
    payload = {
        "type": trigger.get("type"),
        "name": trigger.get("name"),
        "condition": trigger.get("condition"),
        "value": trigger.get("value"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()
    return f"{trigger_type}:{tier}:{digest}"
