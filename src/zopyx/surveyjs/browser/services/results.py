from datetime import datetime

import orjson

from ...utils import ensure_timezone_aware


def format_created(created):
    if isinstance(created, str):
        value = created.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            created = datetime.fromisoformat(value)
        except ValueError:
            return created
    if isinstance(created, datetime):
        created = ensure_timezone_aware(created).replace(tzinfo=None)
        return created.replace(microsecond=0).isoformat()
    return created


def parse_tabulator_param(request, name):
    raw = request.form.get(name)
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    if not raw:
        return []
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        return []


def results2_row(entry):
    result_payload = entry.get("result") or {}
    created = entry.get("created")
    created_ts = None
    if created:
        created_ts = ensure_timezone_aware(created).timestamp()
    return dict(
        poll_id=entry.get("poll_id"),
        user=entry.get("user") or "",
        seq_no=entry.get("seq_no") or "",
        uuid=(result_payload.get("uuid") or ""),
        created_ts=created_ts or 0,
        created_display=format_created(created),
    )


def results2_apply_filters(rows, filters):
    if not filters:
        return rows

    def _match(row, flt):
        field = flt.get("field")
        value = flt.get("value")
        if field is None:
            return True
        row_value = row.get(field, "")
        ftype = (flt.get("type") or "like").lower()
        if ftype in ("=", "eq"):
            return str(row_value) == str(value)
        if ftype in ("!=", "ne"):
            return str(row_value) != str(value)
        if ftype in ("like", "contains"):
            haystack = row_value
            if field == "created_ts":
                haystack = row.get("created_display", "")
            return str(value).lower() in str(haystack).lower()
        if ftype in (">", ">=", "<", "<="):
            try:
                row_num = float(row_value)
                val_num = float(value)
            except (TypeError, ValueError):
                return False
            if ftype == ">":
                return row_num > val_num
            if ftype == ">=":
                return row_num >= val_num
            if ftype == "<":
                return row_num < val_num
            if ftype == "<=":
                return row_num <= val_num
        if ftype == "in" and isinstance(value, (list, tuple)):
            return row_value in value
        return True

    return [row for row in rows if all(_match(row, flt) for flt in filters)]


def build_results2_payload(results, request):
    q = (request.form.get("q") or "").strip().lower()

    def _safe_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    page = _safe_int(request.form.get("page"), 1)
    size = _safe_int(request.form.get("size"), 25)
    page = max(page, 1)
    size = max(size, 1)

    sorters = parse_tabulator_param(request, "sorters")
    filters = parse_tabulator_param(request, "filters")
    if isinstance(sorters, dict):
        sorters = [sorters]
    if isinstance(filters, dict):
        filters = [filters]

    rows = [results2_row(entry) for entry in results]

    if q:

        def _matches(row):
            return (
                q in str(row.get("user") or "").lower()
                or q in str(row.get("poll_id") or "").lower()
                or q in str(row.get("uuid") or "").lower()
                or q in str(row.get("created_display") or "").lower()
                or q in str(row.get("seq_no") or "").lower()
            )

        rows = [row for row in rows if _matches(row)]

    rows = results2_apply_filters(rows, filters)

    if sorters:
        for sorter in reversed(sorters):
            field = sorter.get("field")
            direction = (sorter.get("dir") or "asc").lower()
            reverse = direction == "desc"
            rows.sort(key=lambda r: r.get(field), reverse=reverse)

    total_rows = len(rows)
    last_page = total_rows // size + (1 if total_rows % size else 0)
    last_page = max(last_page, 1)

    start = (page - 1) * size
    data = rows[start : start + size]

    return dict(
        data=data,
        page=page,
        last_page=last_page,
        total_rows=total_rows,
    )


def get_paginated_results(results, request):
    q = request.form.get("q", "").lower()
    b_start = int(request.form.get("b_start", 0))
    pagesize = 10

    all_results = results
    if q:

        def _matches_query(result):
            user = (result.get("user") or "").lower()
            poll_id = (result.get("poll_id") or "").lower()
            created = (format_created(result.get("created")) or "").lower()
            result_uuid = ""
            result_payload = result.get("result") or {}
            if isinstance(result_payload, dict):
                result_uuid = (result_payload.get("uuid") or "").lower()
            return q in user or q in poll_id or q in result_uuid or q in created

        all_results = [r for r in all_results if _matches_query(r)]

    total = len(all_results)
    numpages = total // pagesize
    if total % pagesize > 0:
        numpages += 1
    page = b_start // pagesize + 1
    return dict(
        items=all_results[b_start : b_start + pagesize],
        total=total,
        numpages=numpages,
        page=page,
        pagesize=pagesize,
        q=q,
    )
