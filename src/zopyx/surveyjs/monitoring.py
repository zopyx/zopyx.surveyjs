# -*- coding: utf-8 -*-
"""Monitoring system for survey submissions.

This module provides rate limiting and usage statistics for survey submissions
using diskcache for efficient time-series data storage.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from zope.component.hooks import getSite

try:
    from diskcache import Cache
except ImportError:
    Cache = None

logger = logging.getLogger(__name__)

# Cache key prefixes
SUBMISSION_KEY_PREFIX = "sub:"
FORM_STATS_PREFIX = "form:"
DURATION_KEY_PREFIX = "duration:"
FORM_DURATION_PREFIX = "form-duration:"
GLOBAL_STATS_KEY = "global:stats"

# Time windows in minutes
TIME_WINDOWS = {
    "5m": 5,
    "10m": 10,
    "20m": 20,
    "1h": 60,
    "2h": 120,
    "6h": 360,
    "12h": 720,
    "24h": 1440,
}


def _get_cache_dir() -> str:
    """Get the cache directory for monitoring data."""
    try:
        site = getSite()
        if site is not None:
            # Store in var/surveyjs-monitor relative to instance
            instance_home = os.environ.get("INSTANCE_HOME", "")
            if instance_home:
                cache_dir = Path(instance_home) / "var" / "surveyjs-monitor"
            else:
                # Fallback to temp directory with site ID
                site_id = site.getId()
                cache_dir = Path("/tmp") / f"surveyjs-monitor-{site_id}"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return str(cache_dir)
    except Exception:
        pass
    # Final fallback
    return "/tmp/surveyjs-monitor"


def _get_cache() -> Optional[Cache]:
    """Get or create the diskcache instance."""
    if Cache is None:
        return None
    try:
        cache_dir = _get_cache_dir()
        return Cache(cache_dir, timeout=5)
    except Exception as exc:
        logger.warning("Failed to initialize monitoring cache: %s", exc)
        return None


def _make_submission_key(timestamp: datetime) -> str:
    """Create a cache key for a submission timestamp."""
    # Round to minute for efficient bucketing
    minute_key = timestamp.strftime("%Y%m%d%H%M")
    return f"{SUBMISSION_KEY_PREFIX}{minute_key}"


def _make_form_key(form_uid: str, timestamp: datetime) -> str:
    """Create a cache key for form-specific stats."""
    minute_key = timestamp.strftime("%Y%m%d%H%M")
    return f"{FORM_STATS_PREFIX}{form_uid}:{minute_key}"


def record_submission(context, event) -> None:
    """Event subscriber to record survey submission for monitoring.

    This subscriber listens to ISurveyJSFormSubmittedEvent and records
    submission timestamps for rate limiting and statistics.
    """
    cache = _get_cache()
    if cache is None:
        return

    try:
        now = datetime.now(timezone.utc)
        form_uid = _get_form_uid(context)

        # Get form metadata
        form_title = _get_form_title(context)
        form_path = _get_form_path(context)

        # Get submission data from event
        form_data = getattr(event, "form_data", {}) or {}
        poll_id = form_data.get("poll_id", "unknown")
        user = form_data.get("user", "anonymous")

        # Record global submission
        submission_key = _make_submission_key(now)
        _increment_counter(cache, submission_key, now, poll_id, user)

        # Record form-specific submission
        form_key = _make_form_key(form_uid, now)
        _increment_counter(
            cache,
            form_key,
            now,
            poll_id,
            user,
            form_uid=form_uid,
            form_title=form_title,
            form_path=form_path,
        )

        logger.debug(
            "Recorded submission for monitoring: %s on %s", poll_id, form_title
        )

    except Exception as exc:
        # Fail silently - monitoring should not break submissions
        logger.debug("Failed to record submission for monitoring: %s", exc)
    finally:
        try:
            cache.close()
        except Exception:
            pass


def _increment_counter(
    cache: Cache,
    key: str,
    timestamp: datetime,
    poll_id: str,
    user: str,
    form_uid: Optional[str] = None,
    form_title: Optional[str] = None,
    form_path: Optional[str] = None,
) -> None:
    """Increment a counter in the cache with submission details."""
    try:
        # Get existing data or create new
        data = cache.get(key, {})
        if not isinstance(data, dict):
            data = {}

        # Increment count
        data["count"] = data.get("count", 0) + 1
        data["timestamp"] = timestamp.isoformat()

        # Store poll IDs (limited to last 100)
        poll_ids = data.get("poll_ids", [])
        poll_ids.append(poll_id)
        data["poll_ids"] = poll_ids[-100:]

        # Store users (limited to last 100 unique)
        users = data.get("users", [])
        if user not in users:
            users.append(user)
        data["users"] = users[-100:]

        if form_uid:
            data["form_uid"] = form_uid
        if form_title:
            data["form_title"] = form_title
        if form_path:
            data["form_path"] = form_path

        # Store with expiration (25 hours to cover all time windows)
        cache.set(key, data, expire=25 * 3600)

    except Exception as exc:
        logger.debug("Failed to increment counter: %s", exc)


def record_submission_duration(context, seconds: float) -> None:
    """Record the server-side processing time of an accepted submission.

    Called from the save-poll view right after the submission event fired.
    Stores per-minute latency buckets (count/sum/min/max) both globally and
    per form, so average and worst-case processing time can be charted.
    """
    cache = _get_cache()
    if cache is None:
        return

    try:
        now = datetime.now(timezone.utc)
        minute_key = now.strftime("%Y%m%d%H%M")

        _record_duration_bucket(
            cache, f"{DURATION_KEY_PREFIX}{minute_key}", seconds
        )
        _record_duration_bucket(
            cache,
            f"{FORM_DURATION_PREFIX}{_get_form_uid(context)}:{minute_key}",
            seconds,
            form_uid=_get_form_uid(context),
            form_title=_get_form_title(context),
            form_path=_get_form_path(context),
        )
    except Exception as exc:
        logger.debug("Failed to record submission duration: %s", exc)
    finally:
        try:
            cache.close()
        except Exception:
            pass


def _record_duration_bucket(
    cache: Cache,
    key: str,
    seconds: float,
    form_uid: Optional[str] = None,
    form_title: Optional[str] = None,
    form_path: Optional[str] = None,
) -> None:
    """Increment a per-minute latency bucket with the given duration."""
    try:
        data = cache.get(key, {})
        if not isinstance(data, dict):
            data = {}

        count = data.get("count", 0) + 1
        total = data.get("sum", 0.0) + seconds
        data.update(
            {
                "count": count,
                "sum": total,
                "avg": total / count,
                "min": min(data.get("min", seconds), seconds),
                "max": max(data.get("max", seconds), seconds),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if form_uid:
            data["form_uid"] = form_uid
        if form_title:
            data["form_title"] = form_title
        if form_path:
            data["form_path"] = form_path

        cache.set(key, data, expire=25 * 3600)
    except Exception as exc:
        logger.debug("Failed to record duration bucket: %s", exc)


def _get_form_uid(context) -> str:
    """Get a unique identifier for the survey form."""
    uid = getattr(context, "UID", None)
    if callable(uid):
        try:
            return uid()
        except Exception:
            pass
    try:
        return "/".join(context.getPhysicalPath())
    except Exception:
        return repr(context)


def _get_form_title(context) -> str:
    """Get the title of the survey form."""
    title = getattr(context, "Title", None)
    if callable(title):
        try:
            return title() or "Untitled"
        except Exception:
            pass
    return getattr(context, "title", "Untitled") or "Untitled"


def _get_form_path(context) -> str:
    """Get the relative path of the survey form."""
    try:
        site = getSite()
        site_path = "/".join(site.getPhysicalPath())
        obj_path = "/".join(context.getPhysicalPath())
        if obj_path.startswith(site_path):
            return obj_path[len(site_path) :] or "/"
        return obj_path
    except Exception:
        return "/"


def _generate_full_time_series(
    minutes: int, now: datetime, time_series: Dict[str, int]
) -> Dict[str, int]:
    """Generate a complete time series with zeros for the entire window.

    Args:
        minutes: Time window in minutes
        now: Current datetime
        time_series: Dict with actual submission counts by time

    Returns:
        Complete time series with all time slots filled (zeros where no data)
    """
    full_series: Dict[str, int] = {}

    for i in range(minutes, -1, -1):
        slot_time = now - timedelta(minutes=i)
        time_key = slot_time.strftime("%H:%M")
        full_series[time_key] = time_series.get(time_key, 0)

    return full_series


def _get_form_time_series(
    cache: Cache,
    cutoff: datetime,
    minutes: int,
    now: datetime,
) -> List[Dict]:
    """Build per-form per-minute series aligned to the full time window.

    Returns a list of dicts (one per form that submitted in the window,
    sorted by total count descending)::

        {
            "form_uid": str,
            "title": str,
            "path": str,
            "count": int,               # total in window
            "series": {time_key: count} # full window, zero-filled
        }
    """
    raw: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: Dict[str, int] = defaultdict(int)
    titles: Dict[str, str] = {}
    paths: Dict[str, str] = {}

    for key in cache.iterkeys():
        if not key.startswith(FORM_STATS_PREFIX):
            continue
        try:
            data = cache.get(key)
            if not data or not isinstance(data, dict):
                continue
            form_uid = data.get("form_uid")
            if not form_uid:
                continue
            ts_part = key[len(FORM_STATS_PREFIX) :]
            if ":" not in ts_part:
                continue
            _, ts_str = ts_part.rsplit(":", 1)
            key_time = datetime.strptime(ts_str, "%Y%m%d%H%M").replace(
                tzinfo=timezone.utc
            )
            if key_time < cutoff:
                continue
            time_key = key_time.strftime("%H:%M")
            count = data.get("count", 0)
            raw[form_uid][time_key] += count
            totals[form_uid] += count
            if form_uid not in titles:
                titles[form_uid] = data.get("form_title", "Untitled")
            if form_uid not in paths:
                paths[form_uid] = data.get("form_path", "/")
        except Exception:
            continue

    result = []
    for form_uid, series in raw.items():
        result.append(
            {
                "form_uid": form_uid,
                "title": titles.get(form_uid, "Untitled"),
                "path": paths.get(form_uid, "/"),
                "count": totals.get(form_uid, 0),
                "series": _generate_full_time_series(minutes, now, dict(series)),
            }
        )
    result.sort(key=lambda f: f["count"], reverse=True)
    return result


def _generate_full_duration_series(
    minutes: int, now: datetime, duration_series: Dict[str, Dict]
) -> Dict[str, Optional[Dict]]:
    """Align per-minute latency data to the full window.

    Minutes without recorded submissions map to ``None`` (chart gap),
    minutes with data carry ``{"avg": float, "max": float, "count": int}``.
    """
    full_series: Dict[str, Optional[Dict]] = {}

    for i in range(minutes, -1, -1):
        slot_time = now - timedelta(minutes=i)
        time_key = slot_time.strftime("%H:%M")
        full_series[time_key] = duration_series.get(time_key)

    return full_series


def get_submission_stats(time_window: str = "1h") -> Dict:
    """Get submission statistics for the specified time window.

    Args:
        time_window: One of 5m, 10m, 20m, 1h, 2h, 6h, 12h, 24h

    Returns:
        Dictionary with stats including total count, per-form breakdown,
        per-minute time series, and unique users.
    """
    cache = _get_cache()
    if cache is None:
        return {"error": "Cache not available"}

    try:
        minutes = TIME_WINDOWS.get(time_window, 60)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=minutes)

        # Collect all relevant keys
        total_count = 0
        time_series: Dict[str, int] = defaultdict(int)
        all_users = set()

        # Track first and last event times
        first_event_time: Optional[datetime] = None
        last_event_time: Optional[datetime] = None

        # Iterate through cache looking for submission keys
        for key in cache.iterkeys():
            if not key.startswith(SUBMISSION_KEY_PREFIX):
                continue

            try:
                data = cache.get(key)
                if not data or not isinstance(data, dict):
                    continue

                # Parse timestamp from key
                ts_str = key[len(SUBMISSION_KEY_PREFIX) :]
                key_time = datetime.strptime(ts_str, "%Y%m%d%H%M").replace(
                    tzinfo=timezone.utc
                )

                if key_time < cutoff:
                    continue

                count = data.get("count", 0)
                total_count += count

                # Time series data (per minute)
                time_key = key_time.strftime("%H:%M")
                time_series[time_key] += count

                # Track first/last events
                if first_event_time is None or key_time < first_event_time:
                    first_event_time = key_time
                if last_event_time is None or key_time > last_event_time:
                    last_event_time = key_time

                # Collect users
                users = data.get("users", [])
                all_users.update(users)

            except Exception:
                continue

        # Get form-specific stats
        form_breakdown = _get_form_breakdown(cache, cutoff)
        form_time_series = _get_form_time_series(cache, cutoff, minutes, now)

        # Processing-time series (global, per minute)
        duration_raw: Dict[str, Dict[str, float]] = {}
        for key in cache.iterkeys():
            if not key.startswith(DURATION_KEY_PREFIX):
                continue
            try:
                data = cache.get(key)
                if not data or not isinstance(data, dict):
                    continue
                ts_str = key[len(DURATION_KEY_PREFIX) :]
                key_time = datetime.strptime(ts_str, "%Y%m%d%H%M").replace(
                    tzinfo=timezone.utc
                )
                if key_time < cutoff:
                    continue
                duration_raw[key_time.strftime("%H:%M")] = {
                    "avg": data.get("avg", 0.0),
                    "max": data.get("max", 0.0),
                    "count": data.get("count", 0),
                }
            except Exception:
                continue
        duration_series = _generate_full_duration_series(
            minutes, now, duration_raw
        )

        # Calculate rate (submissions per minute)
        rate = total_count / minutes if minutes > 0 else 0

        # Generate complete time series for the full window
        full_time_series = _generate_full_time_series(minutes, now, dict(time_series))

        return {
            "time_window": time_window,
            "total_count": total_count,
            "rate_per_minute": round(rate, 2),
            "unique_users": len(all_users),
            "time_series": full_time_series,
            "forms": form_breakdown,
            "form_time_series": form_time_series,
            "duration_series": duration_series,
            "first_event": first_event_time.isoformat() if first_event_time else None,
            "last_event": last_event_time.isoformat() if last_event_time else None,
            "generated_at": now.isoformat(),
        }

    except Exception as exc:
        logger.exception("Failed to get submission stats")
        return {"error": str(exc)}
    finally:
        try:
            cache.close()
        except Exception:
            pass


def _get_form_breakdown(cache: Cache, cutoff: datetime) -> List[Dict]:
    """Get per-form submission breakdown."""
    form_data: Dict[str, Dict] = defaultdict(
        lambda: {
            "count": 0,
            "users": set(),
            "poll_ids": [],
            "title": None,
            "path": None,
        }
    )

    for key in cache.iterkeys():
        if not key.startswith(FORM_STATS_PREFIX):
            continue

        try:
            data = cache.get(key)
            if not data or not isinstance(data, dict):
                continue

            form_uid = data.get("form_uid")
            if not form_uid:
                continue

            # Parse timestamp from key
            ts_part = key[len(FORM_STATS_PREFIX) :]
            if ":" in ts_part:
                form_uid_from_key, ts_str = ts_part.rsplit(":", 1)
            else:
                continue

            key_time = datetime.strptime(ts_str, "%Y%m%d%H%M").replace(
                tzinfo=timezone.utc
            )
            if key_time < cutoff:
                continue

            form_data[form_uid]["count"] += data.get("count", 0)
            form_data[form_uid]["users"].update(data.get("users", []))
            form_data[form_uid]["poll_ids"].extend(data.get("poll_ids", []))

            # Store title and path (from first entry)
            if not form_data[form_uid]["title"]:
                form_data[form_uid]["title"] = data.get("form_title", "Untitled")
            if not form_data[form_uid]["path"]:
                form_data[form_uid]["path"] = data.get("form_path", "/")

        except Exception:
            continue

    # Per-form processing-time buckets (same keys as submission buckets)
    for key in cache.iterkeys():
        if not key.startswith(FORM_DURATION_PREFIX):
            continue
        try:
            data = cache.get(key)
            if not data or not isinstance(data, dict):
                continue
            form_uid = data.get("form_uid")
            if not form_uid or form_uid not in form_data:
                continue
            ts_part = key[len(FORM_DURATION_PREFIX) :]
            if ":" not in ts_part:
                continue
            _, ts_str = ts_part.rsplit(":", 1)
            key_time = datetime.strptime(ts_str, "%Y%m%d%H%M").replace(
                tzinfo=timezone.utc
            )
            if key_time < cutoff:
                continue
            entry = form_data[form_uid]
            entry["duration_count"] = entry.get("duration_count", 0) + data.get(
                "count", 0
            )
            entry["duration_sum"] = entry.get("duration_sum", 0.0) + data.get(
                "sum", 0.0
            )
            entry["duration_max"] = max(
                entry.get("duration_max", 0.0), data.get("max", 0.0)
            )
        except Exception:
            continue

    # Convert to list and resolve titles where possible
    result = []
    for form_uid, data in sorted(
        form_data.items(), key=lambda x: x[1]["count"], reverse=True
    ):
        duration_count = data.get("duration_count", 0)
        result.append(
            {
                "form_uid": form_uid,
                "title": data["title"] or "Untitled",
                "path": data["path"] or "/",
                "count": data["count"],
                "unique_users": len(data["users"]),
                "avg_duration": (
                    data.get("duration_sum", 0.0) / duration_count
                    if duration_count
                    else None
                ),
                "max_duration": data.get("duration_max", 0.0) or None,
            }
        )

    return result


def check_rate_limit(
    form_uid: Optional[str] = None, max_per_minute: int = 60
) -> Tuple[bool, Dict]:
    """Check if submissions are within rate limits.

    Args:
        form_uid: Specific form to check, or None for global rate
        max_per_minute: Maximum submissions allowed per minute

    Returns:
        Tuple of (is_allowed, rate_info)
    """
    cache = _get_cache()
    if cache is None:
        return True, {"error": "Cache not available"}

    try:
        now = datetime.now(timezone.utc)

        # Check last minute
        current_key = _make_submission_key(now)
        if form_uid:
            current_key = _make_form_key(form_uid, now)

        data = cache.get(current_key, {})
        current_count = data.get("count", 0) if isinstance(data, dict) else 0

        # Check rolling window (last 5 minutes)
        window_count = 0
        for i in range(5):
            check_time = now - timedelta(minutes=i)
            check_key = _make_submission_key(check_time)
            if form_uid:
                check_key = _make_form_key(form_uid, check_time)

            check_data = cache.get(check_key, {})
            window_count += (
                check_data.get("count", 0) if isinstance(check_data, dict) else 0
            )

        avg_per_minute = window_count / 5.0
        is_allowed = current_count < max_per_minute and avg_per_minute < max_per_minute

        return is_allowed, {
            "current_minute_count": current_count,
            "5min_average": round(avg_per_minute, 2),
            "max_allowed": max_per_minute,
            "is_allowed": is_allowed,
        }

    except Exception as exc:
        logger.debug("Rate limit check failed: %s", exc)
        return True, {"error": str(exc)}
    finally:
        try:
            cache.close()
        except Exception:
            pass


def cleanup_old_data(max_age_hours: int = 48) -> int:
    """Clean up monitoring data older than specified hours.

    Returns:
        Number of entries removed
    """
    cache = _get_cache()
    if cache is None:
        return 0

    removed = 0
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        for key in list(cache.iterkeys()):
            try:
                if not (
                    key.startswith(SUBMISSION_KEY_PREFIX)
                    or key.startswith(FORM_STATS_PREFIX)
                ):
                    continue

                data = cache.get(key)
                if not data or not isinstance(data, dict):
                    continue

                ts_str = data.get("timestamp")
                if ts_str:
                    key_time = datetime.fromisoformat(ts_str)
                    if key_time < cutoff:
                        cache.delete(key)
                        removed += 1

            except Exception:
                continue

        return removed

    except Exception as exc:
        logger.warning("Cleanup failed: %s", exc)
        return removed
    finally:
        try:
            cache.close()
        except Exception:
            pass
