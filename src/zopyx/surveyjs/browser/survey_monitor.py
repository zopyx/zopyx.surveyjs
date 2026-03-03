# -*- coding: utf-8 -*-
"""Browser view for survey submission monitoring dashboard."""

import json
from datetime import datetime, timezone

from Products.Five import BrowserView
from zope.interface import Interface

from ..monitoring import (
    TIME_WINDOWS,
    check_rate_limit,
    cleanup_old_data,
    get_submission_stats,
)


class ISurveyMonitorView(Interface):
    """Marker interface for survey monitor view."""


class SurveyMonitorView(BrowserView):
    """Monitoring dashboard for survey submissions.
    
    Provides real-time statistics and graphs for survey submission rates
    with configurable time windows.
    """

    def __init__(self, context, request):
        super().__init__(context, request)
        self.time_window = "1h"
    
    def __call__(self):
        """Handle GET requests with optional time window parameter."""
        # Get time window from request
        requested_window = self.request.form.get("window", "1h")
        if requested_window in TIME_WINDOWS:
            self.time_window = requested_window
        
        # Handle cleanup action
        if self.request.form.get("action") == "cleanup":
            return self._do_cleanup()
        
        # Handle JSON API
        if self.request.form.get("format") == "json":
            return self._json_response()
        
        # Render template
        return self.index()
    
    def _json_response(self):
        """Return stats as JSON for AJAX updates."""
        stats = get_submission_stats(self.time_window)
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps(stats)
    
    def _do_cleanup(self):
        """Clean up old monitoring data."""
        removed = cleanup_old_data()
        self.request.response.redirect(
            f"{self.context.absolute_url()}/@@survey-monitor?cleanup_done={removed}"
        )
    
    @property
    def available_windows(self):
        """Return available time window options."""
        labels = {
            "5m": "Last 5 minutes",
            "10m": "Last 10 minutes",
            "20m": "Last 20 minutes",
            "1h": "Last hour",
            "2h": "Last 2 hours",
            "6h": "Last 6 hours",
            "12h": "Last 12 hours",
            "24h": "Last 24 hours",
        }
        return [
            {"value": k, "label": labels.get(k, k), "selected": k == self.time_window}
            for k in TIME_WINDOWS.keys()
        ]
    
    def get_stats(self):
        """Get submission statistics for the current time window."""
        return get_submission_stats(self.time_window)
    
    def get_rate_limit_status(self):
        """Get current rate limit status."""
        is_allowed, info = check_rate_limit()
        return info
    
    def get_chart_data(self):
        """Get time series data formatted for charts."""
        stats = get_submission_stats(self.time_window)
        time_series = stats.get("time_series", {})
        
        if not time_series:
            return {"labels": [], "values": []}
        
        labels = list(time_series.keys())
        values = list(time_series.values())
        
        return {"labels": labels, "values": values}
    
    def get_chart_data_json(self):
        """Get chart data as JSON string for template embedding."""
        return json.dumps(self.get_chart_data())
    
    def get_current_time(self):
        """Return current server time."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    def get_cache_path(self):
        """Return the path to the monitoring cache."""
        from ..monitoring import _get_cache_dir
        return _get_cache_dir()
