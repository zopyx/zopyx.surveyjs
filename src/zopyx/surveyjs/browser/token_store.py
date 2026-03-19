import csv
import io
import json
import logging
from datetime import datetime, timezone

import plone.api
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from .views import Views
from zope.annotation.interfaces import IAnnotations
from persistent.mapping import PersistentMapping
from persistent.dict import PersistentDict

from .. import _
from ..constants import TOKENS_KEY
from ..permissions import ManagePortal
from .services.http import json_response

logger = logging.getLogger(__name__)


class TokenStore(Views):
    """Browser view for managing survey access tokens via CSV upload.
    
    Tokens are stored in an annotation on the Survey object as:
    {token: {used: False, used_date: None, revoked: False}}
    """

    index = ViewPageTemplateFile("token_store.pt")

    def __call__(self):
        if not self.can_manage_portal:
            self.request.response.setStatus(403)
            return _("You are not allowed to access this view.")

        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            action = self.request.form.get("action", "upload")
            logger.debug("TokenStore POST action=%s", action)
            if action == "delete":
                return self.handle_delete()
            elif action == "clear_all":
                return self.handle_clear_all()
            elif action == "upload":
                return self.handle_upload()
            else:
                logger.warning("Unknown action: action=%s", action)
                plone.api.portal.show_message(
                    _("Invalid request"), request=self.request, type="error"
                )
                return self.request.response.redirect(self.request.getURL())

    def handle_clear_all(self):
        """Handle clear all tokens request."""
        confirm_text = self.request.form.get("confirm_text", "").strip()
        
        if confirm_text != "clear":
            plone.api.portal.show_message(
                _("Confirmation text does not match. Please type 'clear' to confirm."),
                request=self.request,
                type="error",
            )
            return self.index()
        
        # Verify CSRF token using plone.protect
        try:
            from plone.protect.authenticator import check
            check(self.request, name="_authenticator")
        except Exception as e:
            logger.warning("CSRF verification failed: %s", e)
            plone.api.portal.show_message(
                _("Invalid security token. Please try again."),
                request=self.request,
                type="error",
            )
            return self.index()
        
        annos = IAnnotations(self.context)
        if TOKENS_KEY in annos:
            annos[TOKENS_KEY] = PersistentMapping()
            logger.info(
                "All tokens cleared for survey=%s", self.context.absolute_url()
            )
        
        plone.api.portal.show_message(
            _("All tokens have been cleared successfully"),
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(self.request.getURL())
        return self.index()

    @property
    def can_manage_portal(self) -> bool:
        return plone.api.user.has_permission(ManagePortal, obj=self.context)

    def _get_tokens_annotation(self) -> PersistentMapping:
        """Get or initialize the tokens annotation as a persistent mapping."""
        annos = IAnnotations(self.context)
        if TOKENS_KEY not in annos:
            annos[TOKENS_KEY] = PersistentMapping()
        tokens = annos[TOKENS_KEY]
        # Ensure we have a persistent mapping (handle legacy plain dicts)
        if not isinstance(tokens, PersistentMapping):
            tokens = PersistentMapping(tokens)
            annos[TOKENS_KEY] = tokens
        return tokens

    @property
    def token_count(self) -> int:
        """Return the number of tokens stored."""
        tokens = self._get_tokens_annotation()
        return len(tokens)

    @property
    def tokens(self) -> dict:
        """Return all stored tokens."""
        return dict(self._get_tokens_annotation())

    def handle_upload(self):
        """Handle CSV file upload and merge tokens."""
        uploaded_file = self.request.form.get("csv_file")

        if not uploaded_file:
            plone.api.portal.show_message(
                _("No file uploaded"), request=self.request, type="error"
            )
            return self.index()

        try:
            file_content = uploaded_file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode("utf-8")
        except Exception as e:
            logger.exception("Token store upload decode error")
            plone.api.portal.show_message(
                _("Could not read file: ${error}", mapping={"error": str(e)}),
                request=self.request,
                type="error",
            )
            return self.index()

        new_tokens, errors = self._parse_csv(file_content)

        if errors:
            for error in errors:
                plone.api.portal.show_message(error, request=self.request, type="error")
            return self.index()

        if not new_tokens:
            plone.api.portal.show_message(
                _("No valid tokens found in CSV file"),
                request=self.request,
                type="warning",
            )
            return self.index()

        # Merge tokens into annotation (existing tokens are not modified)
        tokens = self._get_tokens_annotation()
        added_count = 0
        skipped_count = 0

        for token in new_tokens:
            if token not in tokens:
                # Use PersistentDict for individual token data
                tokens[token] = PersistentDict({
                    "used": False,
                    "used_date": None,
                    "revoked": False,
                })
                added_count += 1
            else:
                skipped_count += 1

        # Mark annotation as changed for ZODB
        tokens._p_changed = True

        logger.info(
            "Token store updated: added=%d skipped=%d total=%d survey=%s",
            added_count,
            skipped_count,
            len(tokens),
            self.context.absolute_url(),
        )

        plone.api.portal.show_message(
            _(
                "Tokens updated: ${added} added, ${skipped} already existed. "
                "Total tokens: ${total}",
                mapping={
                    "added": added_count,
                    "skipped": skipped_count,
                    "total": len(tokens),
                },
            ),
            request=self.request,
            type="info",
        )
        return self.request.response.redirect(self.request.getURL())

    def _parse_csv(self, content: str) -> tuple[list[str], list[str]]:
        """Parse CSV content and extract tokens.
        
        Returns a tuple of (tokens_list, error_messages).
        """
        tokens = []
        errors = []

        try:
            reader = csv.DictReader(io.StringIO(content))
        except csv.Error as e:
            return [], [_("Invalid CSV format: ${error}", mapping={"error": str(e)})]

        # Check for required column
        if reader.fieldnames is None:
            return [], [_("Could not detect CSV columns")]

        fieldnames = [f.lower().strip() for f in reader.fieldnames]
        if "tokens" not in fieldnames:
            errors.append(
                _(
                    "CSV must have a 'tokens' column. Found columns: ${columns}",
                    mapping={"columns": ", ".join(reader.fieldnames)},
                )
            )
            return [], errors

        # Find the actual column name (case-insensitive match)
        token_column = None
        for fname in reader.fieldnames:
            if fname.lower().strip() == "tokens":
                token_column = fname
                break

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
            token = row.get(token_column, "").strip()
            if not token:
                continue  # Skip empty rows
            
            # Basic validation - reject tokens with problematic characters
            if any(c in token for c in ['\n', '\r', '\t']):
                errors.append(
                    _(
                        "Row ${row}: Token contains invalid characters",
                        mapping={"row": row_num},
                    )
                )
                continue

            tokens.append(token)

        return tokens, errors

    def revoke_token(self, token: str) -> bool:
        """Revoke a token (mark as revoked)."""
        tokens = self._get_tokens_annotation()
        if token in tokens:
            tokens[token]["revoked"] = True
            tokens._p_changed = True
            return True
        return False

    def mark_token_used(self, token: str) -> bool:
        """Mark a token as used with timestamp."""
        tokens = self._get_tokens_annotation()
        if token in tokens and not tokens[token].get("used"):
            tokens[token]["used"] = True
            tokens[token]["used_date"] = datetime.now(timezone.utc).isoformat()
            tokens._p_changed = True
            return True
        return False

    def clear_all_tokens(self):
        """Clear all tokens from the annotation."""
        annos = IAnnotations(self.context)
        if TOKENS_KEY in annos:
            annos[TOKENS_KEY] = PersistentMapping()
            logger.info(
                "All tokens cleared for survey=%s", self.context.absolute_url()
            )

    def handle_delete(self):
        """Handle token deletion request."""
        token = self.request.form.get("token", "").strip()
        
        if not token:
            plone.api.portal.show_message(
                _("No token specified"), request=self.request, type="error"
            )
            return self.index()
        
        # Verify CSRF token using plone.protect
        authenticator = self.request.form.get("_authenticator", "")
        if not authenticator:
            plone.api.portal.show_message(
                _("Security token missing. Please try again."),
                request=self.request,
                type="error",
            )
            return self.index()
        
        try:
            from plone.protect.authenticator import check
            check(self.request, name="_authenticator")
        except Exception as e:
            logger.warning("CSRF verification failed: %s", e)
            plone.api.portal.show_message(
                _("Invalid security token. Please try again."),
                request=self.request,
                type="error",
            )
            return self.index()
        
        tokens = self._get_tokens_annotation()
        if token in tokens:
            del tokens[token]
            tokens._p_changed = True
            logger.info(
                "Token deleted: token=%s... survey=%s",
                token[:20] if len(token) > 20 else token,
                self.context.absolute_url()
            )
            plone.api.portal.show_message(
                _("Token deleted successfully"),
                request=self.request,
                type="info",
            )
        else:
            plone.api.portal.show_message(
                _("Token not found"),
                request=self.request,
                type="warning",
            )
        
        return self.request.response.redirect(self.request.getURL())
