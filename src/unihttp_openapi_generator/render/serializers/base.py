"""Shared serializer-strategy scaffolding."""

from __future__ import annotations

import re
import textwrap
from abc import ABC, abstractmethod
from typing import Any

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import (
    Declaration,
    Discriminator,
    IRAlias,
    IREnum,
    IRModel,
)
from unihttp_openapi_generator.ir.types import Import

# Generated packages ship without a ``[tool.ruff]`` table, so ruff lints them with
# its default line length of 88. Wrap docstrings below that so the emitted code is
# clean under ``ruff check`` (``ruff format`` does not reflow docstring prose).
_DOCSTRING_LINE_LENGTH = 88


def literal_repr(value: Any) -> str:
    return repr(value)


def docstring(text: str | None, indent: str) -> str:
    if not text:
        return ""
    # Split into paragraphs on blank lines; normalize whitespace within each.
    paragraphs = [
        " ".join(block.split()) for block in re.split(r"\n\s*\n", text.strip()) if block.strip()
    ]
    # Sidestep an embedded closing-quote sequence (rare in API prose).
    paragraphs = [p.replace('"""', "'''") for p in paragraphs]
    if not paragraphs:
        return ""
    # Backslashes (e.g. ``curl \ -H`` from spec markdown) would raise SyntaxWarning in a
    # plain docstring, so use a raw string when any are present.
    prefix = 'r"""' if any("\\" in p for p in paragraphs) else '"""'
    # A single short paragraph stays on one line: prefix + content + ``"""``.
    if len(paragraphs) == 1:
        one_line = paragraphs[0]
        # A trailing ``"`` or ``\`` would clash with / escape the closing quotes.
        if one_line.endswith(('"', "\\")):
            one_line += " "
        if len(indent) + len(prefix) + len(one_line) + 3 <= _DOCSTRING_LINE_LENGTH:
            return f'{indent}{prefix}{one_line}"""\n'
    # Otherwise wrap each paragraph and join paragraphs with a blank line. The closing
    # ``"""`` sits on its own line, so trailing ``"``/``\`` in content is safe.
    body_width = max(_DOCSTRING_LINE_LENGTH - len(indent), 1)
    wrapped_paragraphs: list[list[str]] = []
    for paragraph in paragraphs:
        wrapped = textwrap.wrap(
            paragraph, width=body_width, break_long_words=False, break_on_hyphens=False
        )
        wrapped_paragraphs.append(wrapped or [""])
    lines: list[str] = []
    for index, wrapped in enumerate(wrapped_paragraphs):
        if index > 0:
            lines.append("")  # blank line between paragraphs
        lines.extend(f"{indent}{line}" if line else "" for line in wrapped)
    lines[0] = f"{indent}{prefix}{lines[0][len(indent) :]}"
    lines.append(f'{indent}"""')
    return "\n".join(lines) + "\n"


class SerializerStrategy(ABC):
    key: Serializer

    def __init__(self) -> None:
        # Name -> IRModel index for the document being rendered, populated by
        # ``render_models_module`` before any declaration is rendered. Used by
        # strategies that need to inspect sibling models (e.g. pydantic
        # discriminated unions). Empty unless a document context is bound.
        self.models_by_name: dict[str, IRModel] = {}
        # Names of the models that take part in an inheritance hierarchy (as a base or
        # as a subclass). Only these need keyword-only constructors -- a subclass may
        # pin an inherited field to a default (a discriminator tag) while declaring
        # required fields of its own, which positional ordering cannot express. Models
        # outside every hierarchy keep positional construction so one `allOf` subtype
        # in a spec does not silently break the constructor of every other model.
        self._kw_only_models: frozenset[str] = frozenset()

    def bind_document(self, doc: IRDocument) -> None:
        self.models_by_name = {
            decl.name: decl for decl in doc.declarations if isinstance(decl, IRModel)
        }
        hierarchy: set[str] = set()
        for model in self.models_by_name.values():
            if model.base_model is not None:
                hierarchy.add(model.name)
                hierarchy.add(model.base_model)
        self._kw_only_models = frozenset(hierarchy)

    def is_kw_only(self, model: IRModel) -> bool:
        """Whether ``model``'s constructor must be keyword-only (see ``bind_document``)."""
        return model.name in self._kw_only_models

    # -- imports ---------------------------------------------------------------

    @abstractmethod
    def model_imports(self) -> set[Import]:
        """Imports required by the declaration of a model class."""

    def declaration_imports(self, decl: Declaration) -> set[Import]:
        imports = set(decl.imports())
        if isinstance(decl, IREnum):
            imports.add(Import("enum", "IntEnum" if decl.base == "int" else "StrEnum"))
        elif isinstance(decl, IRModel):
            imports |= self.model_imports()
        return imports

    # -- declaration dispatch --------------------------------------------------

    def render_declaration(self, decl: Declaration) -> str:
        if isinstance(decl, IREnum):
            return self.render_enum(decl)
        if isinstance(decl, IRAlias):
            return self.render_alias(decl)
        body = self.render_model(decl)
        if decl.discriminator is not None:
            # A discriminated base kept as a class (inheritance mode). No serializer
            # resolves a subtype from a base-class annotation on its own, so surface
            # the mapping instead of dropping it: it is what a reader needs to wire
            # tagged decoding by hand.
            body = f"{self._discriminator_comment(decl.discriminator)}\n{body}"
        return body

    @staticmethod
    def _discriminator_comment(disc: Discriminator) -> str:
        mapping = ", ".join(f"{value}={name}" for value, name in sorted(disc.mapping.items()))
        note = f"# discriminator: {disc.property_name}"
        if mapping:
            note += f" ({mapping})"
        return f"{note}\n# subtype resolution is left to the serializer config"

    # -- shared renderers ------------------------------------------------------

    def render_enum(self, enum: IREnum) -> str:
        base = "IntEnum" if enum.base == "int" else "StrEnum"
        lines = [f"class {enum.name}({base}):"]
        doc = docstring(enum.description, "    ")
        if doc:
            lines.append(doc.rstrip("\n"))
        if not enum.members:
            lines.append("    pass")
        for member, value in enum.members:
            lines.append(f"    {member} = {literal_repr(value)}")
        return "\n".join(lines)

    def render_alias(self, alias: IRAlias) -> str:
        lines = []
        if alias.discriminator is not None:
            lines.append(
                f"# discriminator: {alias.discriminator.property_name} "
                f"(tagged-union wiring is left to the serializer config)"
            )
        lines.append(f"type {alias.name} = {alias.target.annotation()}")
        return "\n".join(lines)

    @abstractmethod
    def render_model(self, model: IRModel) -> str:
        """Render an object model class."""

    # -- serialization module --------------------------------------------------

    @abstractmethod
    def serialization_module(self, doc: IRDocument, package: str, *, resolve: bool = False) -> str:
        """Render ``_serialization.py`` defining ``request_dumper`` / ``response_loader``.

        When ``resolve`` is true (per-object file layout) the module calls
        ``resolve_forward_refs()`` from ``<package>._forward_refs`` before constructing
        any retort/dumper/loader, so cross-module annotations resolve cleanly.
        """

    # -- per-object forward-reference resolution -------------------------------

    def needs_model_rebuild(self) -> bool:
        """Whether ``resolve_forward_refs`` must call ``model_rebuild()`` per model."""
        return False
