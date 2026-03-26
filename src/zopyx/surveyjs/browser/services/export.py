"""Helpers for serializing and exporting stored survey results."""

from datetime import datetime

from ...utils import ensure_timezone_aware


def serialize_result_entry(result_entry):
    """Convert a stored result entry to a JSON-friendly structure."""
    serialized = dict(result_entry)
    created = serialized.get("created")
    if isinstance(created, datetime):
        serialized["created"] = ensure_timezone_aware(created).isoformat()
    return serialized


def write_export(format_key, poll_id, items, attachments, creator, created, output_dir):
    """Write an export file in the requested format and return its path."""
    output_path = None
    if format_key == "text":
        from zopyx.surveyjs.converters2.compat import write_text

        output_path = write_text(items, output_dir / f"{poll_id}.txt", poll_id, creator, created)
    elif format_key == "md":
        from zopyx.surveyjs.converters2.compat import write_markdown

        output_path = write_markdown(
            items, output_dir / f"{poll_id}.md", poll_id, creator, created
        )
    elif format_key == "html":
        from zopyx.surveyjs.converters2.compat import build_markdown, write_html

        markdown_body = build_markdown(items, poll_id, creator, created)
        output_path = write_html(
            markdown_body, attachments, output_dir / f"{poll_id}.html"
        )
    elif format_key == "pdf":
        from zopyx.surveyjs.converters2.compat import build_html, build_markdown, write_pdf

        markdown_body = build_markdown(items, poll_id, creator, created)
        html_body = build_html(markdown_body, attachments)
        output_path = write_pdf(
            html_body, output_dir / f"{poll_id}.pdf", creator, created
        )
    elif format_key in {"csv", "xlsx"}:
        from zopyx.surveyjs.converters2.compat import build_table_rows, write_csv, write_xlsx

        table_rows = build_table_rows(items)
        if format_key == "csv":
            output_path = write_csv(table_rows, output_dir / f"{poll_id}.csv")
        else:
            output_path = write_xlsx(table_rows, output_dir / f"{poll_id}.xlsx")
    elif format_key == "xml":
        from zopyx.surveyjs.converters2.compat import write_xml

        output_path = write_xml(items, output_dir / f"{poll_id}.xml", poll_id, creator, created)
    elif format_key == "docx":
        from zopyx.surveyjs.converters2.compat import write_docx

        output_path = write_docx(
            items,
            output_dir / f"{poll_id}.docx",
            poll_id,
            creator,
            created,
        )
    elif format_key == "json":
        from zopyx.surveyjs.converters2.compat import write_json

        output_path = write_json(
            items, output_dir / f"{poll_id}.json", poll_id, creator, created
        )
    return output_path
