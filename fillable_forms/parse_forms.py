#!/usr/bin/env python3
"""
Extract simplified field metadata and layout info from fillable PDFs.

Outputs per-form groups with fields containing key/label/type/value/position.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader
from pypdf.generic import DictionaryObject

SURVEYJS_BUCKET_SIZE = 60.0


def _as_name(val: Any) -> Optional[str]:
    if val is None:
        return None
    try:
        return val.get_object() if hasattr(val, "get_object") else val
    except Exception:
        return val


def _get_name(d: DictionaryObject, key: str) -> Optional[str]:
    if d is None:
        return None
    val = d.get(key)
    if val is None:
        return None
    obj = _as_name(val)
    try:
        return str(obj)
    except Exception:
        return None


def _get_number_list(d: DictionaryObject, key: str) -> Optional[List[float]]:
    if d is None:
        return None
    val = d.get(key)
    if val is None:
        return None
    try:
        arr = val.get_object() if hasattr(val, "get_object") else val
        return [float(x) for x in arr]
    except Exception:
        return None


def _get_parent_chain(field: DictionaryObject) -> List[DictionaryObject]:
    chain = []
    cur = field
    while cur is not None:
        chain.append(cur)
        parent = cur.get("/Parent")
        if parent is None:
            break
        try:
            cur = parent.get_object()
        except Exception:
            break
    return chain


def _field_path(field: DictionaryObject) -> Tuple[List[str], str]:
    chain = _get_parent_chain(field)
    names = []
    for node in reversed(chain):
        name = _get_name(node, "/T")
        if name:
            names.append(name)
    full = ".".join(names) if names else ""
    return names, full


def _get_field_attr(field: DictionaryObject, key: str) -> Any:
    # Walk up parent chain for inherited attributes
    cur = field
    while cur is not None:
        if key in cur:
            try:
                return cur.get(key)
            except Exception:
                return None
        parent = cur.get("/Parent")
        if parent is None:
            break
        try:
            cur = parent.get_object()
        except Exception:
            break
    return None


def _rect_info(rect: List[float], media_box: List[float]) -> Dict[str, Any]:
    x0, y0, x1, y1 = rect
    width = max(0.0, x1 - x0)
    height = max(0.0, y1 - y0)
    page_w = max(0.0, media_box[2] - media_box[0])
    page_h = max(0.0, media_box[3] - media_box[1])
    norm = None
    if page_w and page_h:
        norm = [x0 / page_w, y0 / page_h, x1 / page_w, y1 / page_h]
    return {
        "rect": [x0, y0, x1, y1],
        "width": width,
        "height": height,
        "normalized_rect": norm,
    }

def _stringify_value(val: Any) -> Any:
    if val is None:
        return None
    try:
        obj = val.get_object() if hasattr(val, "get_object") else val
    except Exception:
        obj = val
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def _field_type_label(ft: Any, flags: Any) -> Optional[str]:
    if ft is None:
        return None
    ft_str = str(ft)
    if ft_str == "/Tx":
        if flags is not None and int(flags) & 1 << 12:
            return "Multiline Text"
        return "Text"
    if ft_str == "/Btn":
        if flags is not None:
            ff = int(flags)
            if ff & (1 << 16):
                return "Radio Button"
            if ff & (1 << 15):
                return "Push Button"
        return "Checkbox"
    if ft_str == "/Ch":
        if flags is not None and int(flags) & (1 << 17):
            return "Combo Box"
        return "List Box"
    if ft_str == "/Sig":
        return "Signature"
    return ft_str.lstrip("/")

def _prettify_label(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.replace("_", " ").split())
    if cleaned.isupper() or "_" in text:
        return cleaned.title()
    return cleaned


def _infer_prefix(key: str, label: Optional[str]) -> Optional[str]:
    if key:
        if "_" in key:
            return key.split("_", 1)[0]
        if key.isupper() and " " in key:
            return None
    if label and "_" in label:
        return label.split("_", 1)[0]
    return None


def _slugify(text: str) -> str:
    cleaned = []
    for ch in text.lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in (" ", "-", "_"):
            cleaned.append("_")
    slug = "_".join(filter(None, "".join(cleaned).split("_")))
    return slug or "group"


def _surveyjs_element_type(field_type: Optional[str]) -> str:
    if field_type == "Multiline Text":
        return "comment"
    if field_type == "Text":
        return "text"
    if field_type in ("Checkbox",):
        return "boolean"
    if field_type in ("List Box", "Combo Box"):
        return "dropdown"
    if field_type == "Signature":
        return "signaturepad"
    return "text"


def _surveyjs_title_from_field(field: Dict[str, Any]) -> str:
    label = field.get("label") or field.get("key")
    return _prettify_label(label)


def _build_surveyjs(form: Dict[str, Any]) -> Dict[str, Any]:
    fields: List[Dict[str, Any]] = []
    for group_fields in form.get("groups", {}).values():
        fields.extend(group_fields)

    if not fields:
        return {
            "title": _prettify_label(form.get("file", "Form")),
            "pages": [{"name": "page1", "elements": []}],
            "showQuestionNumbers": "off",
        }

    fields_sorted = sorted(
        fields,
        key=lambda f: (
            f.get("page", 0),
            -(f.get("y", 0.0) or 0.0),
            f.get("x", 0.0) or 0.0,
        ),
    )

    pages = {f.get("page", 1) for f in fields_sorted}
    multi_page = len(pages) > 1

    prefix_counts: Dict[str, int] = {}
    for field in fields_sorted:
        prefix = _infer_prefix(field.get("key", ""), field.get("label"))
        if prefix:
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

    groups: List[Dict[str, Any]] = []
    group_index: Dict[Tuple[Any, ...], int] = {}

    for field in fields_sorted:
        page = field.get("page", 1)
        prefix = _infer_prefix(field.get("key", ""), field.get("label"))
        if prefix and prefix_counts.get(prefix, 0) > 1:
            key = ("prefix", page if multi_page else None, prefix)
            title = _prettify_label(prefix)
            if multi_page:
                title = f"Page {page}: {title}"
        else:
            bucket = int((field.get("y", 0.0) or 0.0) // SURVEYJS_BUCKET_SIZE)
            key = ("pos", page, bucket)
            title = ""
        if key not in group_index:
            group_index[key] = len(groups)
            groups.append({"key": key, "title": title, "fields": []})
        groups[group_index[key]]["fields"].append(field)

    section_counter: Dict[int, int] = {}
    for group in groups:
        key = group["key"]
        if key[0] == "pos":
            page = key[1]
            section_counter[page] = section_counter.get(page, 0) + 1
            title = f"Section {section_counter[page]}"
            if multi_page:
                title = f"Page {page}: {title}"
            group["title"] = title

    radio_counts: Dict[str, int] = {}
    for field in fields_sorted:
        if field.get("type") in ("Radio Button", "Push Button"):
            key = field.get("key", "")
            radio_counts[key] = radio_counts.get(key, 0) + 1

    used_names: Dict[str, int] = {}
    def unique_name(base: str) -> str:
        if base not in used_names:
            used_names[base] = 1
            return base
        used_names[base] += 1
        return f"{base}_{used_names[base]}"

    emitted_radio: set[str] = set()
    elements: List[Dict[str, Any]] = []
    for group in groups:
        panel_elements: List[Dict[str, Any]] = []
        for field in group["fields"]:
            key = field.get("key", "")
            ftype = field.get("type")
            if ftype in ("Radio Button", "Push Button") and radio_counts.get(key, 0) > 1:
                if key in emitted_radio:
                    continue
                count = radio_counts[key]
                choices = [
                    {"value": f"option_{idx+1}", "text": f"Option {idx+1}"}
                    for idx in range(count)
                ]
                panel_elements.append(
                    {
                        "type": "radiogroup",
                        "name": unique_name(key),
                        "title": _surveyjs_title_from_field(field),
                        "choices": choices,
                    }
                )
                emitted_radio.add(key)
                continue

            if ftype in ("Radio Button", "Push Button"):
                panel_elements.append(
                    {
                        "type": "boolean",
                        "name": unique_name(key),
                        "title": _surveyjs_title_from_field(field),
                    }
                )
                continue

            panel_elements.append(
                {
                    "type": _surveyjs_element_type(ftype),
                    "name": unique_name(key),
                    "title": _surveyjs_title_from_field(field),
                }
            )

        panel_title = group["title"]
        panel_name = _slugify(panel_title or "group")
        elements.append(
            {
                "type": "panel",
                "name": unique_name(panel_name),
                "title": panel_title,
                "elements": panel_elements,
            }
        )

    return {
        "title": _prettify_label(form.get("file", "Form")),
        "description": "SurveyJS form generated from PDF fields.",
        "showQuestionNumbers": "off",
        "pages": [{"name": "page1", "elements": elements}],
    }

def extract_pdf(path: Path) -> Dict[str, Any]:
    reader = PdfReader(str(path))
    info: Dict[str, Any] = {
        "file": path.name,
        "groups": {},
    }

    unnamed_counter = 0
    for page_index, page in enumerate(reader.pages, start=1):
        media_box = [float(x) for x in page.mediabox]

        annots = page.get("/Annots") or []
        for annot_idx, annot_ref in enumerate(annots, start=1):
            try:
                annot = annot_ref.get_object()
            except Exception:
                continue
            if _get_name(annot, "/Subtype") != "/Widget":
                continue

            rect = _get_number_list(annot, "/Rect")
            if rect is None or len(rect) != 4:
                continue

            field_path, full_name = _field_path(annot)
            ft = _get_field_attr(annot, "/FT")
            ff = _get_field_attr(annot, "/Ff")
            v = _get_field_attr(annot, "/V")
            tu = _get_field_attr(annot, "/TU")
            tm = _get_field_attr(annot, "/TM")
            rect_info = _rect_info(rect, media_box)

            if not full_name:
                unnamed_counter += 1
                full_name = f"unnamed_{page_index}_{annot_idx}_{unnamed_counter}"

            label = _stringify_value(tu)
            if not label:
                label = field_path[-1] if field_path else full_name

            group_path = ".".join(field_path[:-1]) if len(field_path) > 1 else ""
            if not group_path:
                group_path = "default"

            field_info = {
                "key": full_name,
                "label": label,
                "default_value": _stringify_value(v),
                "type": _field_type_label(ft, ff),
                "flags": int(ff) if ff is not None else None,
                "mapping_name": _stringify_value(tm),
                "x": rect_info["rect"][0],
                "y": rect_info["rect"][1],
                "width": rect_info["width"],
                "height": rect_info["height"],
                "page": page_index,
            }

            info["groups"].setdefault(group_path, []).append(field_info)

    return info


def gather_pdfs(root: Path, patterns: List[str]) -> List[Path]:
    pdfs: List[Path] = []
    if patterns:
        for pat in patterns:
            pdfs.extend(sorted(root.glob(pat)))
    else:
        pdfs = sorted(root.glob("*.pdf"))
    # De-duplicate while preserving order
    seen = set()
    unique = []
    for p in pdfs:
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        unique.append(p)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract simplified PDF form fields + layout")
    parser.add_argument("--glob", action="append", default=[], help="Glob pattern(s) for PDFs (default: *.pdf)")
    parser.add_argument("--out", default="forms_index.json", help="Output JSON file (default: forms_index.json)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--per-file-out", default=None, help="Optional output directory for per-file JSON")
    parser.add_argument(
        "--surveyjs-out",
        default=None,
        help="Optional output directory for per-file SurveyJS JSON",
    )
    args = parser.parse_args()

    root = Path.cwd()
    pdfs = gather_pdfs(root, args.glob)
    if not pdfs:
        raise SystemExit("No PDF files found.")

    results = []
    for pdf in pdfs:
        results.append(extract_pdf(pdf))

    indent = 2 if args.pretty else None
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"forms": results}, f, indent=indent, ensure_ascii=False)

    if args.per_file_out:
        out_dir = Path(args.per_file_out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for form in results:
            out_path = out_dir / f"{Path(form['file']).stem}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(form, f, indent=indent, ensure_ascii=False)

    if args.surveyjs_out:
        out_dir = Path(args.surveyjs_out)
        out_dir.mkdir(parents=True, exist_ok=True)
        for form in results:
            surveyjs = _build_surveyjs(form)
            out_path = out_dir / f"{Path(form['file']).stem}.surveyjs.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(surveyjs, f, indent=indent, ensure_ascii=False)

    print(f"Wrote {len(results)} form(s) to {args.out}")


if __name__ == "__main__":
    main()
