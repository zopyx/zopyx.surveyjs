from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from zopyx.surveyjs.converters import (
    common,
    csv_export,
    docx_export,
    html,
    json_export,
    markdown,
    pdf,
    sanitize,
    spreadsheet,
    text,
    xlsx_export,
    xml_export,
)
from zopyx.surveyjs.converters.types import Attachment, Item


@pytest.fixture
def image_attachment() -> Attachment:
    return Attachment("photo.png", b"\x89PNG", "image/png", field_label="Photo")


@pytest.fixture
def binary_attachment() -> Attachment:
    return Attachment("document.bin", b"binary data", None, field_label="Binary")


@pytest.fixture
def sample_items(
    image_attachment: Attachment, binary_attachment: Attachment
) -> list[Item]:
    return [
        Item(
            key="text",
            label="Text Question",
            values=["alpha", "beta"],
            attachments=[binary_attachment],
        ),
        Item(
            key="table",
            label="Table Question",
            values=[],
            attachments=[image_attachment],
            table=[["Col A", "Col B"], ["Row 1", "Row 2"]],
            table_columns=[("a", "Column A"), ("b", "Column B")],
        ),
        Item(
            key="matrix",
            label="Matrix",
            values=["ignored"],
            attachments=[],
            field_type="matrixdynamic",
            raw_value=[{"col1": "v1"}],
        ),
    ]


def test_attachment_data_url_and_is_image_guessing() -> None:
    bin_attachment = Attachment("file.bin", b"abc", None)
    url = bin_attachment.data_url()
    assert url.startswith("data:application/octet-stream;base64,YWJj")
    assert not bin_attachment.is_image

    png_attachment = Attachment("img.png", b"\x89PNG", "image/png")
    assert png_attachment.is_image
    assert "image/png;base64" in png_attachment.data_url()


def test_render_text_table_empty_and_padding() -> None:
    assert common.render_text_table([]) == ["(empty)"]

    lines = common.render_text_table([["H1"], ["V1", "V2"]])
    assert lines[0].startswith("H1")
    assert lines[1].startswith("-")
    assert "+" in lines[1]
    assert "V1" in lines[2] and "V2" in lines[2]


def test_render_markdown_table_empty_and_padding() -> None:
    assert common.render_markdown_table([]) == ["(empty)"]

    lines = common.render_markdown_table([["H1"], ["V1", "V2"]])
    assert lines[0] == "| H1 |  |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| V1 | V2 |"


def test_build_table_rows_joins_values_and_attachments() -> None:
    items = [
        Item(
            key="k1",
            label="Label 1",
            values=["v1", "v2"],
            attachments=[Attachment("file.txt", b"", "text/plain")],
        ),
        Item(
            key="k2",
            label="Label 2",
            values=["only"],
            attachments=[Attachment("blob.bin", b"", None)],
        ),
    ]
    rows = common.build_table_rows(items)
    assert rows[0] == ("k1", "Label 1", "v1; v2", "file.txt (text/plain)")
    assert rows[1] == ("k2", "Label 2", "only", "blob.bin (binary)")


def test_inline_html_images_replaces_sources(image_attachment: Attachment) -> None:
    html_body = (
        "<p><img src='photo.png'><img src=\"photo.png\"><img src='other.bin'></p>"
    )
    updated = common.inline_html_images(html_body, [image_attachment])
    assert "data:image/png;base64" in updated
    assert "photo.png" not in updated
    assert "other.bin" in updated


def test_wrap_pdf_html_metadata_insertion_with_heading() -> None:
    html_body = "<h1>Title</h1><p>Body</p>"
    wrapped = common.wrap_pdf_html(
        html_body, creator="Alice", created="2024-05-15T10:20:00Z"
    )
    assert wrapped.startswith("<html>")
    assert "Created by:</strong> Alice" in wrapped
    assert "May 15, 2024 at" in wrapped
    assert wrapped.index("</h1>") < wrapped.index("Created by:")


def test_wrap_pdf_html_without_heading_uses_raw_date() -> None:
    wrapped = common.wrap_pdf_html("<p>Body</p>", created="not-a-date")
    assert wrapped.startswith("<html>")
    assert "not-a-date" in wrapped


def test_wrap_pdf_html_without_metadata_keeps_body() -> None:
    wrapped = common.wrap_pdf_html("<p>Just body</p>")
    assert wrapped.startswith("<html>")
    assert "Just body" in wrapped
    assert "Created" not in wrapped


def test_wrap_pdf_html_inserts_metadata_without_heading() -> None:
    wrapped = common.wrap_pdf_html("<p>Body</p>", creator="Sam")
    assert wrapped.startswith("<html>")
    assert wrapped.index("Created by:") < wrapped.index("Body")


def test_build_html_neutralises_click_triggered_javascript_urls() -> None:
    """The stored-XSS chain of the security review (answer -> converter)."""
    md_text = '[review](javascript:alert(document.domain))'
    html_body = html.build_html(md_text, [])

    assert "javascript:" not in html_body
    assert "review" in html_body

    raw_html = '<a href="javascript:alert(1)">click</a>'
    assert "javascript:" not in html.build_html(raw_html, [])


@pytest.mark.parametrize(
    "payload",
    [
        '<a href="java\tscript:alert(1)">x</a>',
        '<a href="JaVaScRiPt:alert(1)">x</a>',
        '<a href="&#106;avascript:alert(1)">x</a>',
        '<a href="vbscript:msgbox(1)">x</a>',
        '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
        '<a href="//evil.example/x">x</a>',
        '<a href="  javascript:alert(1)">x</a>',
    ],
)
def test_sanitize_html_drops_unsafe_url_schemes(payload: str) -> None:
    sanitized = sanitize.sanitize_html(payload)

    assert "javascript:" not in sanitized.lower()
    assert "vbscript:" not in sanitized.lower()
    assert "data:text/html" not in sanitized.lower()
    assert "evil.example" not in sanitized
    assert ">x</a>" in sanitized


def test_sanitize_html_keeps_safe_urls() -> None:
    sanitized = sanitize.sanitize_html(
        '<a href="https://example.com/x?a=1">https</a>'
        '<a href="mailto:survey@example.com">mail</a>'
        '<a href="tel:+4912345">tel</a>'
        '<a href="report.pdf">relative</a>'
    )

    assert '<a href="https://example.com/x?a=1">https</a>' in sanitized
    assert '<a href="mailto:survey@example.com">mail</a>' in sanitized
    assert '<a href="tel:+4912345">tel</a>' in sanitized
    assert '<a href="report.pdf">relative</a>' in sanitized


def test_sanitize_html_drops_active_content_and_its_text() -> None:
    sanitized = sanitize.sanitize_html(
        '<script>alert(1)</script>ok'
        '<style>body{}</style>'
        '<iframe src="https://evil.example"></iframe>'
        '<svg><animate onbegin="alert(1)"></animate></svg>'
    )

    assert "alert(1)" not in sanitized
    assert "<script" not in sanitized
    assert "<style" not in sanitized
    assert "<iframe" not in sanitized
    assert "<svg" not in sanitized
    assert sanitized.endswith("ok")


def test_sanitize_html_drops_event_handler_attributes() -> None:
    sanitized = sanitize.sanitize_html(
        '<img src="https://example.com/x.png" onerror="alert(1)" onload="alert(2)">'
        '<p style="background:url(javascript:alert(1))" onclick="alert(3)">text</p>'
    )

    assert "onerror" not in sanitized
    assert "onload" not in sanitized
    assert "onclick" not in sanitized
    assert "style=" not in sanitized
    assert '<img src="https://example.com/x.png" />' in sanitized
    assert "<p>text</p>" in sanitized


def test_sanitize_html_keeps_allow_listed_markup() -> None:
    sanitized = sanitize.sanitize_html(
        "<h1>Title</h1><p><strong>bold</strong> <em>italic</em></p>"
        "<ul><li>one</li></ul>"
        "<table><thead><tr><th scope=\"col\">H</th></tr></thead>"
        "<tbody><tr><td colspan=\"2\">1</td></tr></tbody></table>"
        '<div class="meta"><span>m</span></div>'
    )

    for fragment in (
        "<h1>Title</h1>",
        "<strong>bold</strong>",
        "<em>italic</em>",
        "<li>one</li>",
        '<th scope="col">H</th>',
        '<td colspan="2">1</td>',
        '<div class="meta">',
    ):
        assert fragment in sanitized


def test_sanitize_html_escapes_text_and_closes_open_elements() -> None:
    sanitized = sanitize.sanitize_html("<em>5 < 6 &amp; 7 > 4")

    assert sanitized == "<em>5 &lt; 6 &amp; 7 &gt; 4</em>"


def test_sanitize_html_rejects_unsafe_attribute_values() -> None:
    sanitized = sanitize.sanitize_html(
        '<div class="a" onmouseover="alert(1)">x</div>'
        '<img src="https://example.com/x.png" width="javascript" height="10">'
        '<a href="mailto:a@example.com" rel="noopener evil">m</a>'
    )

    assert "onmouseover" not in sanitized
    assert "width=" not in sanitized
    assert 'height="10"' in sanitized
    assert 'rel="noopener"' in sanitized


def test_sanitize_html_handles_edges_of_the_parser() -> None:
    # Non-allow-listed elements are unwrapped, their text survives.
    assert sanitize.sanitize_html("<marquee>text</marquee>") == "text"
    # Self-closing forms of dropped and unknown elements.
    assert sanitize.sanitize_html("<iframe/><custom-el/>ok") == "ok"
    # A self-closing tag inside dropped content stays dropped.
    assert sanitize.sanitize_html("<svg><image/>alert</svg>ok") == "ok"
    # Stray end tags are ignored instead of producing broken markup.
    assert sanitize.sanitize_html("</marquee></br></em>ok") == "ok"
    # Attributes without a value and empty URLs are dropped.
    assert sanitize.sanitize_html('<a href title="t">x</a>') == '<a title="t">x</a>'
    assert sanitize.sanitize_html('<a href="">x</a>') == "<a>x</a>"
    # Comments, declarations and instructions never reach the output.
    html_body = sanitize.sanitize_html(
        "<!-- comment --><!DOCTYPE html><?php echo 1; ?><![CDATA[x]]><p>body</p>"
    )
    assert html_body == "<p>body</p>"


def test_sanitize_html_passes_through_empty_input() -> None:
    assert sanitize.sanitize_html("") == ""
    assert sanitize.sanitize_html("plain text") == "plain text"


def test_build_html_keeps_inlined_image_attachments(
    image_attachment: Attachment,
) -> None:
    html_body = html.build_html("![Alt](photo.png)", [image_attachment])

    assert 'src="data:image/png;base64' in html_body


def test_wrap_html_output_adds_style() -> None:
    wrapped = common.wrap_html_output("<p>Body</p>")
    assert wrapped.startswith("<html>")
    assert "<style>" in wrapped
    assert "Body" in wrapped


def test_build_text_handles_tables_and_metadata(sample_items: list[Item]) -> None:
    lines = text.build_text(
        sample_items, creator="User", created="2024-05-15T10:20:00Z"
    )
    assert lines[0] == "Survey response"
    assert any("Created by: User" in line for line in lines)
    assert any("Text Question" in line for line in lines)
    assert any("Attachment" in line for line in lines)
    assert any("Col A" in line for line in lines)


def test_build_text_handles_unparseable_date(sample_items: list[Item]) -> None:
    lines = text.build_text(sample_items, created="yesterday")
    assert any("Created on: yesterday" in line for line in lines)


def test_write_text_creates_file(tmp_path: Path, sample_items: list[Item]) -> None:
    dest = tmp_path / "out" / "survey.txt"
    path = text.write_text(sample_items, dest, creator="User")
    assert path == dest
    content = dest.read_text(encoding="utf-8")
    assert "Survey response" in content
    assert dest.exists()


def test_build_markdown_includes_table_and_attachments(
    sample_items: list[Item],
) -> None:
    md = markdown.build_markdown(
        sample_items, poll_id="poll-1", creator="Bob", created="2024-05-15T10:20:00Z"
    )
    assert md.startswith("# Survey response (poll-1)")
    assert "Created by: Bob" in md
    assert "| Col A | Col B |" in md
    assert "![Table Question - photo.png](photo.png)" in md
    assert "[document.bin](document.bin)" in md


def test_write_markdown_creates_file(tmp_path: Path, sample_items: list[Item]) -> None:
    dest = tmp_path / "md" / "survey.md"
    path = markdown.write_markdown(sample_items, "poll-2", dest)
    assert path == dest
    assert dest.read_text(encoding="utf-8").startswith("# Survey response (poll-2)")


def test_build_markdown_uses_raw_date_on_parse_error(
    sample_items: list[Item],
) -> None:
    md = markdown.build_markdown(
        sample_items, poll_id="poll-3", creator="Dana", created="not-a-date"
    )
    assert "Created by: Dana" in md
    assert "Created on: not-a-date" in md


def test_build_html_inlines_images_and_tables(image_attachment: Attachment) -> None:
    md_text = "# Title\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n![Alt](photo.png)"
    html_body = html.build_html(md_text, [image_attachment])
    assert "<table>" in html_body and "<td>1</td>" in html_body
    assert "data:image/png;base64" in html_body


def test_build_html_moves_metadata_into_meta_block() -> None:
    md_text = "# Title\n\nCreated by: Ada\n\nCreated on: 2024-05-01\n\nBody text."
    html_body = html.build_html(md_text, [])
    assert '<div class="meta">' in html_body
    assert "Created by:</strong> Ada" in html_body
    assert "Created on:</strong> 2024-05-01" in html_body
    assert "Created by: Ada" not in html_body
    assert "Created on: 2024-05-01" not in html_body


def test_write_html_wraps_body(tmp_path: Path, image_attachment: Attachment) -> None:
    dest = tmp_path / "html" / "survey.html"
    html.write_html("# Title", [image_attachment], dest)
    content = dest.read_text(encoding="utf-8")
    assert content.startswith("<html>")
    assert "<style>" in content


def test_write_pdf_uses_weasyprint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}

    class DummyHTML:
        def __init__(self, string: str) -> None:
            captured["string"] = string

        def write_pdf(self, destination: Path) -> None:
            destination.write_bytes(b"%PDF-1.4 dummy")
            captured["destination"] = destination

    monkeypatch.setattr(pdf, "HTML", DummyHTML)

    dest = tmp_path / "pdf" / "survey.pdf"
    result = pdf.write_pdf("<h1>Hi</h1>", dest, creator="Alice")
    assert result == dest
    assert dest.exists()
    assert "%PDF" in dest.read_bytes().decode("latin-1")
    assert "Created by" in captured["string"]


def test_write_pdf_drops_non_inline_images_but_keeps_inline_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}

    class CapturingHTML:
        def __init__(self, string: str, **_kwargs) -> None:
            captured["string"] = string

        def write_pdf(self, destination: Path) -> None:
            destination.write_bytes(b"%PDF-1.4 dummy")

    monkeypatch.setattr(pdf, "HTML", CapturingHTML)
    body = (
        '<img src="http://127.0.0.1:8080/private">'
        '<img src="file:///etc/passwd">'
        '<img src="../private.png">'
        '<img src="data:image/png;base64,AAAA">'
        '<a href="https://example.test/page">link</a>'
    )

    pdf.write_pdf(body, tmp_path / "safe.pdf")

    rendered_html = captured["string"]
    assert 'src="http://127.0.0.1:8080/private"' not in rendered_html
    assert 'src="file:///etc/passwd"' not in rendered_html
    assert 'src="../private.png"' not in rendered_html
    assert 'src="data:image/png;base64,AAAA"' in rendered_html
    assert '<a href="https://example.test/page">link</a>' in rendered_html


def test_write_csv_outputs_rows(tmp_path: Path) -> None:
    dest = tmp_path / "csv" / "survey.csv"
    rows = [("k", "label", "value", "att")]
    path = csv_export.write_csv(rows, dest)
    assert path == dest
    content = dest.read_text(encoding="utf-8").splitlines()
    assert content[0] == "Key,Field,Value,Attachments"
    assert content[1] == "k,label,value,att"


def test_write_xlsx_outputs_rows(tmp_path: Path) -> None:
    dest = tmp_path / "xlsx" / "survey.xlsx"
    rows = [("k", "label", "value", "att")]
    xlsx_export.write_xlsx(rows, dest)
    wb = load_workbook(dest)
    ws = wb.active
    assert ws.title == "Survey"
    assert ws.cell(row=1, column=1).value == "Key"
    assert ws.cell(row=2, column=2).value == "label"


def test_write_csv_escapes_formula_leading_values(tmp_path: Path) -> None:
    dest = tmp_path / "csv" / "survey.csv"
    rows = [
        ("k1", "label", "=1+1", ""),
        ("k2", "label", "+SUM(A1:A2)", ""),
        ("k3", "label", "-2+3", ""),
        ("k4", "label", "@SUM(1+1)*cmd|' /C calc'!A0", ""),
        ("k5", "label", "plain value", ""),
    ]
    csv_export.write_csv(rows, dest)

    content = dest.read_text(encoding="utf-8").splitlines()
    assert content[0] == "Key,Field,Value,Attachments"
    assert content[1] == "k1,label,'=1+1,"
    assert content[2] == "k2,label,'+SUM(A1:A2),"
    assert content[3] == "k3,label,'-2+3,"
    assert content[4] == "k4,label,'@SUM(1+1)*cmd|' /C calc'!A0,"
    assert content[5] == "k5,label,plain value,"


def test_write_xlsx_stores_formula_leading_values_as_text(tmp_path: Path) -> None:
    import zipfile

    dest = tmp_path / "xlsx" / "survey.xlsx"
    rows = [
        ("k1", "label", "=1+1", ""),
        ("k2", "label", "plain value", ""),
    ]
    xlsx_export.write_xlsx(rows, dest)

    wb = load_workbook(dest)
    ws = wb.active
    cell = ws.cell(row=2, column=3)
    assert cell.value == "=1+1"
    assert cell.data_type == "s"
    assert ws.cell(row=3, column=3).value == "plain value"

    with zipfile.ZipFile(dest) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    # The value must not be persisted as a formula element.
    assert "<f>" not in sheet
    assert "=1+1" in sheet


def test_escape_formula_value_leaves_safe_values_untouched() -> None:
    assert spreadsheet.escape_formula_value(5) == 5
    assert spreadsheet.escape_formula_value(None) is None
    assert spreadsheet.escape_formula_value("plain") == "plain"
    assert spreadsheet.escape_formula_value("text=1+1") == "text=1+1"
    assert spreadsheet.escape_formula_value("=1+1") == "'=1+1"
    assert spreadsheet.escape_formula_value("\tvalue") == "'\tvalue"
    assert spreadsheet.escape_formula_value("\rvalue") == "'\rvalue"


def test_escape_formula_row_escapes_every_cell() -> None:
    assert spreadsheet.escape_formula_row(["=a", "b", "@c"]) == ["'=a", "b", "'@c"]


def test_build_xml_handles_tables_and_attachments(
    sample_items: list[Item], image_attachment: Attachment
) -> None:
    items = [
        sample_items[0],
        Item(
            key="table",
            label="Table Question",
            values=[],
            attachments=[image_attachment],
            table=[["H1", "H2", "H3"], ["A", "B", "C"]],
            table_columns=[("col1", "Column 1")],
        ),
    ]
    xml_text = xml_export.build_xml(items, "poll-xml")
    root = ET.fromstring(xml_text.split("\n", 1)[1])
    assert root.tag == "survey_response"
    assert root.get("poll_id") == "poll-xml"
    field = root.findall("field")[1]
    table = field.find("table")
    assert table is not None
    header_row = table.findall("row")[0]
    assert header_row.get("header") == "true"
    cells = header_row.findall("cell")
    assert cells[0].get("label") == "Column 1"
    assert cells[1].get("label") is None
    attachments = field.find("attachments")
    assert attachments is not None
    attachment = attachments.find("attachment")
    assert attachment.get("is_image") == "true"


def test_write_xml_creates_file(tmp_path: Path, sample_items: list[Item]) -> None:
    dest = tmp_path / "xml" / "survey.xml"
    path = xml_export.write_xml(sample_items, "poll-xml", dest)
    assert path == dest
    assert dest.exists()
    assert dest.read_text(encoding="utf-8").startswith('<?xml version="1.0"')


def test_write_docx_writes_content(tmp_path: Path, sample_items: list[Item]) -> None:
    dest = tmp_path / "docx" / "survey.docx"
    docx_export.write_docx(sample_items, dest, poll_id="poll-doc")
    doc = Document(dest)
    assert doc.paragraphs[0].text == "Survey Response: poll-doc"
    texts = [p.text for p in doc.paragraphs if p.text]
    assert any("Text Question" in t for t in texts)
    assert any("Attachment: document.bin" in t for t in texts)
    assert doc.tables[0].cell(0, 0).text == "Col A"


def test_write_docx_formats_created_date(
    tmp_path: Path, sample_items: list[Item]
) -> None:
    dest = tmp_path / "docx" / "survey-date.docx"
    docx_export.write_docx(
        sample_items, dest, poll_id="poll-date", created="2024-05-15T10:20:00Z"
    )
    doc = Document(dest)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    assert any("May 15, 2024 at" in p for p in paragraphs)


def test_write_docx_bolds_table_header(
    tmp_path: Path, sample_items: list[Item]
) -> None:
    dest = tmp_path / "docx" / "survey-bold.docx"
    docx_export.write_docx(sample_items, dest, poll_id="poll-bold")
    doc = Document(dest)
    first_row = doc.tables[0].rows[0]
    # Verify the first header cell contains bold runs
    runs = first_row.cells[0].paragraphs[0].runs
    assert any(run.bold for run in runs)


def test_write_docx_handles_metadata_and_bad_date(
    tmp_path: Path, sample_items: list[Item]
) -> None:
    dest = tmp_path / "docx" / "survey-meta.docx"
    docx_export.write_docx(
        sample_items, dest, poll_id="poll-meta", creator="Eve", created="not-a-date"
    )
    doc = Document(dest)
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    assert any("Created by: Eve" in p for p in paragraphs)
    assert any("Created on: not-a-date" in p for p in paragraphs)


def test_build_json_handles_matrix_values(sample_items: list[Item]) -> None:
    json_text = json_export.build_json(
        sample_items, poll_id="poll-json", creator="Creator", created="2024-05-15"
    )
    payload = json.loads(json_text)
    assert payload["poll_id"] == "poll-json"
    assert payload["creator"] == "Creator"
    matrix_field = payload["fields"][2]
    assert matrix_field["values"] == [{"col1": "v1"}]
    attachment_meta = payload["fields"][1]["attachments"][0]
    assert attachment_meta["is_image"] is True


def test_write_json_creates_file(tmp_path: Path, sample_items: list[Item]) -> None:
    dest = tmp_path / "json" / "survey.json"
    path = json_export.write_json(sample_items, "poll-json", dest)
    assert path == dest
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["poll_id"] == "poll-json"
