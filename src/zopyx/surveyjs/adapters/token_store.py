# -*- coding: utf-8 -*-
"""Token store adapter implementation for surveys."""

from BTrees.OOBTree import OOBTree
from datetime import datetime, timezone
from uuid import uuid4
from zope.annotation.interfaces import IAnnotations
from zope.interface import implementer
from zopyx.surveyjs.constants import TOKEN_STORE_KEY
from zopyx.surveyjs.interfaces import ITokenStore


@implementer(ITokenStore)
class TokenStore:
    """Token store adapter for survey objects.
    
    Tokens are stored as annotations on the survey object with the key
    'zopyx.surveyjs.token-store'. Each token is stored as a dict with:
    - token: The UUID4 token string
    - created: ISO format datetime when token was created
    - used: ISO format datetime when token was used (None if unused)
    """

    def __init__(self, survey):
        """Initialize the token store adapter.
        
        :param survey: The survey object being adapted
        """
        self.survey = survey
        self._annotations = IAnnotations(survey)

    def _get_storage(self) -> OOBTree:
        """Get or create the token storage OOBTree.
        
        :return: The token storage OOBTree (token -> info mapping)
        """
        if TOKEN_STORE_KEY not in self._annotations:
            self._annotations[TOKEN_STORE_KEY] = OOBTree()
        return self._annotations[TOKEN_STORE_KEY]

    def generate_tokens(self, number: int) -> list:
        """Generate a specified number of new tokens.
        
        :param number: Number of tokens to generate
        :return: List of generated token strings (UUID4)
        """
        storage = self._get_storage()
        generated = []
        now = datetime.now(timezone.utc).isoformat()
        
        for _ in range(number):
            token = str(uuid4())
            storage[token] = {
                "token": token,
                "created": now,
                "used": None,
            }
            generated.append(token)
        
        return generated

    def has_token(self, token: str) -> bool:
        """Check if a token exists and is valid (not used).
        
        :param token: Token string to check
        :return: True if token exists and is unused, False otherwise
        """
        storage = self._get_storage()
        if token not in storage:
            return False
        return storage[token].get("used") is None

    def invalidate(self, token: str) -> bool:
        """Invalidate a token (mark as used).
        
        :param token: Token string to invalidate
        :return: True if token was found and invalidated, False otherwise
        """
        storage = self._get_storage()
        if token not in storage:
            return False
        
        storage[token]["used"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_token_info(self, token: str) -> dict:
        """Get information about a specific token.
        
        :param token: Token string to look up
        :return: Token info dict with keys: token, created, used (or None if not found)
        """
        storage = self._get_storage()
        info = storage.get(token)
        if info is None:
            return None
        return dict(info)

    def list_tokens(self) -> list:
        """List all tokens and their information.
        
        :return: List of token info dicts
        """
        storage = self._get_storage()
        return [dict(info) for info in storage.values()]

    def clear(self) -> None:
        """Clear all tokens from the store."""
        storage = self._get_storage()
        storage.clear()
