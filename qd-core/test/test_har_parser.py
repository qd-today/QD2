"""Tests for HAR parser."""

import json
import pytest

from qd_core.client.har import HARParser
from qd_core.schemas.har import HARTemplate


def test_parse_qd2_template():
    """Test parsing a QD2 native template."""
    data = {
        "name": "Test Template",
        "requests": [
            {"method": "GET", "url": "https://example.com"},
        ],
    }
    template = HARParser.parse_dict(data)
    assert template.name == "Test Template"
    assert len(template.requests) == 1


def test_parse_har_format():
    """Test parsing standard HAR format."""
    data = {
        "log": {
            "creator": {"comment": "Test"},
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://example.com/api",
                        "headers": [],
                        "queryString": [],
                        "cookies": [],
                    }
                }
            ],
        }
    }
    template = HARParser.parse_dict(data)
    assert template.name == "imported_template"
    assert len(template.requests) == 1


def test_substitute_variables():
    """Test variable substitution."""
    text = "Hello {{name}}, your token is {{token}}"
    variables = {"name": "World", "token": "abc123"}
    result = HARParser.substitute_variables(text, variables)
    assert result == "Hello World, your token is abc123"


def test_substitute_no_variables():
    """Test text without variables."""
    text = "No variables here"
    result = HARParser.substitute_variables(text, {})
    assert result == "No variables here"


def test_export_template(tmp_path):
    """Test exporting a template to file."""
    template = HARTemplate(
        name="Export Test",
        requests=[{"method": "GET", "url": "https://example.com"}],
    )
    output_file = tmp_path / "test_template.json"
    HARParser.export_template(template, output_file)

    assert output_file.exists()
    data = json.loads(output_file.read_text())
    assert data["name"] == "Export Test"


def test_parse_file_not_found():
    """Test parsing a non-existent file."""
    with pytest.raises(FileNotFoundError):
        HARParser.parse_file("/nonexistent/path.json")


def test_parse_invalid_format():
    """Test parsing invalid format."""
    with pytest.raises(ValueError):
        HARParser.parse_dict({"invalid": "format"})
