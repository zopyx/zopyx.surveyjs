# -*- coding: utf-8 -*-
"""Token store browser view for managing survey access tokens."""

import csv
import io
from AccessControl import getSecurityManager
from zope.component import getAdapter
from zope.interface import implementer
from zope.publisher.interfaces import IPublishTraverse
from plone import api
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from ..interfaces import ITokenStore
from ..permissions import ModifyPortalContent
from .views import Views


@implementer(IPublishTraverse)
class TokenStoreView(Views):
    """Browser view for managing survey tokens."""

    # Define template at class level - standard Five pattern
    template = ViewPageTemplateFile("token_store.pt")

    def __init__(self, context, request):
        super().__init__(context, request)
        self.token_store = getAdapter(context, ITokenStore)

    def _check_permission(self):
        """Check if the current user has permission to manage tokens.

        :return: True if user has ModifyPortalContent permission
        :raises: Unauthorized if user lacks permission
        """
        sm = getSecurityManager()
        if not sm.checkPermission(ModifyPortalContent, self.context):
            from AccessControl import Unauthorized

            raise Unauthorized("You are not allowed to manage tokens for this survey.")
        return True

    def __call__(self, REQUEST=None):
        """Handle form submissions and render the template."""
        # Verify user has permission before processing any action
        self._check_permission()

        # Only validate CSRF token on POST requests
        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            from plone.protect import CheckAuthenticator

            CheckAuthenticator(self.request)

        form = self.request.form

        # Handle token generation
        if "generate_tokens" in form:
            try:
                num_tokens = int(form.get("num_tokens", 0))
                if num_tokens > 0:
                    self.token_store.generate_tokens(num_tokens)
                    api.portal.show_message(
                        f"Generated {num_tokens} new token(s).",
                        request=self.request,
                        type="info",
                    )
                else:
                    api.portal.show_message(
                        "Please enter a positive number.",
                        request=self.request,
                        type="error",
                    )
            except ValueError:
                api.portal.show_message(
                    "Invalid number entered.",
                    request=self.request,
                    type="error",
                )
            return self.request.response.redirect(self.request.URL)

        # Handle CSV download (valid/only unused tokens)
        if "download_valid_tokens" in form:
            return self.download_valid_tokens()

        # Handle CSV download (all tokens with timestamps)
        if "download_all_tokens" in form:
            return self.download_all_tokens()

        # Handle clear tokens
        if "clear_tokens" in form:
            self.token_store.clear()
            api.portal.show_message(
                "All tokens have been cleared.",
                request=self.request,
                type="info",
            )
            return self.request.response.redirect(self.request.URL)

        # Handle CSV import
        if "import_csv" in form:
            return self.handle_csv_import()

        return self.template()

    def get_stats(self):
        """Get token statistics.

        :return: Dict with total, used, and unused token counts
        """
        tokens = self.token_store.list_tokens()
        total = len(tokens)
        used = sum(1 for t in tokens if t.get("used") is not None)
        unused = total - used
        return {
            "total": total,
            "used": used,
            "unused": unused,
        }

    def get_survey_url(self):
        """Get the base survey URL."""
        return self.context.absolute_url()

    def download_valid_tokens(self):
        """Generate and download CSV with unused (valid) tokens and URLs."""
        tokens = [t for t in self.token_store.list_tokens() if t.get("used") is None]
        base_url = self.context.absolute_url()

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["token", "url"])

        # Write data rows
        for token_info in tokens:
            token = token_info["token"]
            url = f"{base_url}?tt={token}"
            writer.writerow([token, url])

        # Prepare response
        csv_content = output.getvalue()
        output.close()

        filename = f"{self.context.getId()}_valid_tokens.csv"

        self.request.response.setHeader("Content-Type", "text/csv; charset=utf-8")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        return csv_content

    def handle_csv_import(self):
        """Handle CSV file upload and token import."""
        form = self.request.form
        csv_file = form.get("csv_file")

        if not csv_file:
            api.portal.show_message(
                "No file uploaded.",
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.request.URL)

        # Check file type
        content_type = getattr(csv_file, "contentType", "")
        filename = getattr(csv_file, "filename", "")
        if not (
            content_type in ("text/csv", "text/plain", "application/vnd.ms-excel")
            or filename.endswith(".csv")
        ):
            api.portal.show_message(
                "Invalid file type. Please upload a CSV file.",
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.request.URL)

        try:
            # Read and parse CSV
            file_content = csv_file.read()
            if isinstance(file_content, bytes):
                file_content = file_content.decode("utf-8")

            if not file_content.strip():
                api.portal.show_message(
                    "CSV file is empty.",
                    request=self.request,
                    type="error",
                )
                return self.request.response.redirect(self.request.URL)

            csv_reader = csv.DictReader(io.StringIO(file_content))

            # Check for token column
            if "token" not in csv_reader.fieldnames:
                api.portal.show_message(
                    "CSV must contain a 'token' column.",
                    request=self.request,
                    type="error",
                )
                return self.request.response.redirect(self.request.URL)

            # Collect and validate tokens
            tokens_to_import = []
            row_num = 1
            errors = []

            for row in csv_reader:
                row_num += 1
                token = row.get("token", "").strip()

                if not token:
                    continue  # Skip empty rows

                if len(token) < 8:
                    errors.append(f"Row {row_num}: token is too short (min 8 chars)")
                    continue

                tokens_to_import.append(token)

            if errors:
                # Show first few errors
                error_msg = "; ".join(errors[:3])
                if len(errors) > 3:
                    error_msg += f" (and {len(errors) - 3} more)"
                api.portal.show_message(
                    f"Validation errors: {error_msg}",
                    request=self.request,
                    type="error",
                )
                return self.request.response.redirect(self.request.URL)

            if not tokens_to_import:
                api.portal.show_message(
                    "No valid tokens found in CSV.",
                    request=self.request,
                    type="error",
                )
                return self.request.response.redirect(self.request.URL)

            # Import tokens
            result = self.token_store.import_tokens(tokens_to_import)
            imported_count = result["imported"]
            skipped_count = len(result["skipped"])

            # Build success message
            if skipped_count > 0:
                msg = f"{imported_count} token(s) imported successfully ({skipped_count} duplicate(s) skipped)."
            else:
                msg = f"{imported_count} token(s) imported successfully."

            api.portal.show_message(
                msg,
                request=self.request,
                type="info",
            )
            return self.request.response.redirect(self.request.URL)

        except csv.Error as e:
            api.portal.show_message(
                f"CSV parsing error: {str(e)}",
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.request.URL)
        except Exception as e:
            api.portal.show_message(
                f"Error importing tokens: {str(e)}",
                request=self.request,
                type="error",
            )
            return self.request.response.redirect(self.request.URL)

    def download_all_tokens(self):
        """Generate and download CSV with all tokens and full metadata."""
        tokens = self.token_store.list_tokens()
        base_url = self.context.absolute_url()

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header with all metadata fields
        writer.writerow(["token", "url", "created", "used", "status"])

        # Write data rows
        for token_info in tokens:
            token = token_info["token"]
            url = f"{base_url}?tt={token}"
            created = token_info.get("created", "")
            used = token_info.get("used") or ""
            status = "used" if token_info.get("used") else "unused"
            writer.writerow([token, url, created, used, status])

        # Prepare response
        csv_content = output.getvalue()
        output.close()

        filename = f"{self.context.getId()}_all_tokens.csv"

        self.request.response.setHeader("Content-Type", "text/csv; charset=utf-8")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        return csv_content
