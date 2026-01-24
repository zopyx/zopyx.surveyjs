import base64
import hashlib
import hmac
import json
import time
import uuid


class AuthTokenError(ValueError):
    def __init__(self, reason: str, status: int = 403) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(message: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256)
    return _b64url_encode(digest.digest())


def build_auth_token(
    *,
    form_id: str,
    form_version: str,
    issuer: str,
    audience: str,
    ttl_seconds: int,
    secret: str,
    now: int | None = None,
) -> str:
    issued_at = int(time.time()) if now is None else int(now)
    payload = {
        "iss": issuer,
        "aud": audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + int(ttl_seconds),
        "jti": uuid.uuid4().hex,
        "form_id": form_id,
        "form_version": form_version,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    message = f"{encoded_header}.{encoded_payload}"
    signature = _sign(message, secret)
    return f"{message}.{signature}"


def validate_auth_token(
    *,
    token: str,
    form_id: str,
    form_version: str,
    issuer: str,
    audience: str,
    secret: str,
    now: int | None = None,
    skew_seconds: int = 120,
) -> dict:
    if not token:
        raise AuthTokenError("missing_auth_token", status=400)

    parts = token.split(".")
    if len(parts) != 3:
        raise AuthTokenError("invalid_auth_token", status=403)

    encoded_header, encoded_payload, signature = parts
    message = f"{encoded_header}.{encoded_payload}"
    expected_sig = _sign(message, secret)
    if not hmac.compare_digest(expected_sig, signature):
        raise AuthTokenError("invalid_auth_token", status=403)

    try:
        header = json.loads(_b64url_decode(encoded_header))
        payload = json.loads(_b64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        raise AuthTokenError("invalid_auth_token", status=403)

    if header.get("alg") != "HS256":
        raise AuthTokenError("invalid_auth_token", status=403)

    now_value = int(time.time()) if now is None else int(now)

    exp = payload.get("exp")
    nbf = payload.get("nbf")
    iat = payload.get("iat")
    if exp is None or nbf is None or iat is None:
        raise AuthTokenError("invalid_auth_token", status=403)

    if now_value > int(exp) + skew_seconds:
        raise AuthTokenError("auth_token_expired", status=403)
    if now_value + skew_seconds < int(nbf):
        raise AuthTokenError("auth_token_not_yet_valid", status=403)
    if now_value + skew_seconds < int(iat):
        raise AuthTokenError("auth_token_invalid_time", status=403)

    if payload.get("iss") != issuer or payload.get("aud") != audience:
        raise AuthTokenError("auth_token_claims_mismatch", status=403)

    if payload.get("form_id") != form_id or payload.get("form_version") != form_version:
        raise AuthTokenError("auth_token_claims_mismatch", status=403)

    return payload
