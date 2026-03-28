"""Authentication and trusted-access helpers for survey browser services."""

import secrets
from datetime import datetime, timezone, timedelta

import diskcache
from plone.registry.interfaces import IRegistry
from zope.component import getUtility

from zope.component import getAdapter

from ...interfaces import IFormsSettings, ITokenStore
from ...security import AuthTokenError, build_auth_token, validate_auth_token
from .http import json_error

TOKEN_CACHE_TTL_SECONDS = 24 * 60 * 60
TRUSTED_ACCESS_TOKEN_BYTES = 16


class AuthService:
    """Encapsulate auth token and trusted access validation for a form."""

    def __init__(self, context, request, form_id_getter):
        """Store request context and the callback used to resolve form IDs."""
        self.context = context
        self.request = request
        self._form_id_getter = form_id_getter

    def _form_id(self):
        """Return the current form identifier."""
        return self._form_id_getter()

    def _auth_settings(self):
        """Load auth-related registry settings."""
        registry = getUtility(IRegistry)
        return registry.forInterface(IFormsSettings, check=False)

    def trusted_access_enabled(self):
        """Return whether trusted access mode is enabled for the context."""
        mode = getattr(self.context, "access_mode", "") or "public"
        mode = str(mode).strip().lower()
        return mode in ("trusted", "trusted-tokens")

    def _trusted_access_cache_key(self, token):
        """Build the cache key used for trusted access tokens."""
        return f"trusted:{token}"

    def _trusted_access_ttl_seconds(self):
        """Return the trusted access token TTL in seconds."""
        hours = getattr(self.context, "trusted_access_ttl_hours", 168)
        try:
            hours_int = int(hours)
        except (TypeError, ValueError):
            hours_int = 168
        return max(hours_int, 1) * 60 * 60

    def _auth_token_enabled(self, settings):
        """Return whether authenticity tokens are enabled in settings."""
        return bool(getattr(settings, "authenticity_token_enabled", False))

    def _auth_token_secret(self, settings):
        """Return the configured authenticity token secret."""
        secret = getattr(settings, "authenticity_token_secret", "") or ""
        return str(secret).strip()

    def _auth_token_issuer(self, settings):
        """Return the configured token issuer."""
        issuer = getattr(settings, "authenticity_token_issuer", "") or ""
        return str(issuer).strip()

    def _auth_token_audience(self, settings):
        """Return the configured token audience."""
        audience = getattr(settings, "authenticity_token_audience", "") or ""
        return str(audience).strip()

    def _auth_token_ttl(self, settings):
        """Return the authenticity token TTL in seconds."""
        try:
            return int(getattr(settings, "authenticity_token_ttl_seconds", 600))
        except (TypeError, ValueError):
            return 600

    def _auth_token_cache_path(self, settings):
        """Return the diskcache path for token tracking."""
        path = getattr(settings, "authenticity_token_cache_path", "") or ""
        return str(path).strip() or "var/token_cache.db"

    def _token_cache(self, settings):
        """Open the token cache and return ``None`` if unavailable."""
        path = self._auth_token_cache_path(settings)
        try:
            cache = diskcache.Cache(path)
            return cache
        except Exception:
            return None

    def _cache_set(self, cache, token, value):
        """Store a token marker in the cache, ignoring cache failures."""
        try:
            cache.set(token, value, expire=TOKEN_CACHE_TTL_SECONDS)
        except Exception:
            return

    def _cache_add(self, cache, token, value):
        """Add a token marker once and report whether it was inserted."""
        try:
            return cache.add(token, value, expire=TOKEN_CACHE_TTL_SECONDS)
        except Exception:
            return False

    def _issued_cache_key(self, token):
        """Build the cache key for issued authenticity tokens."""
        return f"issued:{token}"

    def _received_cache_key(self, token):
        """Build the cache key for received authenticity tokens."""
        return f"received:{token}"

    def build_auth_token(self, form_version_id):
        """Create and record an authenticity token for a form version."""
        settings = self._auth_settings()
        if not self._auth_token_enabled(settings):
            return ""
        secret = self._auth_token_secret(settings)
        if not secret:
            return ""
        issuer = self._auth_token_issuer(settings)
        audience = self._auth_token_audience(settings)
        ttl_seconds = self._auth_token_ttl(settings)
        token = build_auth_token(
            form_id=self._form_id(),
            form_version=form_version_id or "",
            issuer=issuer,
            audience=audience,
            ttl_seconds=ttl_seconds,
            secret=secret,
        )
        cache = self._token_cache(settings)
        if cache is not None:
            try:
                self._cache_set(cache, self._issued_cache_key(token), "ISSUED")
            finally:
                cache.close()
        return token

    def issue_trusted_access_token(self, form_version_id):
        """Issue a single trusted-access token and persist its metadata."""
        settings = self._auth_settings()
        cache = self._token_cache(settings)
        if not cache:
            return None, None
        token = secrets.token_urlsafe(TRUSTED_ACCESS_TOKEN_BYTES)
        ttl_seconds = self._trusted_access_ttl_seconds()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        metadata = {
            "form_id": self._form_id(),
            "form_version": form_version_id,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
            "state": "ISSUED",
        }
        try:
            cache.set(
                self._trusted_access_cache_key(token),
                metadata,
                expire=ttl_seconds,
            )
        finally:
            cache.close()
        return token, metadata

    def _require_trusted_access_cached(self, token, logger=None):
        """Validate cached trusted access token (for 'trusted' mode)."""
        settings = self._auth_settings()
        cache = self._token_cache(settings)
        if not cache:
            if logger:
                logger.info("Survey trusted access denied: reason=cache_unavailable")
            json_error(
                self.request.response,
                503,
                "trusted_access_cache_unavailable",
            )
            return False
        try:
            metadata = cache.get(self._trusted_access_cache_key(token))
        finally:
            cache.close()
        if not isinstance(metadata, dict):
            if logger:
                logger.info("Survey trusted access denied: reason=invalid_token")
            json_error(
                self.request.response,
                403,
                "trusted_access_token_invalid",
            )
            return False
        if metadata.get("state") == "REVOKED":
            if logger:
                logger.info("Survey trusted access denied: reason=revoked_token")
            json_error(
                self.request.response,
                403,
                "trusted_access_token_revoked",
            )
            return False
        if metadata.get("form_id") != self._form_id():
            if logger:
                logger.info("Survey trusted access denied: reason=form_mismatch")
            json_error(
                self.request.response,
                403,
                "trusted_access_form_mismatch",
            )
            return False
        return True

    def _get_token_from_request(self):
        """Get token from request parameters.

        Checks for 'tt' (trusted token, used by token store) or 'access_token' (used by cached tokens).
        """
        # Check for tt first (token store uses this)
        token = self.request.form.get("tt") or self.request.get("tt") or ""
        if token:
            return str(token).strip()

        # Fallback to access_token (cached trusted tokens use this)
        token = (
            self.request.form.get("access_token")
            or self.request.get("access_token")
            or ""
        )
        return str(token).strip()

    def _require_trusted_access_tokens(self, token, logger=None):
        """Validate token using ITokenStore (for 'trusted-tokens' mode)."""
        try:
            token_store = getAdapter(self.context, ITokenStore)
        except Exception:
            if logger:
                logger.info(
                    "Survey trusted-tokens access denied: reason=token_store_unavailable"
                )
            json_error(
                self.request.response,
                503,
                "trusted_tokens_store_unavailable",
            )
            return False

        if not token_store.has_token(token):
            if logger:
                logger.info(
                    "Survey trusted-tokens access denied: reason=invalid_or_used_token"
                )
            json_error(
                self.request.response,
                403,
                "trusted_tokens_token_invalid",
            )
            return False

        # Do not invalidate here; consume on successful submission.
        if logger:
            logger.info("Survey trusted-tokens access: token_valid token=%s", token)
        return True

    def require_trusted_access(self, logger=None):
        """Validate trusted access token requirements for the current request."""
        if not self.trusted_access_enabled():
            return True

        token = self._get_token_from_request()
        if not token:
            if logger:
                logger.info("Survey trusted access denied: reason=missing_token")
            json_error(
                self.request.response,
                403,
                "trusted_access_token_missing",
            )
            return False

        # Determine which mode is active
        mode = getattr(self.context, "access_mode", "") or "public"
        mode = str(mode).strip().lower()

        if mode == "trusted-tokens":
            return self._require_trusted_access_tokens(token, logger=logger)
        else:
            # Original 'trusted' mode with cached tokens
            return self._require_trusted_access_cached(token, logger=logger)

    def trusted_access_token_from_request(self):
        """Return the trusted access token from the request, if any."""
        return self._get_token_from_request()

    def consume_trusted_access_token(self, logger=None):
        """Invalidate a trusted token after successful submission."""
        mode = getattr(self.context, "access_mode", "") or "public"
        mode = str(mode).strip().lower()
        if mode != "trusted-tokens":
            return True

        token = self._get_token_from_request()
        if not token:
            if logger:
                logger.info(
                    "Survey trusted-tokens consume denied: reason=missing_token"
                )
            json_error(
                self.request.response,
                403,
                "trusted_access_token_missing",
            )
            return False

        try:
            token_store = getAdapter(self.context, ITokenStore)
        except Exception:
            if logger:
                logger.info(
                    "Survey trusted-tokens consume denied: reason=token_store_unavailable"
                )
            json_error(
                self.request.response,
                503,
                "trusted_tokens_store_unavailable",
            )
            return False

        # Invalidate with reason for audit trail
        if not token_store.invalidate(token, reason="user_submission"):
            if logger:
                logger.info(
                    "Survey trusted-tokens consume denied: reason=invalid_or_used_token"
                )
            json_error(
                self.request.response,
                403,
                "trusted_tokens_token_invalid",
            )
            return False

        if logger:
            logger.info("Survey trusted-tokens access: token_consumed token=%s", token)
        return True

    def require_auth_token(self, form_version_id, logger=None):
        """Validate the submitted authenticity token and block replay."""
        settings = self._auth_settings()
        if not self._auth_token_enabled(settings):
            return True
        secret = self._auth_token_secret(settings)
        if not secret:
            json_error(
                self.request.response,
                500,
                "auth_token_config_missing",
            )
            return False
        token = self.request.form.get("auth_token") or ""
        if logger:
            logger.info("Survey auth token received: token=%s", token)
        issuer = self._auth_token_issuer(settings)
        audience = self._auth_token_audience(settings)
        try:
            payload = validate_auth_token(
                token=token,
                form_id=self._form_id(),
                form_version=form_version_id or "",
                issuer=issuer,
                audience=audience,
                secret=secret,
            )
            if logger:
                logger.info("Survey auth token validated: payload=%s", payload)
        except AuthTokenError as exc:
            if logger:
                logger.info(
                    "Survey auth token validation failed: reason=%s status=%s",
                    exc.reason,
                    exc.status,
                )
            json_error(
                self.request.response,
                exc.status,
                exc.reason,
            )
            return False
        cache = self._token_cache(settings)
        if cache is None:
            # FAIL CLOSED: reject request when replay protection is unavailable
            if logger:
                logger.error("Survey auth token cache unavailable - rejecting request")
            json_error(
                self.request.response,
                503,
                "auth_service_unavailable",
            )
            return False
        try:
            received_key = self._received_cache_key(token)
            added = self._cache_add(cache, received_key, "RECEIVED")
            if not added:
                if logger:
                    logger.info("Survey auth token replay detected: token=%s", token)
                json_error(
                    self.request.response,
                    403,
                    "auth_token_replay",
                )
                return False
        finally:
            cache.close()
        return True
