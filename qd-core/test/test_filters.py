"""Tests for data extraction filters."""

from qd_core.filters.extractors import extract_json_path, extract_regex, extract_value


def test_extract_json_path_simple():
    """Test simple JSON path extraction."""
    data = {"name": "test", "value": 42}
    assert extract_json_path(data, "name") == "test"
    assert extract_json_path(data, "value") == 42


def test_extract_json_path_nested():
    """Test nested JSON path extraction."""
    data = {"user": {"profile": {"name": "Alice"}}}
    assert extract_json_path(data, "user.profile.name") == "Alice"


def test_extract_json_path_array():
    """Test JSON path with array index."""
    data = {"items": [10, 20, 30]}
    assert extract_json_path(data, "items[1]") == 20


def test_extract_regex_simple():
    """Test regex extraction."""
    text = "Bearer token_abc123_end"
    result = extract_regex(text, r"token_(\w+)_end")
    assert result == "abc123"


def test_extract_regex_no_match():
    """Test regex with no match."""
    text = "No match here"
    result = extract_regex(text, r"pattern_(\d+)")
    assert result is None


def test_extract_value_json():
    """Test extract_value with JSON expression."""
    data = {"key": "value"}
    assert extract_value(data, "json:key") == "value"


def test_extract_value_literal():
    """Test extract_value with literal expression."""
    assert extract_value(None, "literal:hello") == "hello"


def test_extract_value_regex():
    """Test extract_value with regex expression."""
    assert extract_value("abc123", r"regex:(\d+)") == "123"
