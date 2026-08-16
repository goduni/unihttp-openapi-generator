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
    IRField,
    IRModel,
)
from unihttp_openapi_generator.ir.types import Import

# Generated packages ship without a ``[tool.ruff]`` table, so ruff lints them with
# its default line length of 88. Wrap docstrings below that so the emitted code is
# clean under ``ruff check`` (``ruff format`` does not reflow docstring prose).
_DOCSTRING_LINE_LENGTH = 88


def literal_repr(value: Any) -> str:
    return repr(value)


def default_source(f: IRField) -> str:
    """Python source for a field's default value.

    ``IRField.default_expr`` wins when set: an enum-typed discriminator tag has to be
    written as ``ButtonKind.CALLBACK``, which ``repr`` of the underlying ``'callback'``
    cannot produce. Only ever a scalar, so callers keep their own list/dict
    ``default_factory`` branch ahead of this.
    """
    return f.default_expr if f.default_expr is not None else literal_repr(f.default)


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
    for index, paragraph in enumerate(paragraphs):
        # The opening ``\"\"\"`` shares the first line of the first paragraph, so that
        # line has ``len(prefix)`` fewer columns to play with. Budgeting it as an
        # initial indent (stripped again below) keeps every emitted line inside the
        # limit instead of overshooting it by exactly the quotes.
        wrapped = textwrap.wrap(
            paragraph,
            width=body_width,
            initial_indent=" " * len(prefix) if index == 0 else "",
            break_long_words=False,
            break_on_hyphens=False,
        )
        if index == 0 and wrapped:
            wrapped[0] = wrapped[0][len(prefix) :]
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

    def inherited_field_names(self, model: IRModel) -> set[str]:
        """Python attribute names ``model`` inherits from its whole base chain."""
        names: set[str] = set()
        seen: set[str] = set()
        current = model.base_model
        while current is not None and current not in seen:
            seen.add(current)
            parent = self.models_by_name.get(current)
            if parent is None:
                break
            names |= {f.name for f in parent.fields}
            current = parent.base_model
        return names

    @staticmethod
    def override_suppression(f: IRField) -> str:
        """Trailing comment for a field the subtype re-declares incompatibly.

        ``unused-ignore`` is listed alongside ``assignment`` on purpose: the builder
        decides whether an override is compatible from the IR alone, and the IR is a
        coarser view of the type than mypy's. It has no notion of the numeric tower
        beyond ``int``/``float``, and a ``$ref`` narrowed to a schema that is itself a
        subtype resolves to a plain ``RefType`` whose relation to the base's is not
        visible in the annotation. Whenever the builder is stricter than mypy the bare
        ``[assignment]`` ignore would be unused, which ``--strict`` reports as an error
        of its own -- so the comment silences its own redundancy.
        """
        if not f.incompatible_override:
            return ""
        return "  # type: ignore[assignment, unused-ignore]"

    @staticmethod
    def field_doc_lines(f: IRField) -> list[str]:
        """A field's schema prose as a PEP 258 attribute docstring.

        The same device the method classes already use for parameters and body fields,
        and for the same reason: it is the one place the prose can land without
        touching the constructor signature or the decoded value. It also renders
        identically for all three serializers, where the native mechanisms do not --
        pydantic would need ``Field(description=...)`` on every documented field,
        msgspec an ``Annotated[..., Meta(description=...)]``, and adaptix has no
        equivalent at all.

        Rendered at the class-body indent, which is where every strategy puts it.
        """
        doc = docstring(f.description, "    ")
        if not doc:
            return []
        return doc.rstrip("\n").split("\n")

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
        # A discriminated base kept as a class (inheritance mode). No serializer
        # resolves a subtype from a base-class annotation on its own, so surface the
        # mapping instead of dropping it: it is what a reader needs to wire tagged
        # decoding by hand. The mapping alone is the gate -- without one there is
        # nothing to say, and the note would announce a concrete model (a leaf
        # subclass, or a plain object that merely names a discriminator property) as a
        # union base. ``base_model`` is no proxy for it: a subclass is the opposite of
        # a union base, while a base kept as a class always has a mapping.
        if decl.discriminator is not None and decl.discriminator.mapping:
            body = f"{self._discriminator_comment(decl.discriminator)}\n{body}"
        return body

    @staticmethod
    def _discriminator_comment(disc: Discriminator) -> str:
        """The value -> class mapping a reader needs to wire tagged decoding by hand."""
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
        if alias.discriminator is not None and alias.discriminator.mapping:
            # Same note (and the same gate) a discriminated base kept as a class gets:
            # a mapping-less discriminator leaves nothing for a reader to wire from.
            lines.append(self._discriminator_comment(alias.discriminator))
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
