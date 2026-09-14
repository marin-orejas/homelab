from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.config import settings

_SEVERITY_ORDER = ("good", "warning", "critical")


def _worst(*severities: str) -> str:
    known = [s for s in severities if s in _SEVERITY_ORDER]
    if not known:
        return "good"
    return max(known, key=_SEVERITY_ORDER.index)


def collect() -> dict[str, Any]:
    """Last SMART reading, or an error field if there is nothing to read."""
    path = settings.smart_state_path
    payload: dict[str, Any] = {
        "path": path,
        "generated_at": None,
        "age_seconds": None,
        "stale": False,
        "stale_after_seconds": settings.smart_stale_after_seconds,
        "severity": "good",
        "disks": [],
    }

    try:
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        payload["error"] = "No reading yet - smartcheck has not run since deployment."
        payload["severity"] = "warning"
        return payload
    except (OSError, json.JSONDecodeError) as exc:
        payload["error"] = f"Could not read {path}: {exc}"
        payload["severity"] = "warning"
        return payload

    payload["disks"] = [dict(disk) for disk in (state.get("disks") or [])]
    payload["generated_at"] = state.get("generated_at")

    deltas: dict[str, Any] = {}
    if settings.history_enabled:
        try:
            from app import storage

            deltas = storage.smart_deltas()
        except Exception:  # pragma: no cover
            deltas = {}

    for disk in payload["disks"]:
        change = deltas.get(disk.get("label")) or {}
        disk["start_stop_delta"] = change.get("start_stop_delta")
        disk["load_cycle_delta"] = change.get("load_cycle_delta")
        disk["delta_since_day"] = change.get("delta_since_day")

    written_at: datetime | None = None
    raw = state.get("generated_at")
    if isinstance(raw, str):
        try:
            written_at = datetime.fromisoformat(raw)
        except ValueError:
            written_at = None
    if written_at is None:
        try:
            written_at = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
        except OSError:
            written_at = None

    if written_at is not None:
        if written_at.tzinfo is None:
            written_at = written_at.astimezone()
        age = (datetime.now(timezone.utc) - written_at).total_seconds()
        payload["age_seconds"] = age
        payload["stale"] = age > settings.smart_stale_after_seconds

    severity = state.get("severity")
    if severity not in _SEVERITY_ORDER:
        severity = _worst(*(d.get("severity", "good") for d in payload["disks"]))

    if payload["stale"]:
        severity = _worst(severity, "warning")

    payload["severity"] = severity
    return payload
