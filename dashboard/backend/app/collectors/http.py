from __future__ import annotations

import json
from typing import Any

import httpx


class ServiceError(RuntimeError):
    """A downstream service is unreachable or rejected the request."""


_client: httpx.AsyncClient | None = None


async def open_client() -> None:
    """Create the shared client. Called once, from the app lifespan."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient()


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _require_client() -> httpx.AsyncClient:
    if _client is None:
        raise ServiceError("HTTP client is not open")
    return _client


async def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> Any:
    """GET a JSON document, or raise ServiceError."""
    global _client
    if _client is None:
        await open_client()

    client = _require_client()
    try:
        response = await client.get(
            url, headers=headers, params=params, timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise ServiceError(
            f"{exc.response.status_code} from {url}"
        ) from exc
    except httpx.RequestError as exc:
        raise ServiceError(f"Cannot reach {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ServiceError(f"{url} did not return JSON: {exc}") from exc
