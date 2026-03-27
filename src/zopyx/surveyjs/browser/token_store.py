# -*- coding: utf-8 -*-
"""Token store browser view for managing survey access tokens."""

import csv
import io
from zope.component import getAdapter
from zope.interface import implementer
from zope.publisher.interfaces import IPublishTraverse
from plone import api
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from ..interfaces import ITokenStore
from .views import Views


@implementer(IPublishTraverse)
class TokenStoreView(Views):
    """Browser view for managing survey tokens."""

    # Define template at class level - standard Five pattern
    template = ViewPageTemplateFile("token_store.pt")

    def __init__(self, context, request):
        super().__init__(context, request)
        self.token_store = getAdapter(context, ITokenStore)

    def __call__(self):
        """Handle form submissions and render the template."""
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
        tokens = [
            t for t in self.token_store.list_tokens()
            if t.get("used") is None
        ]
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
