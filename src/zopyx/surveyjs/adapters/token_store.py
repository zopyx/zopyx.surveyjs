# -*- coding: utf-8 -*-
"""Token store adapter implementation for surveys."""

import logging
import secrets
from BTrees.OOBTree import OOBTree
from datetime import datetime, timezone
from zope.annotation.interfaces import IAnnotations
from zope.interface import implementer
from zopyx.surveyjs.constants import TOKEN_STORE_KEY
from zopyx.surveyjs.interfaces import ITokenStore

# Token generation: URL-safe base64, 32 characters
# token_urlsafe(24) produces 32 chars (base64 uses 4/3 ratio)

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger(f"{__name__}.audit")


@implementer(ITokenStore)
class TokenStore:
    """Token store adapter for survey objects (ZODB backend).

    Tokens are stored as annotations on the survey object with the key
    'zopyx.surveyjs.token-store'. Each token is stored as a dict with:
    - token: The 32-character URL-safe token string
    - created: ISO format datetime when token was created
    - used: ISO format datetime when token was used (None if unused)
    - used_by: User ID who used the token (optional)
    - used_from: IP address where token was used (optional)
    - revocation_reason: Reason for invalidation (optional)
    """

    def _get_survey_path(self) -> str:
        """Get physical path of survey for logging."""
        try:
            return "/".join(self.survey.getPhysicalPath())
        except Exception as e:
            logger.debug("Failed to get survey path: %s", e)
            return str(self.survey)

    def _get_user_context(self) -> dict:
        """Get current user context for audit logging.
        
        :return: Dict with user_id and client_ip
        """
        try:
            from plone import api
            user = api.user.get_current()
            user_id = user.getId() if user else "anonymous"
        except Exception as e:
            logger.debug("Failed to get user context: %s", e)
            user_id = "unknown"
        
        # Try to get client IP from request
        client_ip = "unknown"
        try:
            request = getattr(self.survey, 'REQUEST', None)
            if request:
                client_ip = request.getClientIP() or "unknown"
        except Exception as e:
            logger.debug("Failed to get client IP: %s", e)
        
        return {"user_id": user_id, "client_ip": client_ip}

    def __init__(self, survey):
        """Initialize the token store adapter.

        :param survey: The survey object being adapted
        """
        self.survey = survey
        self._annotations = IAnnotations(survey)
        self._backend = "ZODB"
        logger.debug(
            "[TokenStore:%s] Initialized for survey %s",
            self._backend,
            self._get_survey_path(),
        )

    def _get_storage(self) -> OOBTree:
        """Get or create the token storage OOBTree.

        :return: The token storage OOBTree (token -> info mapping)
        """
        if TOKEN_STORE_KEY not in self._annotations:
            self._annotations[TOKEN_STORE_KEY] = OOBTree()
        return self._annotations[TOKEN_STORE_KEY]

    def _generate_token(self) -> str:
        """Generate a single random token.

        :return: A 32-character URL-safe token
        """
        return secrets.token_urlsafe(24)

    def generate_tokens(self, number: int) -> list:
        """Generate a specified number of new tokens.

        :param number: Number of tokens to generate
        :return: List of generated token strings (32-char URL-safe)
        """
        storage = self._get_storage()
        generated = []
        now = datetime.now(timezone.utc).isoformat()
        user_context = self._get_user_context()

        for _ in range(number):
            token = self._generate_token()
            storage[token] = {
                "token": token,
                "created": now,
                "used": None,
            }
            generated.append(token)

        logger.info(
            "[TokenStore:%s] Generated %d tokens for survey %s",
            self._backend,
            number,
            self._get_survey_path(),
        )
        audit_logger.info(
            "TOKEN_GENERATED: survey=%s user=%s ip=%s count=%d",
            self._get_survey_path(),
            user_context["user_id"],
            user_context["client_ip"],
            number,
        )
        return generated

    def has_token(self, token: str) -> bool:
        """Check if a token exists and is valid (not used).

        :param token: Token string to check
        :return: True if token exists and is unused, False otherwise
        """
        storage = self._get_storage()
        if token not in storage:
            logger.debug(
                "[TokenStore:%s] Token not found: %s...", self._backend, token[:8]
            )
            return False
        is_valid = storage[token].get("used") is None
        logger.debug(
            "[TokenStore:%s] Token check: %s... valid=%s",
            self._backend,
            token[:8],
            is_valid,
        )
        return is_valid

    def invalidate(self, token: str, reason: str = None) -> bool:
        """Invalidate a token (mark as used).

        :param token: Token string to invalidate
        :param reason: Optional reason for invalidation (e.g., 'user_submission', 'admin_revoked')
        :return: True if token was found and invalidated, False otherwise
        """
        storage = self._get_storage()
        if token not in storage:
            logger.warning(
                "[TokenStore:%s] Invalidate failed - token not found: %s...",
                self._backend,
                token[:8],
            )
            return False
        
        user_context = self._get_user_context()
        info = dict(storage[token])
        info["used"] = datetime.now(timezone.utc).isoformat()
        info["used_by"] = user_context["user_id"]
        info["used_from"] = user_context["client_ip"]
        if reason:
            info["revocation_reason"] = reason
        storage[token] = info
        
        logger.info(
            "[TokenStore:%s] Token invalidated: %s...", self._backend, token[:8]
        )
        audit_logger.info(
            "TOKEN_INVALIDATED: survey=%s token=%s... user=%s ip=%s reason=%s",
            self._get_survey_path(),
            token[:8],
            user_context["user_id"],
            user_context["client_ip"],
            reason or "user_submission",
        )
        return True

    def get_token_info(self, token: str) -> dict:
        """Get information about a specific token.

        :param token: Token string to look up
        :return: Token info dict with keys: token, created, used (or None if not found)
        """
        storage = self._get_storage()
        info = storage.get(token)
        if info is None:
            logger.debug(
                "[TokenStore:%s] get_token_info - token not found: %s...",
                self._backend,
                token[:8],
            )
            return None
        logger.debug(
            "[TokenStore:%s] get_token_info - token found: %s...",
            self._backend,
            token[:8],
        )
        return dict(info)

    def list_tokens(self) -> list:
        """List all tokens and their information.

        :return: List of token info dicts
        """
        storage = self._get_storage()
        tokens = [dict(info) for info in storage.values()]
        logger.debug(
            "[TokenStore:%s] list_tokens - found %d tokens", self._backend, len(tokens)
        )
        return tokens

    def get_stats(self) -> dict:
        """Get token statistics.

        :return: Dict with total, used, and unused token counts
        """
        tokens = self.list_tokens()
        total = len(tokens)
        used = sum(1 for t in tokens if t.get("used") is not None)
        unused = total - used
        stats = {
            "total": total,
            "used": used,
            "unused": unused,
        }
        logger.debug("[TokenStore:%s] get_stats: %s", self._backend, stats)
        return stats

    def clear(self) -> None:
        """Clear all tokens from the store."""
        storage = self._get_storage()
        count = len(storage)
        user_context = self._get_user_context()
        storage.clear()
        logger.info("[TokenStore:%s] Cleared %d tokens", self._backend, count)
        audit_logger.info(
            "TOKENS_CLEARED: survey=%s user=%s ip=%s count=%d",
            self._get_survey_path(),
            user_context["user_id"],
            user_context["client_ip"],
            count,
        )

    def import_tokens(self, tokens: list) -> dict:
        """Import a list of tokens into the store.

        :param tokens: List of token strings to import
        :return: Dict with 'imported' count and 'skipped' list (duplicates/invalid)
        """
        storage = self._get_storage()
        imported = 0
        skipped = []
        now = datetime.now(timezone.utc).isoformat()
        user_context = self._get_user_context()

        for token in tokens:
            # Skip if token already exists
            if token in storage:
                skipped.append({"token": token, "reason": "duplicate"})
                continue

            # Store the token
            storage[token] = {
                "token": token,
                "created": now,
                "used": None,
            }
            imported += 1

        logger.info(
            "[TokenStore:%s] Imported %d tokens, skipped %d for survey %s",
            self._backend,
            imported,
            len(skipped),
            self._get_survey_path(),
        )
        audit_logger.info(
            "TOKENS_IMPORTED: survey=%s user=%s ip=%s imported=%d skipped=%d",
            self._get_survey_path(),
            user_context["user_id"],
            user_context["client_ip"],
            imported,
            len(skipped),
        )
        return {"imported": imported, "skipped": skipped}
