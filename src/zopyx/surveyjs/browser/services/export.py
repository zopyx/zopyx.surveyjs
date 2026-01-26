from datetime import datetime

from ...utils import ensure_timezone_aware


def serialize_result_entry(result_entry):
    serialized = dict(result_entry)
    created = serialized.get("created")
    if isinstance(created, datetime):
        serialized["created"] = ensure_timezone_aware(created).isoformat()
    return serialized


def write_export(format_key, poll_id, items, attachments, creator, created, output_dir):
    output_path = None
    if format_key == "text":
        from zopyx.surveyjs.converters import write_text

        output_path = write_text(items, output_dir / f"{poll_id}.txt", creator, created)
    elif format_key == "md":
        from zopyx.surveyjs.converters import write_markdown

        output_path = write_markdown(
            items, poll_id, output_dir / f"{poll_id}.md", creator, created
        )
    elif format_key == "html":
        from zopyx.surveyjs.converters import build_markdown, write_html

        markdown_body = build_markdown(items, poll_id, creator, created)
        output_path = write_html(
            markdown_body, attachments, output_dir / f"{poll_id}.html"
        )
    elif format_key == "pdf":
        from zopyx.surveyjs.converters import build_markdown, write_pdf
        from zopyx.surveyjs.converters.html import build_html

        markdown_body = build_markdown(items, poll_id, creator, created)
        html_body = build_html(markdown_body, attachments)
        output_path = write_pdf(
            html_body, output_dir / f"{poll_id}.pdf", creator, created
        )
    elif format_key in {"csv", "xlsx"}:
        from zopyx.surveyjs.converters import build_table_rows, write_csv, write_xlsx

        table_rows = build_table_rows(items)
        if format_key == "csv":
            output_path = write_csv(table_rows, output_dir / f"{poll_id}.csv")
        else:
            output_path = write_xlsx(table_rows, output_dir / f"{poll_id}.xlsx")
    elif format_key == "xml":
        from zopyx.surveyjs.converters import write_xml

        output_path = write_xml(items, poll_id, output_dir / f"{poll_id}.xml")
    elif format_key == "docx":
        from zopyx.surveyjs.converters import write_docx

        output_path = write_docx(
            items,
            output_dir / f"{poll_id}.docx",
            poll_id,
            creator,
            created,
        )
    elif format_key == "json":
        from zopyx.surveyjs.converters import write_json

        output_path = write_json(
            items, poll_id, output_dir / f"{poll_id}.json", creator, created
        )
    return output_path
