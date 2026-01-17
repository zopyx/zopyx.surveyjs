# -*- coding: utf-8 -*-
try:
    __import__("pkg_resources").declare_namespace(__name__)
except ModuleNotFoundError:
    # Fallback for environments without setuptools (pkg_resources).
    from pkgutil import extend_path

    __path__ = extend_path(__path__, __name__)
