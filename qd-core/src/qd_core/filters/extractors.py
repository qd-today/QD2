"""Data extraction filters for QD2.

Provides utilities for extracting values from HTTP responses.
"""

import json
import re
from typing import Any, Optional


def extract_json_path(data: Any, path: str) -> Any:
    """Extract a value from JSON data using a dot-notation path.

    Args:
        data: Parsed JSON data (dict, list, or primitive).
        path: Dot-notation path (e.g., 'data.items[0].name').

    Returns:
        The extracted value, or None if not found.

    Examples:
        >>> extract_json_path({"data": {"name": "test"}}, "data.name")
        'test'
        >>> extract_json_path({"items": [1, 2, 3]}, "items[1]")
        2
    """
    parts = re.split(r'\.(?![^\[]*\])', path)
    current = data

    for part in parts:
        # Handle array index: items[0]
        match = re.match(r'(\w+)\[(\d+)\]', part)
        if match:
            key, index = match.groups()
            current = current[key][int(index)]
        else:
            current = current[part]

    return current


def extract_regex(text: str, pattern: str, group: int = 1) -> Optional[str]:
    """Extract a value from text using a regex pattern.

    Args:
        text: The text to search.
        pattern: Regex pattern with optional capture groups.
        group: The capture group to return (default: 1).

    Returns:
        The matched group, or None if no match.
    """
    match = re.search(pattern, text)
    if match:
        try:
            return match.group(group)
        except IndexError:
            return match.group(0)
    return None


def extract_value(data: Any, expression: str) -> Any:
    """Extract a value using an expression.

    Supports:
    - JSON path: json:data.key.subkey
    - Regex: regex:pattern
    - Header: header:Header-Name
    - Literal: literal:value

    Args:
        data: The data to extract from.
        expression: The extraction expression.

    Returns:
        The extracted value.
    """
    if expression.startswith("json:"):
        path = expression[5:]
        return extract_json_path(data, path)

    if expression.startswith("regex:"):
        pattern = expression[6:]
        if isinstance(data, str):
            return extract_regex(data, pattern)
        return extract_regex(json.dumps(data), pattern)

    if expression.startswith("header:"):
        header_name = expression[7:]
        if isinstance(data, dict):
            return data.get(header_name)
        return None

    if expression.startswith("literal:"):
        return expression[8:]

    # Default: return as-is
    return data
