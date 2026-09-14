from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import access, security, storage
from app.collectors import http, services, smart, system
from app.config import settings

log = logging.getLogger("uvicorn.error")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_PRUNE_INTERVAL_SECONDS = 6 * 3600


async def _sample_once() -> None:
    """Take one reading and store it."""
    payload: dict = {
        "system": await asyncio.to_thread(system.collect_all),
        "smart": await asyncio.to_thread(smart.collect),
    }
    payload.update(await services.collect())

    await asyncio.to_thread(storage.record, payload)


async def _history_writer() -> None:
    """Sample on an interval until cancelled."""
    last_prune = 0.0

    while True:
        try:
            await _sample_once()

            now = time.monotonic()
            if now - last_prune > _PRUNE_INTERVAL_SECONDS:
                await asyncio.to_thread(storage.prune)
                last_prune = now
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("History sample failed; continuing")

        await asyncio.sleep(settings.history_interval_seconds)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task: asyncio.Task | None = None

    await http.open_client()

    if settings.history_enabled:
        try:
            await asyncio.to_thread(storage.initialise)
            task = asyncio.create_task(_history_writer())
        except Exception:
            log.exception("History disabled: the database could not be opened")

    yield

    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    await http.close_client()


app = FastAPI(
    title="Home Lab Dashboard API",
    description="Read-only host and media-stack metrics for a home server.",
    version="0.3.1",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)


def _install_access_check(application: FastAPI) -> None:
    """Verify the Cloudflare Access token, if this deployment is set up to."""
    mode = settings.access_mode.strip().lower()
    if mode == "off":
        return
    if mode not in ("log", "enforce"):
        raise RuntimeError(
            f"DASHBOARD_ACCESS_MODE must be off, log or enforce; got {mode!r}."
        )

    if not (settings.access_team_domain and settings.access_aud):
        raise RuntimeError(
            f"DASHBOARD_ACCESS_MODE={mode} needs both DASHBOARD_ACCESS_TEAM_DOMAIN "
            "and DASHBOARD_ACCESS_AUD."
        )

    verifier = access.Verifier(settings.access_team_domain, settings.access_aud)
    application.add_middleware(
        access.AccessMiddleware, verifier=verifier, enforce=(mode == "enforce")
    )
    log.info("Cloudflare Access verification is %s, issuer %s", mode, verifier.issuer)


_install_access_check(app)

app.add_middleware(
    security.SecurityHeadersMiddleware,
    csp=security.build_csp(security.inline_script_hashes(STATIC_DIR / "index.html")),
)

if settings.cors_origins.strip():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET"],
        allow_headers=["*"],
    )


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe. Deliberately does no downstream calls."""
    return {"status": "ok"}


@app.get("/api/system", tags=["system"])
async def get_system() -> dict:
    """Full host snapshot: CPU, memory, disks, network, sensors, processes."""
    return await asyncio.to_thread(system.collect_all)


@app.get("/api/services", tags=["services"])
async def get_services() -> dict:
    """Reachability and version of every configured downstream service."""
    payload = await services.collect()
    return {"services": payload["services"]}


async def _service_section(key: str) -> dict:
    payload = await services.collect()
    section = payload.get(key)
    if section is None:
        raise HTTPException(status_code=404, detail=f"No service provides {key}.")
    if "error" in section:
        raise HTTPException(status_code=503, detail=section["error"])
    return section


@app.get("/api/jellyfin/sessions", tags=["services"])
async def get_jellyfin_sessions() -> dict:
    """Currently playing streams, including transcode reasons."""
    return await _service_section("sessions")


@app.get("/api/jellyfin/library", tags=["services"])
async def get_jellyfin_library() -> dict:
    """Library item counts and server version info."""
    return await _service_section("library")


@app.get("/api/smart", tags=["system"])
async def get_smart() -> dict:
    """Last daily SMART reading of the two media disks."""
    return await asyncio.to_thread(smart.collect)


@app.get("/api/summary", tags=["system"])
async def get_summary() -> dict:
    """Everything in one call, for a dashboard that polls a single endpoint."""
    payload: dict = {
        "system": await asyncio.to_thread(system.collect_all),
        "smart": await asyncio.to_thread(smart.collect),
    }
    payload.update(await services.collect())
    return payload


HISTORY_RANGES: dict[str, int] = {
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
    "7d": 604800,
    "30d": 2592000,
}


def _require_history() -> None:
    if not settings.history_enabled:
        raise HTTPException(
            status_code=503,
            detail="History is disabled (DASHBOARD_HISTORY_ENABLED=false).",
        )


@app.get("/api/history", tags=["history"])
async def get_history(
    window: str = Query("24h", alias="range", description="One of 1h, 6h, 24h, 7d, 30d"),
    buckets: int = Query(180, ge=10, le=1000),
) -> dict:
    """Downsampled series over a window, with counters already turned into rates."""
    _require_history()

    if window not in HISTORY_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown range '{window}'. Valid: {', '.join(HISTORY_RANGES)}.",
        )

    payload = await asyncio.to_thread(
        storage.history,
        storage.HistoryWindow(seconds=HISTORY_RANGES[window], buckets=buckets),
    )
    payload["range"] = window
    payload["storage"] = await asyncio.to_thread(storage.statistics)
    return payload


@app.get("/api/history/disks", tags=["history"])
async def get_disk_trend(days: int = Query(90, ge=1, le=3650)) -> dict:
    """Daily fill levels, plus a fill-rate projection per disk."""
    _require_history()
    return await asyncio.to_thread(storage.disk_trend, days)


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
