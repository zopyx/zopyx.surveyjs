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


@implementer(ITokenStore)
class TokenStore:
    """Token store adapter for survey objects (ZODB backend).
    
    Tokens are stored as annotations on the survey object with the key
    'zopyx.surveyjs.token-store'. Each token is stored as a dict with:
    - token: The 32-character URL-safe token string
    - created: ISO format datetime when token was created
    - used: ISO format datetime when token was used (None if unused)
    """

    def _get_survey_path(self) -> str:
        """Get physical path of survey for logging."""
        try:
            return "/".join(self.survey.getPhysicalPath())
        except Exception:
            return str(self.survey)

    def __init__(self, survey):
        """Initialize the token store adapter.
        
        :param survey: The survey object being adapted
        """
        self.survey = survey
        self._annotations = IAnnotations(survey)
        self._backend = "ZODB"
        logger.debug("[TokenStore:%s] Initialized for survey %s", self._backend, self._get_survey_path())

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
        
        for _ in range(number):
            token = self._generate_token()
            storage[token] = {
                "token": token,
                "created": now,
                "used": None,
            }
            generated.append(token)
        
        logger.info("[TokenStore:%s] Generated %d tokens for survey %s", 
                    self._backend, number, self._get_survey_path())
        return generated

    def has_token(self, token: str) -> bool:
        """Check if a token exists and is valid (not used).
        
        :param token: Token string to check
        :return: True if token exists and is unused, False otherwise
        """
        storage = self._get_storage()
        if token not in storage:
            logger.debug("[TokenStore:%s] Token not found: %s...", self._backend, token[:8])
            return False
        is_valid = storage[token].get("used") is None
        logger.debug("[TokenStore:%s] Token check: %s... valid=%s", self._backend, token[:8], is_valid)
        return is_valid

    def invalidate(self, token: str) -> bool:
        """Invalidate a token (mark as used).
        
        :param token: Token string to invalidate
        :return: True if token was found and invalidated, False otherwise
        """
        storage = self._get_storage()
        if token not in storage:
            logger.warning("[TokenStore:%s] Invalidate failed - token not found: %s...", 
                          self._backend, token[:8])
            return False
        info = dict(storage[token])
        info["used"] = datetime.now(timezone.utc).isoformat()
        storage[token] = info
        logger.info("[TokenStore:%s] Token invalidated: %s...", self._backend, token[:8])
        return True

    def get_token_info(self, token: str) -> dict:
        """Get information about a specific token.
        
        :param token: Token string to look up
        :return: Token info dict with keys: token, created, used (or None if not found)
        """
        storage = self._get_storage()
        info = storage.get(token)
        if info is None:
            logger.debug("[TokenStore:%s] get_token_info - token not found: %s...", 
                        self._backend, token[:8])
            return None
        logger.debug("[TokenStore:%s] get_token_info - token found: %s...", 
                    self._backend, token[:8])
        return dict(info)

    def list_tokens(self) -> list:
        """List all tokens and their information.
        
        :return: List of token info dicts
        """
        storage = self._get_storage()
        tokens = [dict(info) for info in storage.values()]
        logger.debug("[TokenStore:%s] list_tokens - found %d tokens", self._backend, len(tokens))
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
        storage.clear()
        logger.info("[TokenStore:%s] Cleared %d tokens", self._backend, count)
