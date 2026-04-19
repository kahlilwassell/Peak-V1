import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional


PASSWORD_HASH_PREFIX = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 210_000
ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
OAUTH_STATE_TTL_SECONDS = 60 * 10


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _auth_secret() -> bytes:
    return os.getenv("PEAK_AUTH_SECRET", "peak-dev-secret-change-me").encode("utf-8")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "{prefix}${iterations}${salt}${digest}".format(
        prefix=PASSWORD_HASH_PREFIX,
        iterations=PASSWORD_HASH_ITERATIONS,
        salt=_b64encode(salt),
        digest=_b64encode(digest),
    )


def verify_password(stored_password: str, candidate_password: str) -> bool:
    if not stored_password.startswith(f"{PASSWORD_HASH_PREFIX}$"):
        return hmac.compare_digest(stored_password, candidate_password)

    try:
        _, iterations, salt, digest = stored_password.split("$", 3)
        candidate_digest = hashlib.pbkdf2_hmac(
            "sha256",
            candidate_password.encode("utf-8"),
            _b64decode(salt),
            int(iterations),
        )
    except Exception:
        return False

    return hmac.compare_digest(_b64encode(candidate_digest), digest)


def _sign(value: str) -> str:
    signature = hmac.new(_auth_secret(), value.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(signature)


def _create_signed_token(kind: str, subject: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {
        "exp": now + ttl_seconds,
        "iat": now,
        "kind": kind,
        "nonce": secrets.token_urlsafe(16),
        "sub": subject,
    }
    encoded_payload = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{encoded_payload}.{_sign(encoded_payload)}"


def _verify_signed_token(token: str, expected_kind: str) -> Optional[Dict[str, Any]]:
    try:
        encoded_payload, signature = token.split(".", 1)
        if not hmac.compare_digest(_sign(encoded_payload), signature):
            return None
        payload = json.loads(_b64decode(encoded_payload))
    except Exception:
        return None

    if payload.get("kind") != expected_kind:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if not isinstance(payload.get("sub"), str):
        return None
    return payload


def create_access_token(user_id: str) -> str:
    return _create_signed_token("access", user_id, ACCESS_TOKEN_TTL_SECONDS)


def verify_access_token(token: str) -> Optional[str]:
    payload = _verify_signed_token(token, "access")
    return payload["sub"] if payload else None


def create_oauth_state(user_id: str) -> str:
    return _create_signed_token("strava_oauth_state", user_id, OAUTH_STATE_TTL_SECONDS)


def verify_oauth_state(state: str) -> Optional[str]:
    payload = _verify_signed_token(state, "strava_oauth_state")
    return payload["sub"] if payload else None
