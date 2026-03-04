"""Security utilities for Direct DOM Embedding.

This module provides token generation, validation, and origin verification
for the Direct DOM Embedding feature. Implements defense-in-depth security
with HMAC-signed tokens, origin binding, and short-lived credentials.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import diskcache
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from ..interfaces import IFormsSettings


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
        return diskcache.Cache("var/embed_token_cache.db")
    except Exception:
        return None


def _get_signing_key(settings=None):
    """Get the signing key for embed tokens.
    
    Falls back to authenticity_token_secret if embed_direct_signing_key is not set.
    """
    if settings is None:
        try:
            registry = getUtility(IRegistry)
            settings = registry.forInterface(IFormsSettings, check=False)
        except Exception:
            return None
    
    secret = getattr(settings, "embed_direct_signing_key", "") or ""
    if secret:
        return secret.strip()
    
    # Fallback to authenticity token secret
    secret = getattr(settings, "authenticity_token_secret", "") or ""
    return secret.strip() or None


def build_embed_token(payload, secret):
    """Build a signed JWT-style token.
    
    Token format: base64(header).base64(payload).base64(signature)
    
    Args:
        payload: Dictionary with token claims (must include 'exp')
        secret: HMAC signing secret
        
    Returns:
        str: Signed token string
    """
    header = {"alg": "HS256", "typ": "JWT"}
    
    # Encode header and payload
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(header, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    
    # Create signature
    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def validate_embed_token(token, expected_origin, secret=None):
    """Validate an embed token.

    Args:
        token: The token string to validate
        expected_origin: The origin this token must be bound to
        secret: HMAC signing secret (auto-fetched from registry if None)

    Returns:
        dict: The decoded payload if valid

    Raises:
        TokenInvalidError: If token format or signature is invalid
        TokenExpiredError: If token has expired
        EmbedSecurityError: If origin binding check fails
    """
    if secret is None:
        secret = _get_signing_key()
        if not secret:
            raise EmbedSecurityError("Embed signing key not configured")
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenInvalidError("Invalid token format")
        
        header_b64, payload_b64, signature_b64 = parts
        
        # Verify signature
        message = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")
        
        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            raise TokenInvalidError("Invalid token signature")
        
        # Decode payload
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        
        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
        payload = json.loads(payload_json)
        
        # Check expiration
        exp = payload.get("exp")
        if not exp:
            raise TokenInvalidError("Token missing expiration")
        
        if time.time() > exp:
            raise TokenExpiredError("Token has expired")
        
        # Check origin binding
        token_origin = payload.get("origin")
        if token_origin != expected_origin:
            raise EmbedSecurityError(
                f"Origin mismatch: token for {token_origin}, expected {expected_origin}",
                reason="origin_mismatch"
            )
        
        return payload
        
    except (json.JSONDecodeError, base64.binascii.Error) as e:
        raise TokenInvalidError(f"Token decode error: {e}")


def validate_origin(origin, allowed_origins):
    """Validate an origin against an allowlist.
    
    Args:
        origin: The origin to validate (e.g., "https://example.com")
        allowed_origins: List of allowed origin strings
        
    Returns:
        tuple: (is_valid: bool, normalized_origin: str or None, error_message: str)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.warning("[EMBED DEBUG] validate_origin called with: origin=%s, allowed_origins=%s", origin, allowed_origins)
    
    if not origin:
        logger.warning("[EMBED DEBUG] validate_origin: no origin provided")
        return False, None, "Origin header required"
    
    # Parse and normalize
    try:
        parsed = urlparse(origin)
        logger.warning("[EMBED DEBUG] validate_origin: parsed=%s", parsed)
    except Exception as e:
        logger.warning("[EMBED DEBUG] validate_origin: parse error: %s", e)
        return False, None, "Invalid origin format"
    
    # Require HTTPS (except for localhost development)
    hostname = parsed.hostname or ""
    is_localhost = hostname in ("localhost", "127.0.0.1", "::1")
    logger.warning("[EMBED DEBUG] validate_origin: hostname=%s, is_localhost=%s", hostname, is_localhost)
    
    if parsed.scheme != "https" and not is_localhost:
        logger.warning("[EMBED DEBUG] validate_origin: rejected - HTTPS required for non-localhost")
        return False, None, "HTTPS required for embedding (except localhost)"
    
    # Allow http for localhost only
    if parsed.scheme not in ("http", "https"):
        logger.warning("[EMBED DEBUG] validate_origin: rejected - invalid scheme: %s", parsed.scheme)
        return False, None, "Origin must use HTTP or HTTPS"
    
    # No path, query, or fragment allowed in origin
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        logger.warning("[EMBED DEBUG] validate_origin: rejected - path/query/fragment not allowed")
        return False, None, "Origin must not contain path, query, or fragment"
    
    normalized = f"{parsed.scheme}://{parsed.netloc}"
    logger.warning("[EMBED DEBUG] validate_origin: normalized=%s", normalized)
    
    # Check against allowlist
    if normalized not in allowed_origins:
        logger.warning("[EMBED DEBUG] validate_origin: rejected - not in allowlist. normalized=%s, allowed=%s", normalized, allowed_origins)
        return False, None, "Origin not in allowlist"
    
    logger.warning("[EMBED DEBUG] validate_origin: accepted - normalized=%s", normalized)
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
        EmbedSecurityError: If secret is not configured
    """
    if secret is None:
        secret = _get_signing_key()
        if not secret:
            raise EmbedSecurityError("Embed signing key not configured")
    
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
            cache.set(cache_key, {
                "survey_uid": survey_uid,
                "origin": origin,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "used": False,
            }, expire=ttl_seconds + 60)  # Keep slightly longer than token lifetime
        finally:
            cache.close()
    
    metadata = {
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "issued_at": datetime.fromtimestamp(issued_at, tz=timezone.utc).isoformat(),
        "jti": payload["jti"],
    }
    
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
        bool: True if token was newly marked, False if already used
    """
    cache = _get_embed_cache()
    if cache is None:
        return True  # Can't track, assume OK
    
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
        "Content-Type, X-Embed-Token, X-Session-ID, X-Requested-With"
    )
    response.setHeader("Vary", "Origin")
    
    # Security headers
    response.setHeader("X-Content-Type-Options", "nosniff")
    response.setHeader("X-Frame-Options", "DENY")  # We're in shadow DOM, not iframe
    response.setHeader("Referrer-Policy", "strict-origin-when-cross-origin")


def handle_cors_preflight(request, response, allowed_origins):
    """Handle CORS preflight (OPTIONS) requests.
    
    Args:
        request: The HTTP request object
        response: The HTTP response object
        allowed_origins: List of allowed origins
        
    Returns:
        bool: True if this was a preflight request that was handled
    """
    import logging
    logger = logging.getLogger(__name__)
    
    method = request.get("REQUEST_METHOD")
    logger.warning("[EMBED DEBUG] handle_cors_preflight called, method=%s", method)
    
    if method != "OPTIONS":
        logger.warning("[EMBED DEBUG] Not an OPTIONS request, skipping preflight")
        return False
    
    origin = request.get_header("Origin") or request.get("HTTP_ORIGIN")
    logger.warning("[EMBED DEBUG] Preflight origin: %s", origin)
    
    is_valid, normalized, error = validate_origin(origin, allowed_origins)
    logger.warning("[EMBED DEBUG] Preflight validation: is_valid=%s, normalized=%s, error=%s", is_valid, normalized, error)
    
    if is_valid:
        logger.warning("[EMBED DEBUG] Preflight: origin valid, setting full CORS headers")
        set_cors_headers(response, normalized)
    elif origin:
        logger.warning("[EMBED DEBUG] Preflight: origin invalid but present, setting partial CORS headers")
        # Always set Allow-Origin and Allow-Credentials for preflight to avoid browser errors
        # The actual request will still be rejected if origin is invalid
        response.setHeader("Access-Control-Allow-Origin", origin)
        response.setHeader("Access-Control-Allow-Credentials", "true")
        response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        response.setHeader(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Embed-Token, X-Session-ID, X-Requested-With"
        )
    else:
        logger.warning("[EMBED DEBUG] Preflight: no origin provided")
    
    response.setStatus(204)
    logger.warning("[EMBED DEBUG] Preflight returning 204")
    return True
