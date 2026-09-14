from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from app import security


def test_inline_script_hash_matches_what_a_browser_would_compute(tmp_path):
    """The hash covers the script body, and nothing around it."""
    body = '\n      var theme = "dark";\n    '
    index = tmp_path / "index.html"
    index.write_text(f"<head><script>{body}</script></head>")

    digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    assert security.inline_script_hashes(index) == [f"'sha256-{digest}'"]


def test_inline_script_hashes_skips_scripts_with_a_src(tmp_path):
    """The bundle is loaded by src, and is covered by 'self' rather than a hash."""
    index = tmp_path / "index.html"
    index.write_text(
        "<script>var a = 1;</script>"
        '<script type="module" src="/assets/index.js"></script>'
    )

    hashes = security.inline_script_hashes(index)
    assert len(hashes) == 1
    assert hashes[0].startswith("'sha256-") and hashes[0].endswith("'")


def test_inline_script_hashes_is_empty_without_a_built_page():
    """Local development has no bundle, and the app must still start."""
    assert security.inline_script_hashes(Path("/nonexistent/index.html")) == []


def test_csp_never_allows_inline_script():
    """'unsafe-inline' in script-src is the whole policy undone."""
    policy = security.build_csp(["'sha256-abc'"])

    script = next(d for d in policy.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script
    assert "'sha256-abc'" in script


def test_csp_closes_the_directives_that_have_no_use_here():
    """A page with no forms, no plugins and no frames should say so."""
    policy = security.build_csp([])

    for directive in (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "connect-src 'self'",
    ):
        assert directive in policy

    assert "style-src-attr 'unsafe-inline'" in policy
    assert "style-src-elem 'self' https://fonts.googleapis.com" in policy
