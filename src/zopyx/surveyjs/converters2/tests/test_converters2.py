"""Tests for converters2 package."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from zopyx.surveyjs.converters2 import (
    Cell,
    CellAddress,
    CellType,
    ResponseBuilder,
    SurveyConverter,
    ValueType,
    load_form_schema,
    write_csv,
    write_json,
    write_markdown,
    write_text,
    write_xml,
)


# Test fixtures

@pytest.fixture
def sample_form_schema():
    """Sample SurveyJS form schema."""
    return {
        "pages": [{
            "elements": [
                {
                    "type": "text",
                    "name": "Q1_Name",
                    "title": "Full Name"
                },
                {
                    "type": "checkbox",
                    "name": "Q2_Interests",
                    "title": "Interests",
                    "choices": [
                        {"value": "sports", "text": "Sports"},
                        {"value": "music", "text": "Music"},
                        {"value": "reading", "text": "Reading"}
                    ]
                },
                {
                    "type": "matrix",
                    "name": "Q3_Rating",
                    "title": "Product Rating",
                    "rows": [
                        {"value": "quality", "text": "Quality"},
                        {"value": "price", "text": "Value for Money"}
                    ],
                    "columns": [
                        {"value": "1", "text": "Poor"},
                        {"value": "5", "text": "Excellent"}
                    ]
                },
                {
                    "type": "matrixdynamic",
                    "name": "Q4_Orders",
                    "title": "Orders",
                    "columns": [
                        {"name": "product", "title": "Product"},
                        {"name": "qty", "title": "Quantity"},
                        {"name": "price", "title": "Price"}
                    ]
                }
            ]
        }]
    }


@pytest.fixture
def sample_response_data():
    """Sample survey response data."""
    return {
        "Q1_Name": "John Doe",
        "Q2_Interests": ["sports", "reading"],
        "Q3_Rating": {
            "quality": "5",
            "price": "4"
        },
        "Q4_Orders": [
            {"product": "Widget", "qty": "5", "price": "10.00"},
            {"product": "Gadget", "qty": "2", "price": "25.00"}
        ]
    }


@pytest.fixture
def sample_response(sample_form_schema, sample_response_data):
    """Build a Response object from fixtures."""
    builder = ResponseBuilder(sample_form_schema)
    return builder.build_from_json(
        sample_response_data,
        response_id="test-001",
        creator="john@example.com",
        created="2024-03-26T10:30:00Z"
    )


# Test types

class TestCellAddress:
    """Test CellAddress functionality."""
    
    def test_simple_address(self):
        addr = CellAddress("Q1")
        assert addr.to_path() == "Q1"
        assert addr.to_column_name() == "Q1"
    
    def test_matrix_address(self):
        addr = CellAddress("Q10", sub_key="row1")
        assert addr.to_path() == "Q10.row1"
        assert addr.to_column_name() == "Q10_row1"
    
    def test_dynamic_address(self):
        addr = CellAddress("Q12", row_index=0, sub_key="product")
        assert addr.to_path() == "Q12[0].product"
        assert addr.to_column_name() == "Q12_product"


class TestCell:
    """Test Cell functionality."""
    
    def test_cell_creation(self):
        cell = Cell(
            address=CellAddress("Q1"),
            label="Full Name",
            field_type="text",
            value="John",
            cell_type=CellType.SCALAR,
            value_type=ValueType.STRING
        )
        assert cell.column_name == "Q1"
        assert cell.value == "John"


class TestResponseBuilder:
    """Test ResponseBuilder functionality."""
    
    def test_simple_field(self, sample_form_schema):
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q1_Name": "John Doe"},
            "test-001"
        )
        
        assert len(response.cells) == 1
        cell = response.cells[0]
        assert cell.address.question_key == "Q1_Name"
        assert cell.value == "John Doe"
        assert cell.cell_type == CellType.SCALAR
    
    def test_checkbox_onehot(self, sample_form_schema):
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q2_Interests": ["sports", "reading"]},
            "test-001"
        )
        
        # Should create 3 cells (one per choice)
        cells = response.get_cells_by_question("Q2_Interests")
        assert len(cells) == 3
        
        # Check values
        by_subkey = {c.address.sub_key: c.value for c in cells}
        assert by_subkey["sports"] == 1
        assert by_subkey["music"] == 0
        assert by_subkey["reading"] == 1
    
    def test_matrix_expansion(self, sample_form_schema):
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q3_Rating": {"quality": "5", "price": "4"}},
            "test-001"
        )
        
        cells = response.get_cells_by_question("Q3_Rating")
        assert len(cells) == 2
        
        by_subkey = {c.address.sub_key: c.value for c in cells}
        assert by_subkey["quality"] == "5"
        assert by_subkey["price"] == "4"
    
    def test_matrixdynamic_table(self, sample_form_schema):
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q4_Orders": [
                {"product": "Widget", "qty": "5", "price": "10.00"},
                {"product": "Gadget", "qty": "2", "price": "25.00"}
            ]},
            "test-001"
        )
        
        cells = response.get_cells_by_question("Q4_Orders")
        assert len(cells) == 6  # 3 columns x 2 rows
        
        # Check row indices
        row_0 = [c for c in cells if c.address.row_index == 0]
        row_1 = [c for c in cells if c.address.row_index == 1]
        assert len(row_0) == 3
        assert len(row_1) == 3
    
    def test_cell_lookup(self, sample_form_schema):
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q1_Name": "John"},
            "test-001"
        )
        
        cell = response.get_cell("Q1_Name")
        assert cell is not None
        assert cell.value == "John"
        
        assert response.get_cell("NonExistent") is None


class TestExportFormats:
    """Test export format writers."""
    
    def test_write_text(self, sample_response, tmp_path):
        output = tmp_path / "output.txt"
        write_text(sample_response, output)
        
        assert output.exists()
        content = output.read_text()
        assert "John Doe" in content
        assert "test-001" in content
    
    def test_write_markdown(self, sample_response, tmp_path):
        output = tmp_path / "output.md"
        write_markdown(sample_response, output)
        
        assert output.exists()
        content = output.read_text()
        assert "John Doe" in content
        assert "# Survey Response" in content
    
    def test_write_csv_wide(self, sample_response, tmp_path):
        output = tmp_path / "output.csv"
        write_csv(sample_response, output, format="wide")
        
        assert output.exists()
        content = output.read_text()
        assert "_ResponseID" in content
        assert "test-001" in content
        assert "Q1_Name" in content
    
    def test_write_csv_long(self, sample_response, tmp_path):
        output = tmp_path / "output.csv"
        write_csv(sample_response, output, format="long")
        
        assert output.exists()
        content = output.read_text()
        # Long format should have multiple rows for dynamic content
        lines = content.strip().split("\n")
        assert len(lines) > 2  # header + at least 2 data rows
    
    def test_write_json(self, sample_response, tmp_path):
        output = tmp_path / "output.json"
        write_json(sample_response, output)
        
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["response_id"] == "test-001"
        assert data["data"]["Q1_Name"] == "John Doe"
    
    def test_write_xml(self, sample_response, tmp_path):
        output = tmp_path / "output.xml"
        write_xml(sample_response, output)
        
        assert output.exists()
        content = output.read_text()
        assert "survey_response" in content
        assert 'id="test-001"' in content


class TestSurveyConverter:
    """Test SurveyConverter integration."""
    
    def test_from_files(self, sample_form_schema, tmp_path):
        # Write schema to temp file
        form_file = tmp_path / "form.json"
        form_file.write_text(json.dumps(sample_form_schema))
        
        converter = SurveyConverter.from_files(form_file)
        assert "Q1_Name" in converter.builder.question_schemas
    
    def test_full_conversion(self, sample_form_schema, sample_response_data, tmp_path):
        form_file = tmp_path / "form.json"
        form_file.write_text(json.dumps(sample_form_schema))
        
        converter = SurveyConverter.from_files(form_file)
        response = converter.convert(
            sample_response_data,
            "resp-001",
            creator="test@example.com"
        )
        
        assert response.response_id == "resp-001"
        assert response.creator == "test@example.com"
        assert len(response.cells) > 0
    
    def test_run_multiple_formats(self, sample_form_schema, sample_response_data, tmp_path):
        form_file = tmp_path / "form.json"
        form_file.write_text(json.dumps(sample_form_schema))
        
        converter = SurveyConverter.from_files(form_file)
        response = converter.convert(sample_response_data, "test-id")
        
        output_dir = tmp_path / "output"
        paths = converter.run(
            response,
            formats={"text", "json", "csv"},
            output_dir=output_dir
        )
        
        assert len(paths) == 3
        for path in paths:
            assert path.exists()


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_response(self, sample_form_schema):
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json({}, "empty-001")
        
        assert len(response.cells) == 0
        assert response.response_id == "empty-001"
    
    def test_partial_response(self, sample_form_schema):
        """Response with only some questions answered."""
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q1_Name": "Only Name"},
            "partial-001"
        )
        
        assert len(response.cells) == 1
        assert response.cells[0].value == "Only Name"
    
    def test_unknown_question(self, sample_form_schema):
        """Response contains question not in schema."""
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Unknown_Question": "value"},
            "unknown-001"
        )
        
        # Should still create cell for unknown question
        assert len(response.cells) == 1
        assert response.cells[0].value == "value"
    
    def test_empty_checkbox(self, sample_form_schema):
        """Checkbox with no selections."""
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q2_Interests": []},
            "empty-check-001"
        )
        
        cells = response.get_cells_by_question("Q2_Interests")
        # Should still create all choice cells with value 0
        assert len(cells) == 3
        assert all(c.value == 0 for c in cells)
    
    def test_empty_matrixdynamic(self, sample_form_schema):
        """MatrixDynamic with no rows."""
        builder = ResponseBuilder(sample_form_schema)
        response = builder.build_from_json(
            {"Q4_Orders": []},
            "empty-table-001"
        )
        
        cells = response.get_cells_by_question("Q4_Orders")
        assert len(cells) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
