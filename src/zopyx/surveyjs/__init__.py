# -*- coding: utf-8 -*-
"""Init and utils."""

import logging
import platform

from zope.i18nmessageid import MessageFactory

_ = MessageFactory("zopyx.surveyjs")

_log = logging.getLogger(__name__)


def _check_validation_binaries_staleness() -> None:
    try:
        from .data_validation import deno_build
    except Exception as exc:  # pragma: no cover - startup guard
        _log.debug("Skipping data validation staleness check: %s", exc)
        return

    system = platform.system().lower()
    if system not in ("darwin", "linux"):
        return

    try:
        deno_build.deno_build_targets([system], force=False)
    except Exception as exc:  # pragma: no cover - startup guard
        _log.warning("Data validation staleness check failed: %s", exc)


_check_validation_binaries_staleness()
