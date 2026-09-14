from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_INLINE_SCRIPT = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


def inline_script_hashes(index_html: Path) -> list[str]:
    """CSP source expressions for every inline script in the built page."""
    try:
        markup = index_html.read_bytes()
    except OSError:
        return []

    return [
        "'sha256-" + base64.b64encode(hashlib.sha256(body).digest()).decode() + "'"
        for body in _INLINE_SCRIPT.findall(markup)
    ]


def build_csp(script_hashes: list[str]) -> str:
    """The page's content security policy, as one header value."""
    fonts_css = "https://fonts.googleapis.com"
    fonts_files = "https://fonts.gstatic.com"

    return "; ".join(
        [
            "default-src 'self'",
            "base-uri 'none'",
            "object-src 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
            "img-src 'self' data:",
            f"style-src 'self' 'unsafe-inline' {fonts_css}",
            f"style-src-elem 'self' {fonts_css}",
            "style-src-attr 'unsafe-inline'",
            f"font-src {fonts_files}",
            " ".join(["script-src 'self'", *script_hashes]),
            "connect-src 'self'",
        ]
    )


_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the policy above to every response, without overriding a route."""

    def __init__(self, app, csp: str) -> None:
        super().__init__(app)
        self._csp = csp

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for name, value in _STATIC_HEADERS.items():
            response.headers.setdefault(name, value)
        if self._csp:
            response.headers.setdefault("Content-Security-Policy", self._csp)
        return response
