"""Allow-list sanitization for generated result HTML.

Submission answers reach the result detail view, the HTML and PDF exports and
the mail body through the Markdown pipeline (``markdown2``), which passes raw
inline HTML through unchanged and turns Markdown link syntax into anchors.
Answer values are attacker-controlled, so the generated HTML is sanitized
before it is rendered with ``structure`` or handed to WeasyPrint/the mailer.

The sanitizer is a parser-based allow list (``html.parser``), never a
regular-expression filter:

* elements not in :data:`ALLOWED_ELEMENTS` are dropped, their text content is
  kept as escaped text — except for the content elements in
  :data:`DROP_CONTENT_ELEMENTS` (``script``, ``style``, ``svg``, ``iframe``,
  …), whose content is dropped as well;
* attributes are only kept when the element/attribute pair is allow-listed;
* URL attributes (``href``, ``src``) must use a safe scheme: ``http``,
  ``https``, ``mailto``, ``tel`` or a relative reference.  Characters a
  browser ignores when it resolves a URL (whitespace and control characters,
  e.g. ``java\tscript:``) are removed before the scheme is checked, so
  obfuscated ``javascript:``/``vbscript:``/``data:`` URLs never survive.
  Base64 ``data:image/*`` URLs are accepted for ``img src`` only (that is the
  form the converters use to inline validated image attachments).
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

ALLOWED_ELEMENTS = frozenset(
    {
        "a",
        "abbr",
        "b",
        "blockquote",
        "br",
        "caption",
        "cite",
        "code",
        "dd",
        "del",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "ins",
        "kbd",
        "li",
        "mark",
        "ol",
        "p",
        "pre",
        "q",
        "s",
        "samp",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
        "var",
    }
)

#: Elements without an end tag.
VOID_ELEMENTS = frozenset({"br", "hr", "img"})

#: Elements whose *content* is dropped, not just the element itself.
DROP_CONTENT_ELEMENTS = frozenset(
    {
        "applet",
        "base",
        "embed",
        "iframe",
        "link",
        "math",
        "meta",
        "noscript",
        "object",
        "script",
        "style",
        "svg",
        "template",
        "title",
    }
)

#: Attributes allowed on every allow-listed element.
GLOBAL_ATTRIBUTES = frozenset({"title"})

ALLOWED_ATTRIBUTES = {
    "a": frozenset({"href", "title", "rel"}),
    "img": frozenset({"src", "alt", "title", "height", "width"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
    # ``class`` is only needed by the generated metadata block, not by
    # Markdown output; keeping it off every other element keeps the surface
    # minimal.
    "div": frozenset({"class"}),
    "p": frozenset({"class"}),
    "span": frozenset({"class"}),
}

#: ``href`` on ``a``; ``src`` on ``img`` (see :func:`_clean_url`).
URL_ATTRIBUTES = {"a": "href", "img": "src"}

SAFE_URL_SCHEMES = ("http:", "https:", "mailto:", "tel:")

_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
#: Characters browsers strip or ignore while resolving a URL.
_URL_IGNORED_CHARACTERS = re.compile(r"[\x00-\x20\x7f]+")
_DATA_IMAGE_URL = re.compile(
    r"^data:image/(?:png|jpeg|jpg|gif|webp|bmp);base64,[A-Za-z0-9+/]+={0,2}$"
)
_DIMENSION = re.compile(r"^\d{1,4}$")
_SPAN = re.compile(r"^\d{1,3}$")
_CLASS_NAME = re.compile(r"^[A-Za-z0-9_\- ]{1,64}$")
_SCOPE_VALUES = frozenset({"row", "col", "rowgroup", "colgroup"})


def sanitize_html(html_body: str, *, data_images_only: bool = False) -> str:
    """Return ``html_body`` with everything outside the allow list removed.

    ``data_images_only`` removes relative and network image sources as well,
    which is required at sinks such as server-side PDF rendering.
    """
    if not html_body:
        return html_body
    sanitizer = _AllowListSanitizer(data_images_only=data_images_only)
    sanitizer.feed(html_body)
    sanitizer.close()
    return sanitizer.result()


def _clean_url(
    value: str,
    *,
    allow_data_image: bool,
    allow_network: bool = True,
    allow_relative: bool = True,
) -> str | None:
    """Return a safe URL from ``value`` or ``None`` when it is not allowed."""
    candidate = value.strip()
    probe = _URL_IGNORED_CHARACTERS.sub("", candidate)
    if not probe:
        return None
    lowered = probe.lower()
    if lowered.startswith("data:"):
        if allow_data_image and _DATA_IMAGE_URL.fullmatch(probe):
            return candidate
        return None
    if _URL_SCHEME.match(probe):
        if allow_network and lowered.startswith(SAFE_URL_SCHEMES):
            return candidate
        return None
    if probe.startswith("//"):
        # Protocol-relative URL: always a foreign origin.
        return None
    return candidate if allow_relative else None


def _clean_attribute(
    tag: str,
    name: str,
    value: str | None,
    *,
    data_images_only: bool = False,
) -> str | None:
    """Return a safe attribute value or ``None`` when the attribute is dropped."""
    if value is None:
        return None
    if URL_ATTRIBUTES.get(tag) == name:
        image_in_pdf = data_images_only and tag == "img"
        return _clean_url(
            value,
            allow_data_image=(tag == "img"),
            allow_network=not image_in_pdf,
            allow_relative=not image_in_pdf,
        )
    if name == "class":
        return value if _CLASS_NAME.fullmatch(value) else None
    if name in {"width", "height"}:
        return value if _DIMENSION.fullmatch(value) else None
    if name in {"colspan", "rowspan"}:
        return value if _SPAN.fullmatch(value) else None
    if name == "scope":
        return value if value.lower() in _SCOPE_VALUES else None
    if name == "rel":
        return " ".join(
            token for token in value.split() if token.lower() in {"nofollow", "noopener", "noreferrer"}
        ) or None
    return value


class _AllowListSanitizer(HTMLParser):
    """Serialize parsed markup, keeping only allow-listed tags/attributes."""

    def __init__(self, *, data_images_only: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self._data_images_only = data_images_only
        self._output: list[str] = []
        self._open: list[str] = []
        self._dropping: str = ""

    def result(self) -> str:
        while self._open:
            self._output.append(f"</{self._open.pop()}>")
        return "".join(self._output)

    # -- serialization helpers ------------------------------------------
    def _append_text(self, data: str) -> None:
        if data and not self._dropping:
            self._output.append(escape(data, quote=False))

    def _render_start(self, tag: str, attrs) -> str:
        parts = [f"<{tag}"]
        allowed = ALLOWED_ATTRIBUTES.get(tag, frozenset())
        seen: set[str] = set()
        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            if name in seen or (name not in allowed and name not in GLOBAL_ATTRIBUTES):
                continue
            value = _clean_attribute(
                tag,
                name,
                raw_value,
                data_images_only=self._data_images_only,
            )
            if value is None:
                continue
            seen.add(name)
            parts.append(f' {name}="{escape(value, quote=True)}"')
        parts.append(" />" if tag in VOID_ELEMENTS else ">")
        return "".join(parts)

    # -- HTMLParser hooks ------------------------------------------------
    def handle_starttag(self, tag, attrs) -> None:
        tag = tag.lower()
        if self._dropping:
            return
        if tag in DROP_CONTENT_ELEMENTS:
            self._dropping = tag
            return
        if tag not in ALLOWED_ELEMENTS:
            return
        self._output.append(self._render_start(tag, attrs))
        if tag not in VOID_ELEMENTS:
            self._open.append(tag)

    def handle_startendtag(self, tag, attrs) -> None:
        tag = tag.lower()
        if self._dropping:
            return
        if tag in DROP_CONTENT_ELEMENTS:
            return
        if tag not in ALLOWED_ELEMENTS:
            return
        self._output.append(self._render_start(tag, attrs))

    def handle_endtag(self, tag) -> None:
        tag = tag.lower()
        if self._dropping:
            if tag == self._dropping:
                self._dropping = ""
            return
        if tag not in ALLOWED_ELEMENTS or tag in VOID_ELEMENTS:
            return
        if tag not in self._open:
            return
        while self._open:
            current = self._open.pop()
            self._output.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def handle_entityref(self, name: str) -> None:  # pragma: no cover - charrefs converted
        self._append_text(f"&{name};")

    def handle_charref(self, name: str) -> None:  # pragma: no cover - charrefs converted
        self._append_text(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        return

    def handle_decl(self, decl: str) -> None:
        return

    def handle_pi(self, data: str) -> None:
        return

    def unknown_decl(self, data: str) -> None:
        return
