"""Byte/text conversion helpers (ported from QD v1 libs/convert.py, simplified).

These helpers make filter functions tolerant of bytes/str/arbitrary inputs,
matching the behaviour templates from the original QD expect.
"""

import codecs
from typing import Any

try:
    codecs.lookup_error("surrogateescape")
    HAS_SURROGATEESCAPE = True
except LookupError:
    HAS_SURROGATEESCAPE = False

_COMPOSED_ERROR_HANDLERS = frozenset(
    (None, "surrogate_or_replace", "surrogate_or_strict", "surrogate_then_replace")
)


def to_bytes(obj: Any, encoding: str = "utf-8", errors: str | None = None, nonstring: str = "simplerepr") -> bytes:
    """Make sure that a string is a byte string."""
    if isinstance(obj, bytes):
        return obj

    original_errors = errors
    if errors in _COMPOSED_ERROR_HANDLERS:
        if HAS_SURROGATEESCAPE:
            errors = "surrogateescape"
        elif errors == "surrogate_or_strict":
            errors = "strict"
        else:
            errors = "replace"

    if isinstance(obj, str):
        try:
            return obj.encode(encoding, errors)
        except UnicodeEncodeError:
            if original_errors in (None, "surrogate_then_replace"):
                return_string = obj.encode("utf-8", "surrogateescape")
                return_string = return_string.decode("utf-8", "replace")
                return return_string.encode(encoding, "replace")
            raise

    # Note: We do these last even though we have to call to_bytes again on the
    # value because we're optimizing the common case
    if nonstring == "simplerepr":
        try:
            value = str(obj)
        except UnicodeError:
            try:
                value = repr(obj)
            except UnicodeError:
                # Giving up
                return b""
    elif nonstring == "passthru":
        return obj
    elif nonstring == "empty":
        return b""
    elif nonstring == "strict":
        raise TypeError(f"obj must be a string type, not {type(obj)}")
    else:
        raise TypeError(f"Invalid value {nonstring} for to_bytes' nonstring parameter")

    return to_bytes(value, encoding, errors)


def to_text(obj: Any, encoding: str = "utf-8", errors: str | None = None, nonstring: str = "simplerepr") -> str:
    """Make sure that a string is a text string."""
    if isinstance(obj, str):
        return obj

    original_errors = errors
    if errors in _COMPOSED_ERROR_HANDLERS:
        if HAS_SURROGATEESCAPE:
            errors = "surrogateescape"
        elif errors == "surrogate_or_strict":
            errors = "strict"
        else:
            errors = "replace"

    if isinstance(obj, bytes):
        try:
            return obj.decode(encoding, errors)
        except UnicodeDecodeError:
            if original_errors in (None, "surrogate_then_replace"):
                return obj.decode(encoding, "replace")
            raise

    if nonstring == "simplerepr":
        try:
            value = str(obj)
        except UnicodeError:
            try:
                value = repr(obj)
            except UnicodeError:
                return ""
    elif nonstring == "passthru":
        return obj
    elif nonstring == "empty":
        return ""
    elif nonstring == "strict":
        raise TypeError(f"obj must be a string type, not {type(obj)}")
    else:
        raise TypeError(f"Invalid value {nonstring} for to_text's nonstring parameter")

    return to_text(value, encoding, errors)


# alias matching original QD naming
to_native = to_text
