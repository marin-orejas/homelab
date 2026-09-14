from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("uvicorn.error")

HEADER = "Cf-Access-Jwt-Assertion"

# Named here and never read from the token header.
ALGORITHMS = ["RS256"]

_REFETCH_MIN_INTERVAL_SECONDS = 60.0


class AccessError(RuntimeError):
    """The request did not carry a token this origin could verify."""


class Verifier:
    """Checks tokens against one team's published keys."""

    def __init__(self, team_domain: str, audience: str) -> None:
        host = team_domain.strip().removeprefix("https://").removesuffix("/")
        if "." not in host:
            host = f"{host}.cloudflareaccess.com"

        self.issuer = f"https://{host}"
        self.certs_url = f"{self.issuer}/cdn-cgi/access/certs"
        self.audience = audience.strip()

        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _load_keys(self, force: bool = False) -> None:
        from app.collectors.http import ServiceError, get_json

        async with self._lock:
            now = time.monotonic()
            if self._keys and not force:
                return
            if self._fetched_at and (now - self._fetched_at) < _REFETCH_MIN_INTERVAL_SECONDS:
                return
            self._fetched_at = now

            try:
                document = await get_json(self.certs_url, timeout=10.0)
                keys = {
                    key["kid"]: jwt.PyJWK.from_dict(key)
                    for key in document.get("keys", [])
                    if key.get("kid")
                }
            except (ServiceError, jwt.PyJWTError, AttributeError, TypeError) as exc:
                log.error("Access keys could not be loaded: %s", exc)
                return

            self._keys = keys
            log.info("Access signing keys loaded: %d", len(self._keys))

    async def _key_for(self, kid: str) -> Any:
        if not self._keys:
            await self._load_keys()
        if kid not in self._keys:
            await self._load_keys(force=True)
        key = self._keys.get(kid)
        if key is None:
            raise AccessError("token signed by an unknown key")
        return key

    async def verify(self, token: str) -> dict[str, Any]:
        """The token's claims, or AccessError. Never raises anything else."""
        if not token:
            raise AccessError(f"no {HEADER} header")

        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise AccessError(f"malformed token: {exc}") from exc
        if not kid:
            raise AccessError("token names no signing key")

        key = await self._key_for(kid)

        try:
            return jwt.decode(
                token,
                key=key,
                algorithms=ALGORITHMS,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise AccessError(f"{type(exc).__name__}: {exc}") from exc


EXEMPT_PATHS = frozenset({"/api/health"})


class AccessMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, verifier: Verifier, enforce: bool) -> None:
        super().__init__(app)
        self._verifier = verifier
        self._enforce = enforce
        self._seen_a_good_one = False

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        try:
            claims = await self._verifier.verify(request.headers.get(HEADER, ""))
        except AccessError as exc:
            if self._enforce:
                log.warning("Access token refused for %s: %s", request.url.path, exc)
                return JSONResponse(
                    {"detail": "This request did not come through Cloudflare Access."},
                    status_code=403,
                )
            log.warning(
                "Access token would be refused for %s: %s (log mode)",
                request.url.path,
                exc,
            )
            return await call_next(request)

        if not self._seen_a_good_one:
            self._seen_a_good_one = True
            log.info(
                "Access token verified for %s - origin verification is working",
                claims.get("email", "?"),
            )
        else:
            log.debug("Access token accepted for %s", claims.get("email", "?"))
        return await call_next(request)
