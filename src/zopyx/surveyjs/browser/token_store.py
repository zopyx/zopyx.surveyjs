# -*- coding: utf-8 -*-
"""Token store browser view for managing survey access tokens."""

import csv
import io
from zope.component import getAdapter
from zope.interface import implementer
from zope.publisher.interfaces import IPublishTraverse
from plone import api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from ..interfaces import ITokenStore


@implementer(IPublishTraverse)
class TokenStoreView(BrowserView):
    """Browser view for managing survey tokens."""

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

        # Handle CSV download
        if "download_csv" in form:
            return self.download_csv()

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

    def download_csv(self):
        """Generate and download CSV with unused tokens and URLs."""
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

        filename = f"{self.context.getId()}_tokens.csv"
        
        self.request.response.setHeader("Content-Type", "text/csv; charset=utf-8")
        self.request.response.setHeader(
            "Content-Disposition", f'attachment; filename="{filename}"'
        )
        return csv_content
