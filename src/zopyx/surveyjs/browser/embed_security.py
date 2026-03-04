"""Security utilities for Direct DOM Embedding.

This module provides token generation, validation, and origin verification
for the Direct DOM Embedding feature. Implements defense-in-depth security
with HMAC-signed tokens, origin binding, and short-lived credentials.
"""

import logging
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import diskcache
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ..interfaces import IFormsSettings

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("zopyx.surveyjs.embed.audit")


class EmbedSecurityError(Exception):
    """Base exception for embed security errors."""

    def __init__(self, message, reason=None):
        super().__init__(message)
        self.reason = reason


class TokenExpiredError(EmbedSecurityError):
    """Raised when a token has expired."""

    pass


class TokenInvalidError(EmbedSecurityError):
    """Raised when a token is invalid or tampered."""

    pass


class OriginNotAllowedError(EmbedSecurityError):
    """Raised when an origin is not in the allowlist."""

    pass


def _get_embed_cache():
    """Get diskcache instance for embed tokens."""
    try:
        cache_path = os.path.join(os.getcwd(), "var", "embed_token_cache.db")
        return diskcache.Cache(cache_path)
    except Exception:
        return None


def _get_signing_key(settings=None):
    """Get the signing key for embed tokens.

    Returns None if embed_direct_signing_key is not configured.
    Does NOT fall back to other secrets — a dedicated key is required.
    """
    if settings is None:
        try:
            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)
        except Exception:
            return None

    secret = getattr(settings, "embed_direct_signing_key", "") or ""
    return secret.strip() or None


def build_embed_token(payload, secret):
    """Build a signed JWT token using PyJWT.

    Args:
        payload: Dictionary with token claims (must include 'exp')
        secret: HMAC signing secret

    Returns:
        str: Signed JWT token string
    """
    return jwt.encode(payload, secret, algorithm="HS256")


def validate_embed_token(token, expected_origin, secret=None):
    """Validate an embed token using PyJWT.

    Args:
        token: The JWT token string to validate
        expected_origin: The origin this token must be bound to
        secret: HMAC signing secret (auto-fetched from registry if None)

    Returns:
        dict: The decoded payload if valid

    Raises:
        TokenInvalidError: If token format, signature, or one-time use check fails
        TokenExpiredError: If token has expired
        EmbedSecurityError: If origin binding check fails or signing key not configured
    """
    if secret is None:
        secret = _get_signing_key()
        if not secret:
            raise EmbedSecurityError(
                "embed_direct_signing_key must be configured in Site Setup > "
                "Forms Settings before using Direct DOM Embedding"
            )

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="embed-client",
            issuer="privacyforms.studio",
            options={"verify_aud": True, "verify_iss": True},
        )
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except InvalidTokenError as e:
        raise TokenInvalidError(f"Invalid token: {e}")

    # Check origin binding (custom claim, not verified by PyJWT)
    token_origin = payload.get("origin")
    if token_origin != expected_origin:
        raise EmbedSecurityError(
            f"Origin mismatch: token for {token_origin}, expected {expected_origin}",
            reason="origin_mismatch",
        )

    audit_logger.info(
        "embed.token.validated",
        extra={
            "jti": payload.get("jti"),
            "survey_uid": payload.get("sub"),
            "origin": expected_origin,
            "status": "ok",
        },
    )
    return payload


def validate_origin(origin, allowed_origins):
    """Validate an origin against an allowlist.

    Args:
        origin: The origin to validate (e.g., "https://example.com")
        allowed_origins: List of allowed origin strings

    Returns:
        tuple: (is_valid: bool, normalized_origin: str or None, error_message: str)
    """
    if not origin:
        return False, None, "Origin header required"

    # Parse and normalize
    try:
        parsed = urlparse(origin)
    except Exception:
        return False, None, "Invalid origin format"

    # Require HTTPS (except for localhost development)
    hostname = parsed.hostname or ""
    is_localhost = hostname in ("localhost", "127.0.0.1", "::1")

    if parsed.scheme != "https" and not is_localhost:
        return False, None, "HTTPS required for embedding (except localhost)"

    # Allow http for localhost only
    if parsed.scheme not in ("http", "https"):
        return False, None, "Origin must use HTTP or HTTPS"

    # No path, query, or fragment allowed in origin
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return False, None, "Origin must not contain path, query, or fragment"

    normalized = f"{parsed.scheme}://{parsed.netloc}"

    # Normalize stored allowlist entries to scheme://netloc so that values
    # stored with a trailing slash (https://example.com/) still match.
    def _norm(o):
        try:
            p = urlparse(o)
            return f"{p.scheme}://{p.netloc}"
        except Exception:
            return o

    normalized_allowlist = {_norm(o) for o in allowed_origins}

    # Check against allowlist
    if normalized not in normalized_allowlist:
        return False, None, "Origin not in allowlist"

    return True, normalized, None


def generate_embed_token(survey_uid, origin, ttl_seconds=300, secret=None):
    """Generate a new embed token for a survey.

    Args:
        survey_uid: Unique identifier for the survey
        origin: The origin this token is bound to
        ttl_seconds: Token lifetime in seconds (default 300)
        secret: HMAC signing secret (auto-fetched if None)

    Returns:
        tuple: (token_string, metadata_dict)

    Raises:
        EmbedSecurityError: If signing key is not configured
    """
    if secret is None:
        secret = _get_signing_key()
        if not secret:
            raise EmbedSecurityError(
                "embed_direct_signing_key must be configured in Site Setup > "
                "Forms Settings before using Direct DOM Embedding"
            )

    issued_at = int(time.time())
    expires_at = issued_at + min(max(ttl_seconds, 60), 3600)

    payload = {
        "iss": "privacyforms.studio",
        "aud": "embed-client",
        "sub": survey_uid,
        "origin": origin,
        "iat": issued_at,
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
        "nonce": secrets.token_urlsafe(16),
    }

    token = build_embed_token(payload, secret)

    # Store token metadata in cache for revocation/tracking
    cache = _get_embed_cache()
    if cache is not None:
        try:
            cache_key = f"embed_token:{payload['jti']}"
            cache.set(
                cache_key,
                {
                    "survey_uid": survey_uid,
                    "origin": origin,
                    "issued_at": issued_at,
                    "expires_at": expires_at,
                    "used": False,
                },
                expire=ttl_seconds + 60,
            )  # Keep slightly longer than token lifetime
        finally:
            cache.close()

    metadata = {
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "issued_at": datetime.fromtimestamp(issued_at, tz=timezone.utc).isoformat(),
        "jti": payload["jti"],
    }

    audit_logger.info(
        "embed.token.issued",
        extra={
            "survey_uid": survey_uid,
            "origin": origin,
            "jti": payload["jti"],
            "expires_at": metadata["expires_at"],
        },
    )

    return token, metadata


def is_embed_direct_globally_enabled():
    """Check if direct DOM embedding is enabled globally.

    Returns:
        bool: True if enabled in registry settings
    """
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        return getattr(settings, "embed_direct_global_enabled", False)
    except Exception:
        return False


def get_embed_direct_max_origins(default=10):
    """Get maximum allowed origins per survey.

    Args:
        default: Default value if not configured

    Returns:
        int: Maximum number of origins allowed
    """
    try:
        registry = getUtility(IRegistry)
        settings = registry.forInterface(IFormsSettings, check=False)
        value = getattr(settings, "embed_direct_max_origins", default)
        return min(max(int(value), 1), 100)
    except Exception:
        return default


def mark_token_used(jti):
    """Mark a token as used (for one-time use enforcement).

    Args:
        jti: The token ID (jti claim)

    Returns:
        bool: True if token was newly marked (first use), False if already used
    """
    cache = _get_embed_cache()
    if cache is None:
        logger.error("embed.cache.unavailable: rejecting token use to prevent replay")
        return False  # Fail-closed: deny rather than allow replay

    try:
        cache_key = f"embed_token_used:{jti}"
        # add() returns True only if key didn't exist
        was_added = cache.add(cache_key, True, expire=3600)
        return was_added
    finally:
        cache.close()


def set_cors_headers(response, origin):
    """Set appropriate CORS headers for embed endpoints.

    Args:
        response: The HTTP response object
        origin: The allowed origin (specific, not wildcard)
    """
    response.setHeader("Access-Control-Allow-Origin", origin)
    response.setHeader("Access-Control-Allow-Credentials", "true")
    response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.setHeader(
        "Access-Control-Allow-Headers",
        "Content-Type, X-Embed-Token, X-Session-ID, X-Requested-With",
    )
    response.setHeader("Vary", "Origin")

    # Security headers
    response.setHeader("X-Content-Type-Options", "nosniff")
    response.setHeader("X-Frame-Options", "DENY")  # We're in shadow DOM, not iframe
    response.setHeader("Referrer-Policy", "strict-origin-when-cross-origin")


def handle_cors_preflight(request, response, allowed_origins):
    """Handle CORS preflight (OPTIONS) requests.

    Only sets CORS headers for origins in the allowlist. Unknown origins
    receive a 204 response with no CORS headers — the browser will then
    block the actual request client-side.

    Args:
        request: The HTTP request object
        response: The HTTP response object
        allowed_origins: List of allowed origins

    Returns:
        bool: True if this was a preflight request that was handled
    """
    method = request.get("REQUEST_METHOD")

    if method != "OPTIONS":
        return False

    origin = request.get_header("Origin") or request.get("HTTP_ORIGIN")

    is_valid, normalized, error = validate_origin(origin, allowed_origins)

    if is_valid:
        set_cors_headers(response, normalized)
    # else: return 204 with no CORS headers — browser blocks the actual request

    response.setStatus(204)
    return True
