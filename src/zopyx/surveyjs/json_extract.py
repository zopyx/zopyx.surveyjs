from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union


class NoJSONFound(ValueError):
    """Raised when no valid JSON payload can be extracted."""


_FENCED_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL
)
_PRE_BLOCK_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.IGNORECASE | re.DOTALL)
_CODE_BLOCK_RE = re.compile(r"<code[^>]*>(.*?)</code>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    obj: object

    @property
    def length(self) -> int:
        return self.end - self.start


def _read_source(source: Union[str, Path]) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8", errors="replace")
    if isinstance(source, str) and os.path.exists(source):
        return Path(source).read_text(encoding="utf-8", errors="replace")
    return source


def _try_load(text: str) -> Optional[object]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _iter_blocks(text: str) -> Iterable[str]:
    for regex in (_FENCED_BLOCK_RE, _PRE_BLOCK_RE, _CODE_BLOCK_RE):
        for match in regex.finditer(text):
            block = match.group(1).strip()
            if block:
                yield block


def _find_candidates(text: str) -> Iterable[_Candidate]:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            continue
        yield _Candidate(start=idx, end=end, obj=obj)


def _pick_best(candidates: Iterable[_Candidate]) -> Optional[_Candidate]:
    best: Optional[_Candidate] = None
    for candidate in candidates:
        if best is None or candidate.length > best.length:
            best = candidate
    return best


def extract_json(source: Union[str, Path]) -> object:
    """Extract and parse the first valid JSON payload from text or a file path."""
    text = _read_source(source)

    direct = _try_load(text)
    if direct is not None:
        return direct

    for block in _iter_blocks(text):
        parsed = _try_load(block)
        if parsed is not None:
            return parsed

    best = _pick_best(_find_candidates(text))
    if best is not None:
        return best.obj

    raise NoJSONFound("No valid JSON object or array found in input.")


def extract_json_text(source: Union[str, Path]) -> str:
    """Return the JSON payload string from text or a file path."""
    text = _read_source(source)

    direct = _try_load(text)
    if direct is not None:
        return text.strip()

    for block in _iter_blocks(text):
        parsed = _try_load(block)
        if parsed is not None:
            return block.strip()

    best = _pick_best(_find_candidates(text))
    if best is not None:
        return text[best.start:best.end].strip()

    raise NoJSONFound("No valid JSON object or array found in input.")


def _main(argv: Optional[Iterable[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract JSON from a file or raw text."
    )
    parser.add_argument(
        "source",
        help="File path or raw text to scan for JSON.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Print the JSON text instead of parsing it.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.text:
            print(extract_json_text(args.source))
        else:
            print(json.dumps(extract_json(args.source), indent=2, ensure_ascii=True))
    except NoJSONFound as exc:
        parser.error(str(exc))

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
