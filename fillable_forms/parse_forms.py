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

SURVEYJS_CLUSTER_Y_GAP = 28.0
SURVEYJS_CLUSTER_X_GAP = 200.0


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


def _get_options(field: DictionaryObject) -> Optional[List[str]]:
    opt = _get_field_attr(field, "/Opt")
    if opt is None:
        return None
    try:
        arr = opt.get_object() if hasattr(opt, "get_object") else opt
    except Exception:
        arr = opt
    out: List[str] = []
    if isinstance(arr, list):
        for item in arr:
            try:
                obj = item.get_object() if hasattr(item, "get_object") else item
            except Exception:
                obj = item
            if isinstance(obj, list) and obj:
                label = obj[-1]
                out.append(str(label))
            else:
                out.append(str(obj))
    return out or None


def _get_appearance_states(annot: DictionaryObject) -> Optional[List[str]]:
    ap = annot.get("/AP")
    if ap is None:
        return None
    try:
        ap_obj = ap.get_object() if hasattr(ap, "get_object") else ap
    except Exception:
        ap_obj = ap
    n = ap_obj.get("/N") if isinstance(ap_obj, DictionaryObject) else None
    if n is None:
        return None
    try:
        n_obj = n.get_object() if hasattr(n, "get_object") else n
    except Exception:
        n_obj = n
    if not isinstance(n_obj, DictionaryObject):
        return None
    states = []
    for key in n_obj.keys():
        name = str(key)
        if name != "/Off":
            states.append(name.lstrip("/"))
    return states or None


def _get_appearance_state(annot: DictionaryObject) -> Optional[str]:
    as_name = _get_name(annot, "/AS")
    if as_name and as_name != "/Off":
        return as_name.lstrip("/")
    return None


def _bool_default(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val)
    return s not in ("", "0", "False", "false", "/Off", "Off")


def _is_required(field: Dict[str, Any]) -> bool:
    if field.get("required"):
        return True
    label = (field.get("label") or "").lower()
    return "required" in label or "must" in label


def _input_hints(field: Dict[str, Any]) -> Dict[str, Any]:
    key = (field.get("key") or "").upper()
    label = (field.get("label") or "").upper()
    text = f"{key} {label}"
    if "SSN" in text:
        return {
            "inputType": "text",
            "mask": "999-99-9999",
            "validators": [
                {
                    "type": "regex",
                    "text": "Use ###-##-####",
                    "regex": "^[0-9]{3}-[0-9]{2}-[0-9]{4}$",
                }
            ],
        }
    if "ZIP" in text or "POSTAL" in text:
        return {
            "inputType": "text",
            "mask": "99999",
            "validators": [
                {"type": "regex", "text": "Use 5-digit ZIP", "regex": "^[0-9]{5}$"}
            ],
        }
    if "PHONE" in text or "TELEPHONE" in text:
        return {
            "inputType": "tel",
            "mask": "(999) 999-9999",
            "validators": [
                {
                    "type": "regex",
                    "text": "Use (###) ###-####",
                    "regex": "^\\([0-9]{3}\\) [0-9]{3}-[0-9]{4}$",
                }
            ],
        }
    if "BIRTH" in text or "DOB" in text or "DATE" in text:
        return {"inputType": "date"}
    if "EMAIL" in text:
        return {"inputType": "email", "validators": [{"type": "email"}]}
    return {}


def _cluster_by_adjacency(fields: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    clusters: List[List[Dict[str, Any]]] = []
    for field in fields:
        placed = False
        fx = float(field.get("x", 0.0) or 0.0)
        fy = float(field.get("y", 0.0) or 0.0)
        for cluster in clusters:
            xs = [float(f.get("x", 0.0) or 0.0) for f in cluster]
            ys = [float(f.get("y", 0.0) or 0.0) for f in cluster]
            if not ys or not xs:
                continue
            if abs(max(ys) - fy) <= SURVEYJS_CLUSTER_Y_GAP and (
                fx >= min(xs) - SURVEYJS_CLUSTER_X_GAP
                and fx <= max(xs) + SURVEYJS_CLUSTER_X_GAP
            ):
                cluster.append(field)
                placed = True
                break
        if not placed:
            clusters.append([field])
    return clusters


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


def _choices_from_field(field: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    opts = field.get("options")
    if not opts:
        return None
    return [{"value": opt, "text": _prettify_label(opt)} for opt in opts]


def _choices_from_appearance(
    fields: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    values: List[str] = []
    for f in fields:
        states = f.get("appearance_states") or []
        for state in states:
            if state not in values:
                values.append(state)
    if not values:
        return None
    return [{"value": v, "text": _prettify_label(v)} for v in values]


def _default_from_field(field: Dict[str, Any]) -> Any:
    val = field.get("default_value")
    if val is None:
        return None
    if isinstance(val, str) and val.startswith("/"):
        return val.lstrip("/")
    return val


def _apply_common_props(question: Dict[str, Any], field: Dict[str, Any]) -> None:
    if _is_required(field):
        question["isRequired"] = True
    if field.get("read_only"):
        question["readOnly"] = True
    default_val = _default_from_field(field)
    if default_val not in (None, ""):
        if question.get("type") == "boolean":
            question["defaultValue"] = _bool_default(default_val)
        else:
            question["defaultValue"] = default_val


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

    grouped: List[Dict[str, Any]] = []
    group_index: Dict[Tuple[Any, ...], int] = {}

    positional_fields: List[Dict[str, Any]] = []
    for field in fields_sorted:
        page = field.get("page", 1)
        prefix = _infer_prefix(field.get("key", ""), field.get("label"))
        if prefix and prefix_counts.get(prefix, 0) > 1:
            key = ("prefix", page if multi_page else None, prefix)
            title = _prettify_label(prefix)
            if multi_page:
                title = f"Page {page}: {title}"
            if key not in group_index:
                group_index[key] = len(grouped)
                grouped.append({"key": key, "title": title, "fields": []})
            grouped[group_index[key]]["fields"].append(field)
        else:
            positional_fields.append(field)

    if positional_fields:
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for field in positional_fields:
            by_page.setdefault(field.get("page", 1), []).append(field)
        for page, page_fields in by_page.items():
            sorted_fields = sorted(
                page_fields,
                key=lambda f: (-(f.get("y", 0.0) or 0.0), f.get("x", 0.0) or 0.0),
            )
            clusters = _cluster_by_adjacency(sorted_fields)
            for idx, cluster in enumerate(clusters, start=1):
                key = ("pos", page, idx)
                title = f"Section {idx}"
                if multi_page:
                    title = f"Page {page}: {title}"
                grouped.append({"key": key, "title": title, "fields": cluster})

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
    for group in grouped:
        panel_elements: List[Dict[str, Any]] = []
        fields_in_group = group["fields"]

        checkbox_fields = [f for f in fields_in_group if f.get("type") == "Checkbox"]
        checkbox_used: set[str] = set()
        checkbox_clusters: List[List[Dict[str, Any]]] = []
        if checkbox_fields:
            sorted_checks = sorted(
                checkbox_fields,
                key=lambda f: (-(f.get("y", 0.0) or 0.0), f.get("x", 0.0) or 0.0),
            )
            checkbox_clusters = _cluster_by_adjacency(sorted_checks)

        def checkbox_cluster_title(cluster: List[Dict[str, Any]]) -> str:
            if not cluster:
                return "Selections"
            prefix = _infer_prefix(cluster[0].get("key", ""), cluster[0].get("label"))
            if prefix:
                return _prettify_label(prefix)
            return "Selections"

        for cluster in checkbox_clusters:
            if len(cluster) < 2:
                continue
            cluster_keys = {c.get("key", "") for c in cluster}
            for ck in cluster_keys:
                checkbox_used.add(ck)
            cluster_sorted = sorted(
                cluster,
                key=lambda f: (-(f.get("y", 0.0) or 0.0), f.get("x", 0.0) or 0.0),
            )
            choices = [
                {"value": c.get("key"), "text": _surveyjs_title_from_field(c)}
                for c in cluster_sorted
            ]
            defaults = [
                c.get("key") for c in cluster if _bool_default(c.get("default_value"))
            ]
            question = {
                "type": "checkbox",
                "name": unique_name(_slugify(checkbox_cluster_title(cluster))),
                "title": checkbox_cluster_title(cluster),
                "choices": choices,
            }
            if any(_is_required(c) for c in cluster):
                question["isRequired"] = True
            if any(c.get("read_only") for c in cluster):
                question["readOnly"] = True
            if defaults:
                question["defaultValue"] = defaults
            panel_elements.append(question)

        for field in fields_in_group:
            key = field.get("key", "")
            if key in checkbox_used:
                continue
            ftype = field.get("type")
            if (
                ftype in ("Radio Button", "Push Button")
                and radio_counts.get(key, 0) > 1
            ):
                if key in emitted_radio:
                    continue
                fields_same = [f for f in fields_sorted if f.get("key") == key]
                choices = _choices_from_appearance(fields_same)
                if not choices:
                    count = radio_counts[key]
                    choices = [
                        {"value": f"option_{idx + 1}", "text": f"Option {idx + 1}"}
                        for idx in range(count)
                    ]
                question = {
                    "type": "radiogroup",
                    "name": unique_name(key),
                    "title": _surveyjs_title_from_field(field),
                    "choices": choices,
                }
                default_val = _default_from_field(field)
                if not default_val:
                    for f in fields_same:
                        if f.get("appearance_state"):
                            default_val = f.get("appearance_state")
                            break
                if default_val:
                    question["defaultValue"] = default_val
                _apply_common_props(question, field)
                panel_elements.append(question)
                emitted_radio.add(key)
                continue

            if ftype in ("Radio Button", "Push Button"):
                question = {
                    "type": "boolean",
                    "name": unique_name(key),
                    "title": _surveyjs_title_from_field(field),
                }
                _apply_common_props(question, field)
                panel_elements.append(question)
                continue

            if ftype in ("List Box", "Combo Box"):
                question = {
                    "type": "dropdown",
                    "name": unique_name(key),
                    "title": _surveyjs_title_from_field(field),
                }
                choices = _choices_from_field(field)
                if choices:
                    question["choices"] = choices
                _apply_common_props(question, field)
                panel_elements.append(question)
                continue

            question = {
                "type": _surveyjs_element_type(ftype),
                "name": unique_name(key),
                "title": _surveyjs_title_from_field(field),
            }
            _apply_common_props(question, field)
            if question["type"] in ("text", "comment"):
                hints = _input_hints(field)
                question.update(hints)
            panel_elements.append(question)

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
            options = _get_options(annot)
            ap_states = _get_appearance_states(annot)
            ap_state = _get_appearance_state(annot)
            flags_val = int(ff) if ff is not None else None

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
                "flags": flags_val,
                "required": bool(flags_val & 2) if flags_val is not None else False,
                "read_only": bool(flags_val & 1) if flags_val is not None else False,
                "mapping_name": _stringify_value(tm),
                "x": rect_info["rect"][0],
                "y": rect_info["rect"][1],
                "width": rect_info["width"],
                "height": rect_info["height"],
                "rect": rect_info["rect"],
                "normalized_rect": rect_info["normalized_rect"],
                "page": page_index,
                "options": options,
                "appearance_states": ap_states,
                "appearance_state": ap_state,
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
    parser = argparse.ArgumentParser(
        description="Extract simplified PDF form fields + layout"
    )
    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        help="Glob pattern(s) for PDFs (default: *.pdf)",
    )
    parser.add_argument(
        "--out",
        default="forms_index.json",
        help="Output JSON file (default: forms_index.json)",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output"
    )
    parser.add_argument(
        "--per-file-out",
        default=None,
        help="Optional output directory for per-file JSON",
    )
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
