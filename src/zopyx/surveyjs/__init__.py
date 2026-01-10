# -*- coding: utf-8 -*-
"""Init and utils."""

try:
    from zope.i18nmessageid import MessageFactory

    _ = MessageFactory("zopyx.surveyjs")
except:
    pass
