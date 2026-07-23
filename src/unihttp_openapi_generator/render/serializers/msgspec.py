"""msgspec serializer strategy: msgspec.Struct classes with field(name=...) aliases."""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import Declaration, IRField, IRModel
from unihttp_openapi_generator.ir.types import Import
from unihttp_openapi_generator.render.serializers.base import (
    SerializerStrategy,
    docstring,
    literal_repr,
)

# OpenAPI constraint key -> msgspec.Meta keyword argument.
_META_MAP = {
    "minimum": "ge",
    "maximum": "le",
    "exclusiveMinimum": "gt",
    "exclusiveMaximum": "lt",
    "minLength": "min_length",
    "maxLength": "max_length",
    "minItems": "min_length",
    "maxItems": "max_length",
    "pattern": "pattern",
    "multipleOf": "multiple_of",
}


class MsgspecStrategy(SerializerStrategy):
    key = Serializer.MSGSPEC

    def model_imports(self) -> set[Import]:
        return {Import("msgspec", "Struct")}

    def declaration_imports(self, decl: Declaration) -> set[Import]:
        imports = super().declaration_imports(decl)
        if isinstance(decl, IRModel):
            if any(self._uses_field(f) for f in decl.fields):
                # Qualify as ``msgspec.field(...)`` (bare ``import msgspec``) so a model
                # field literally named ``field`` can't shadow the imported helper.
                imports.add(Import("msgspec", ""))
            if any(self._meta_args(f) for f in decl.fields):
                imports.add(Import("msgspec", "Meta"))
                imports.add(Import("typing", "Annotated"))
        return imports

    @staticmethod
    def _meta_args(f: IRField) -> list[str]:
        return [
            f"{meta_key}={literal_repr(f.constraints[key])}"
            for key, meta_key in _META_MAP.items()
            if key in f.constraints
        ]

    @staticmethod
    def _uses_field(f: IRField) -> bool:
        return bool(f.needs_alias or f.has_default)

    @staticmethod
    def _sort_key(f: IRField) -> tuple[bool, bool]:
        # msgspec/dataclass ordering: required before defaulted (primary), and among
        # required, bare fields before those rendered as ``= field(name=...)`` (secondary).
        # A required aliased field has no real default, so it must NOT sort with defaulted ones.
        return (f.has_default, f.needs_alias)

    def render_model(self, model: IRModel) -> str:
        # See the adaptix strategy: inheritance forces keyword-only constructors.
        options = ", kw_only=True" if self.is_kw_only(model) else ""
        lines = [f"class {model.name}({model.base_model or 'Struct'}{options}):"]
        doc = docstring(model.description, "    ")
        if doc:
            lines.append(doc.rstrip("\n"))
        fields = sorted(model.fields, key=self._sort_key)
        for f in fields:
            lines.append("    " + self._field_line(f))
        if not fields and not doc:
            lines.append("    pass")
        return "\n".join(lines)

    def _field_line(self, f: IRField) -> str:
        annotation = f.type.annotation()
        meta_args = self._meta_args(f)
        if meta_args:
            annotation = f"Annotated[{annotation}, Meta({', '.join(meta_args)})]"
        args: list[str] = []
        if f.needs_alias:
            args.append(f"name={f.wire_name!r}")
        if f.has_default:
            if isinstance(f.default, list | dict):
                args.append(f"default_factory=lambda: {f.default!r}")
            else:
                args.append(f"default={literal_repr(f.default)}")
        if args:
            return f"{f.name}: {annotation} = msgspec.field({', '.join(args)})"
        return f"{f.name}: {annotation}"

    def serialization_module(self, doc: IRDocument, package: str, *, resolve: bool = False) -> str:
        imports = "from unihttp.serializers.msgspec import MsgspecDumper, MsgspecLoader\n"
        if resolve:
            imports += f"from {package}._forward_refs import resolve_forward_refs\n"
        body = "request_dumper = MsgspecDumper()\nresponse_loader = MsgspecLoader()\n"
        if resolve:
            body = f"resolve_forward_refs()\n\n{body}"
        return f'"""Serialization wiring (msgspec)."""\n\n{imports}\n{body}'

    @staticmethod
    def _default_repr(value: Any) -> str:  # pragma: no cover - parity helper
        return literal_repr(value)
