"""Resolve ``$ref`` pointers (internal and external) while preserving component names."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from unihttp_openapi_generator.loader import _read_text, parse_spec_text


class RefError(Exception):
    """Base class for reference resolution errors."""


class CircularRefError(RefError):
    """Raised when a ``$ref`` chain forms a cycle."""


@dataclass(frozen=True)
class ResolvedRef:
    """The terminal node a ``$ref`` chain points at."""

    value: Any
    base_uri: str
    """Document URI the value lives in (for resolving nested refs)."""
    pointer: str
    """JSON pointer of the value within ``base_uri``."""
    name: str | None
    """Component name if the pointer is ``/components/<section>/<name>``."""


def _unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(doc: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return doc
    node = doc
    for raw in pointer.lstrip("/").split("/"):
        token = _unescape_token(raw)
        if isinstance(node, dict):
            if token not in node:
                raise RefError(f"pointer {pointer!r} not found at segment {token!r}")
            node = node[token]
        elif isinstance(node, list):
            try:
                node = node[int(token)]
            except (ValueError, IndexError) as exc:
                raise RefError(f"pointer {pointer!r} bad list index {token!r}") from exc
        else:
            raise RefError(f"pointer {pointer!r} traverses non-container at {token!r}")
    return node


def _component_name(pointer: str) -> str | None:
    parts = [_unescape_token(p) for p in pointer.lstrip("/").split("/")]
    if len(parts) == 3 and parts[0] == "components":
        return parts[2]
    return None


def _is_url(uri: str) -> bool:
    return urlparse(uri).scheme in ("http", "https")


def _join_uri(base_uri: str, ref_doc: str) -> str:
    """Resolve ``ref_doc`` (a document part, no fragment) against ``base_uri``."""
    if not ref_doc:
        return base_uri
    if _is_url(ref_doc):
        return ref_doc
    if _is_url(base_uri):
        return urljoin(base_uri, ref_doc)
    base_dir = os.path.dirname(base_uri)
    return os.path.normpath(os.path.join(base_dir, ref_doc))


class RefResolver:
    """Resolves ``$ref`` strings against a root document and external documents."""

    def __init__(self, root: dict[str, Any], root_uri: str = "") -> None:
        self._root_uri = root_uri
        self._docs: dict[str, Any] = {root_uri: root}

    def _document(self, uri: str) -> Any:
        if uri not in self._docs:
            self._docs[uri] = parse_spec_text(_read_text(uri))
        return self._docs[uri]

    def resolve_ref(self, ref: str, base_uri: str | None = None) -> ResolvedRef:
        """Resolve ``ref``, following ``$ref`` chains to a concrete node."""
        if not isinstance(ref, str):
            raise RefError(f"expected a $ref string, got {type(ref).__name__}: {ref!r}")
        current_base = self._root_uri if base_uri is None else base_uri
        seen: set[tuple[str, str]] = set()

        while True:
            ref_doc, fragment = urldefrag(ref)
            doc_uri = _join_uri(current_base, ref_doc)
            pointer = fragment if fragment.startswith("/") or fragment == "" else "/" + fragment

            key = (doc_uri, pointer)
            if key in seen:
                raise CircularRefError(f"circular $ref detected at {doc_uri}#{pointer}")
            seen.add(key)

            value = _resolve_pointer(self._document(doc_uri), pointer)
            current_base = doc_uri

            if isinstance(value, dict) and isinstance(value.get("$ref"), str):
                ref = value["$ref"]
                continue

            return ResolvedRef(
                value=value,
                base_uri=doc_uri,
                pointer=pointer,
                name=_component_name(pointer),
            )
