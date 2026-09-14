from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.collectors import jellyfin
from app.collectors.http import ServiceError
from app.config import settings

log = logging.getLogger("uvicorn.error")

SectionFn = Callable[[str, str, float], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Kind:
    """How one type of service is read."""

    sections: dict[str, SectionFn]
    version_path: tuple[str, ...] | None = None
    requires_key: bool = True


KINDS: dict[str, Kind] = {
    "jellyfin": Kind(
        sections={
            "sessions": jellyfin.collect_sessions,
            "library": jellyfin.collect_library,
        },
        version_path=("library", "server", "version"),
    ),
}


@dataclass(frozen=True)
class Probe:
    name: str
    kind: str
    base_url: str
    api_key: str = field(repr=False, default="")


def probes() -> list[Probe]:
    """Every configured service that names a kind this build understands."""
    result: list[Probe] = []
    for name, kind, url in settings.parsed_service_specs():
        if kind not in KINDS:
            log.warning("Ignoring service %r: unknown kind %r", name, kind)
            continue
        result.append(Probe(name, kind, url, settings.service_api_key(name)))
    return result


async def _run_probe(probe: Probe) -> tuple[dict[str, Any], dict[str, Any]]:
    """Collect one service. Returns (sections, status)."""
    kind = KINDS[probe.kind]
    status: dict[str, Any] = {
        "name": probe.name,
        "kind": probe.kind,
        "url": probe.base_url,
        "reachable": True,
        "version": None,
        "error": None,
    }

    if kind.requires_key and not probe.api_key:
        message = (
            f"No API key configured for {probe.name} "
            f"({settings.service_key_variable(probe.name)})"
        )
        status.update(reachable=False, error=message)
        return {name: {"error": message} for name in kind.sections}, status

    async def one(name: str, fn: SectionFn) -> tuple[str, dict[str, Any]]:
        try:
            return name, await fn(
                probe.base_url, probe.api_key, settings.service_timeout
            )
        except ServiceError as exc:
            return name, {"error": str(exc)}
        except Exception as exc:  # pragma: no cover
            log.exception("Probe %s/%s failed unexpectedly", probe.name, name)
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    sections = dict(
        await asyncio.gather(*(one(n, f) for n, f in kind.sections.items()))
    )

    failed = [s.get("error") for s in sections.values() if "error" in s]
    if failed:
        status.update(reachable=False, error=failed[0])
    elif kind.version_path:
        cursor: Any = sections
        for key in kind.version_path:
            cursor = cursor.get(key) if isinstance(cursor, dict) else None
        status["version"] = cursor

    return sections, status


_cache: dict[str, Any] | None = None
_cached_at = 0.0
_lock = asyncio.Lock()


async def collect(max_age_seconds: float | None = None) -> dict[str, Any]:
    """Every service's sections plus a uniform `services` status list."""
    global _cache, _cached_at

    ttl = (
        settings.service_ttl_seconds
        if max_age_seconds is None
        else max_age_seconds
    )

    async with _lock:
        now = time.monotonic()
        if _cache is not None and (now - _cached_at) < ttl:
            return _cache

        configured = probes()
        kind_counts: dict[str, int] = {}
        for probe in configured:
            kind_counts[probe.kind] = kind_counts.get(probe.kind, 0) + 1

        results = await asyncio.gather(*(_run_probe(p) for p in configured))

        payload: dict[str, Any] = {"services": []}
        for probe, (sections, status) in zip(configured, results):
            solo = kind_counts[probe.kind] == 1
            for name, section in sections.items():
                payload[name if solo else f"{probe.name}_{name}"] = section
            payload["services"].append(status)

        _cache, _cached_at = payload, now
        return payload


def reset_cache() -> None:
    """Forget the cached results. For tests, and after a config change."""
    global _cache, _cached_at
    _cache, _cached_at = None, 0.0
