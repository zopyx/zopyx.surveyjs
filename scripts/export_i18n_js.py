#!/usr/bin/env python3
import gettext
import json
import sys
from pathlib import Path
from typing import Dict

DOMAIN = "zopyx.surveyjs"
REPO_ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = REPO_ROOT / "src" / "zopyx" / "surveyjs" / "locales"
OUTPUT_DIR = (
    REPO_ROOT / "src" / "zopyx" / "surveyjs" / "browser" / "static" / "i18n"
)


def load_messages_from_mo(mo_path: Path) -> Dict[str, str]:
    with mo_path.open("rb") as handle:
        translations = gettext.GNUTranslations(handle)

    messages: Dict[str, str] = {}
    catalog = translations._catalog
    for key, value in catalog.items():
        if key is None or key == "":
            continue
        if isinstance(key, tuple):
            msgid = key[0]
            if isinstance(value, tuple):
                messages[msgid] = value[0]
            else:
                messages[msgid] = value
        else:
            messages[key] = value

    return messages


def load_messages_from_po(po_path: Path) -> Dict[str, str]:
    messages: Dict[str, str] = {}
    msgid = None
    msgstr = None
    state = None

    def commit():
        nonlocal msgid, msgstr
        if not msgid:
            msgid = None
            msgstr = None
            return
        value = msgstr if msgstr is not None and msgstr != "" else msgid
        messages[msgid] = value
        msgid = None
        msgstr = None

    for raw_line in po_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgctxt"):
            continue
        if line.startswith("msgid_plural"):
            continue
        if line.startswith("msgid"):
            commit()
            state = "msgid"
            msgid = line[5:].strip().lstrip()
            if msgid.startswith('"'):
                msgid = msgid.strip('"')
            continue
        if line.startswith("msgstr"):
            state = "msgstr"
            msgstr = line[6:].strip().lstrip()
            if msgstr.startswith('"'):
                msgstr = msgstr.strip('"')
            continue
        if line.startswith("msgstr["):
            state = "msgstr"
            msgstr = line.split("]", 1)[1].strip().lstrip()
            if msgstr.startswith('"'):
                msgstr = msgstr.strip('"')
            continue
        if line.startswith('"'):
            value = line.strip('"')
            if state == "msgid" and msgid is not None:
                msgid += value
            elif state == "msgstr" and msgstr is not None:
                msgstr += value

    commit()
    messages.pop("", None)
    return messages


def export_language(lang: str) -> bool:
    po_path = LOCALES_DIR / lang / "LC_MESSAGES" / f"{DOMAIN}.po"
    mo_path = LOCALES_DIR / lang / "LC_MESSAGES" / f"{DOMAIN}.mo"
    if po_path.exists():
        messages = load_messages_from_po(po_path)
    elif mo_path.exists():
        messages = load_messages_from_mo(mo_path)
    else:
        print(f"Skipping {lang}: missing {po_path} and {mo_path}", file=sys.stderr)
        return False
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{lang}.js"
    payload = json.dumps(messages, indent=2, sort_keys=True, ensure_ascii=True)
    output_path.write_text(
        f"window.SURVEYJS_I18N_MESSAGES = {payload};\n", encoding="utf-8"
    )
    print(f"Wrote {output_path}")
    return True


def main() -> int:
    if not LOCALES_DIR.exists():
        print(f"Locales directory not found: {LOCALES_DIR}", file=sys.stderr)
        return 1

    languages = [
        path.name
        for path in LOCALES_DIR.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    ]

    if not languages:
        print("No locales found", file=sys.stderr)
        return 1

    exported = False
    for lang in sorted(languages):
        exported = export_language(lang) or exported

    return 0 if exported else 1


if __name__ == "__main__":
    raise SystemExit(main())
