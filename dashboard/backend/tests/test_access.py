from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

import httpx

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import access

pytestmark = pytest.mark.anyio

TEAM = "example-team"
ISSUER = f"https://{TEAM}.cloudflareaccess.com"
AUD = "66672c7280c7f63e39c97fdd9d75929e"
KID = "test-key-1"


@pytest.fixture(scope="module")
def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def verifier(keypair, monkeypatch):
    """A verifier whose key set is served locally instead of from Cloudflare."""
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(keypair.public_key(), as_dict=True)
    jwk.update(kid=KID, alg="RS256", use="sig")

    calls = {"count": 0}

    async def fake_get_json(url, **_):
        calls["count"] += 1
        assert url == f"{ISSUER}/cdn-cgi/access/certs"
        return {"keys": [jwk]}

    monkeypatch.setattr("app.collectors.http.get_json", fake_get_json)

    made = access.Verifier(TEAM, AUD)
    made.fetches = calls
    return made


def sign(keypair, *, aud=AUD, iss=ISSUER, kid=KID, algorithm="RS256",
         key=None, exp_offset=300, claims=None):
    now = int(time.time())
    payload = {
        "aud": aud,
        "iss": iss,
        "iat": now,
        "exp": now + exp_offset,
        "email": "someone@example.com",
    }
    payload.update(claims or {})
    for empty in [k for k, v in payload.items() if v is None]:
        del payload[empty]
    return jwt.encode(
        payload, key if key is not None else keypair,
        algorithm=algorithm, headers={"kid": kid},
    )


async def test_a_token_from_access_is_accepted(verifier, keypair):
    claims = await verifier.verify(sign(keypair))
    assert claims["email"] == "someone@example.com"


async def test_the_team_domain_may_be_given_either_way():
    """The Zero Trust dashboard shows it both ways, so both must work."""
    assert access.Verifier(TEAM, AUD).issuer == ISSUER
    assert access.Verifier(f"{TEAM}.cloudflareaccess.com", AUD).issuer == ISSUER
    assert access.Verifier(f"https://{TEAM}.cloudflareaccess.com/", AUD).issuer == ISSUER


def _b64(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw).rstrip(b"=")


def _handmade(header: dict, payload: dict, secret: bytes | None) -> str:
    """A JWT assembled without PyJWT, the way an attacker would."""
    signing_input = _b64(json.dumps(header).encode()) + b"." + _b64(json.dumps(payload).encode())
    signature = b"" if secret is None else hmac.new(secret, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64(signature)).decode()


async def test_a_token_signed_with_the_wrong_algorithm_is_refused(verifier, keypair):
    """Algorithm confusion: the RSA *public* key used as an HMAC secret."""
    public_pem = keypair.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    now = int(time.time())
    forged = _handmade(
        {"alg": "HS256", "typ": "JWT", "kid": KID},
        {"aud": AUD, "iss": ISSUER, "iat": now, "exp": now + 300},
        secret=public_pem,
    )

    with pytest.raises(access.AccessError):
        await verifier.verify(forged)


async def test_an_unsigned_token_is_refused(verifier):
    """`alg: none` - a token that asserts it needs no signature at all."""
    now = int(time.time())
    forged = _handmade(
        {"alg": "none", "typ": "JWT", "kid": KID},
        {"aud": AUD, "iss": ISSUER, "iat": now, "exp": now + 300},
        secret=None,
    )

    with pytest.raises(access.AccessError):
        await verifier.verify(forged)


async def test_a_token_for_another_application_is_refused(verifier, keypair):
    """The audience is what ties a token to *this* app, not to the account."""
    with pytest.raises(access.AccessError):
        await verifier.verify(sign(keypair, aud="some-other-application"))


async def test_a_token_from_another_team_is_refused(verifier, keypair):
    with pytest.raises(access.AccessError):
        await verifier.verify(sign(keypair, iss="https://someone-else.cloudflareaccess.com"))


async def test_an_expired_token_is_refused(verifier, keypair):
    with pytest.raises(access.AccessError):
        await verifier.verify(sign(keypair, exp_offset=-60))


async def test_a_token_with_no_expiry_is_refused(verifier, keypair):
    """A token that verifies and never expires is a permanent key."""
    with pytest.raises(access.AccessError):
        await verifier.verify(sign(keypair, claims={"exp": None}))


async def test_a_token_signed_by_a_stranger_is_refused(verifier):
    """The whole premise: only Cloudflare holds the signing key."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(access.AccessError):
        await verifier.verify(sign(other, key=other))


async def test_a_missing_header_is_refused(verifier):
    with pytest.raises(access.AccessError):
        await verifier.verify("")


async def test_rubbish_is_refused_rather_than_crashing(verifier):
    for rubbish in ("not-a-token", "a.b.c", "..", "eyJhbGciOiJub25lIn0..") :
        with pytest.raises(access.AccessError):
            await verifier.verify(rubbish)


async def test_keys_are_fetched_once_and_then_reused(verifier, keypair):
    for _ in range(5):
        await verifier.verify(sign(keypair))
    assert verifier.fetches["count"] == 1


async def test_an_unknown_kid_refetches_once_and_is_then_rate_limited(verifier, keypair):
    """A rotation is an unknown kid - so is anything anyone cares to invent."""
    await verifier.verify(sign(keypair))
    assert verifier.fetches["count"] == 1

    for _ in range(10):
        with pytest.raises(access.AccessError):
            await verifier.verify(sign(keypair, kid="invented"))

    assert verifier.fetches["count"] == 1, "rate limit did not hold"


async def test_a_failed_fetch_refuses_rather_than_allowing(monkeypatch, keypair):
    """No keys means no verification, and an unverified request is refused."""
    from app.collectors.http import ServiceError

    async def unreachable(url, **_):
        raise ServiceError("Cannot reach the certs endpoint")

    monkeypatch.setattr("app.collectors.http.get_json", unreachable)

    with pytest.raises(access.AccessError):
        await access.Verifier(TEAM, AUD).verify(sign(keypair))


def test_the_container_healthcheck_is_exempt():
    """The HEALTHCHECK calls this from inside, with no Cloudflare in front."""
    assert "/api/health" in access.EXEMPT_PATHS
    assert "/api/summary" not in access.EXEMPT_PATHS
    assert "/" not in access.EXEMPT_PATHS


def _app_with(verifier, enforce):
    """A minimal ASGI app behind the middleware, called without a network."""
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def ok(_):
        return PlainTextResponse("reached the route")

    app = Starlette(routes=[Route("/api/summary", ok), Route("/api/health", ok)])
    app.add_middleware(access.AccessMiddleware, verifier=verifier, enforce=enforce)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://origin"
    )


async def test_enforce_refuses_a_request_with_no_token(verifier):
    async with _app_with(verifier, enforce=True) as client:
        response = await client.get("/api/summary")
    assert response.status_code == 403
    assert "Cloudflare Access" in response.json()["detail"]


async def test_enforce_lets_a_real_token_through(verifier, keypair):
    async with _app_with(verifier, enforce=True) as client:
        response = await client.get(
            "/api/summary", headers={access.HEADER: sign(keypair)}
        )
    assert response.status_code == 200
    assert response.text == "reached the route"


async def test_enforce_still_answers_the_healthcheck(verifier):
    """The container probes this itself, with no Cloudflare in front."""
    async with _app_with(verifier, enforce=True) as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


async def test_log_mode_lets_a_bad_request_through_and_says_so(verifier, caplog):
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        async with _app_with(verifier, enforce=False) as client:
            response = await client.get("/api/summary")

    assert response.status_code == 200, "log mode must never refuse"
    assert any("would be refused" in r.message for r in caplog.records)


async def test_the_first_good_token_is_announced_once(verifier, keypair, caplog):
    """`log` mode has to be able to prove success, not only failure."""
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        async with _app_with(verifier, enforce=False) as client:
            for _ in range(3):
                await client.get(
                    "/api/summary", headers={access.HEADER: sign(keypair)}
                )

    announced = [r for r in caplog.records if "origin verification is working" in r.message]
    assert len(announced) == 1, "should be announced exactly once, not per request"
