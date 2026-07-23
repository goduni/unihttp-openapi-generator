"""Identifier conversion, sanitization and collision handling."""

from __future__ import annotations

import keyword
import re

_WORD_BOUNDARY = re.compile(r"[^0-9a-zA-Z]+")
_LOWER_UPPER = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_UPPER_RUN = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")

# Soft keywords (``type``, ``match``, ``case``, ``_``) are legal identifiers, and a
# spec field named ``type`` is common enough that suffixing it would be noise. Only
# ``_`` is reserved: it is conventionally a throwaway name and reads as a bug in a
# field/parameter position.
_RESERVED_SOFT_KEYWORDS = frozenset({"_"})


def _split_words(name: str) -> list[str]:
    spaced = _WORD_BOUNDARY.sub(" ", name)
    spaced = _LOWER_UPPER.sub(" ", spaced)
    spaced = _UPPER_RUN.sub(" ", spaced)
    return [w for w in spaced.split() if w]


def to_snake_case(name: str) -> str:
    words = _split_words(name)
    return "_".join(w.lower() for w in words)


def to_pascal_case(name: str) -> str:
    words = _split_words(name)
    return "".join(w[:1].upper() + w[1:] for w in words)


def sanitize_identifier(name: str, *, fallback: str = "field") -> str:
    """Return a valid, non-keyword Python identifier derived from ``name``."""
    candidate = name or fallback
    if not candidate.isidentifier():
        candidate = _WORD_BOUNDARY.sub("_", candidate).strip("_") or fallback
    if candidate and candidate[0].isdigit():
        candidate = f"_{candidate}"
    if keyword.iskeyword(candidate) or candidate in _RESERVED_SOFT_KEYWORDS:
        candidate = f"{candidate}_"
    return candidate


def field_name(wire_name: str) -> str:
    """Python field name for a wire name (snake_case, sanitized)."""
    return sanitize_identifier(to_snake_case(wire_name) or wire_name, fallback="field")


def class_name(raw: str) -> str:
    """Python class name for a schema/operation (PascalCase, sanitized)."""
    pascal = to_pascal_case(raw) or "Model"
    return sanitize_identifier(pascal, fallback="Model")


def method_name(operation_id: str) -> str:
    """Python method name for an operationId (snake_case, sanitized)."""
    return sanitize_identifier(to_snake_case(operation_id) or operation_id, fallback="call")


class NameRegistry:
    """Hands out unique names, appending numeric suffixes on collision."""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def reserve(self, preferred: str) -> str:
        candidate = preferred
        counter = 2
        while candidate in self._used:
            candidate = f"{preferred}{counter}"
            counter += 1
        self._used.add(candidate)
        return candidate

    def __contains__(self, name: str) -> bool:
        return name in self._used
