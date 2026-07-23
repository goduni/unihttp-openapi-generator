"""Pydantic serializer strategy: BaseModel classes with Field aliases/constraints."""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import Declaration, IRAlias, IRField, IRModel
from unihttp_openapi_generator.ir.naming import field_name
from unihttp_openapi_generator.ir.types import Import, LiteralType, RefType, UnionType
from unihttp_openapi_generator.render.serializers.base import (
    SerializerStrategy,
    docstring,
    literal_repr,
)

_CONSTRAINT_MAP = {
    "minLength": "min_length",
    "maxLength": "max_length",
    "pattern": "pattern",
    "minimum": "ge",
    "maximum": "le",
    "exclusiveMinimum": "gt",
    "exclusiveMaximum": "lt",
    "multipleOf": "multiple_of",
    "minItems": "min_length",
    "maxItems": "max_length",
}


class PydanticStrategy(SerializerStrategy):
    key = Serializer.PYDANTIC

    def model_imports(self) -> set[Import]:
        return {Import("pydantic", "BaseModel"), Import("pydantic", "ConfigDict")}

    def declaration_imports(self, decl: Declaration) -> set[Import]:
        imports = super().declaration_imports(decl)
        if isinstance(decl, IRModel) and any(self._uses_field(f) for f in decl.fields):
            # Qualify as ``pydantic.Field(...)`` (bare ``import pydantic``) so a model
            # field named ``Field`` can't shadow the imported helper.
            imports.add(Import("pydantic", ""))
        if isinstance(decl, IRAlias) and self._discriminated_union(decl) is not None:
            imports.add(Import("typing", "Annotated"))
            imports.add(Import("pydantic", "Field"))
        return imports

    def _discriminated_union(self, alias: IRAlias) -> str | None:
        """Return the discriminator field name if ``alias`` is a pydantic-tagged union.

        Guard: the alias declares a discriminator, its target is a union of
        ``RefType``s, and every referenced model carries a field named after the
        discriminator property whose type is a single-value ``Literal`` (the tag).
        """
        disc = alias.discriminator
        if disc is None or not isinstance(alias.target, UnionType):
            return None
        tag = field_name(disc.property_name)
        seen_values: set[Any] = set()
        for member in alias.target.members:
            if not isinstance(member, RefType):
                return None
            model = self.models_by_name.get(member.name)
            if model is None:
                return None
            tag_field = next((f for f in model.fields if f.name == tag), None)
            if tag_field is None or not isinstance(tag_field.type, LiteralType):
                return None
            if len(tag_field.type.values) != 1:
                return None
            value = tag_field.type.values[0]
            # pydantic rejects a discriminated union where two members share a tag
            # value; fall back to a plain union when any value repeats.
            if value in seen_values:
                return None
            seen_values.add(value)
        return tag

    def render_alias(self, alias: IRAlias) -> str:
        tag = self._discriminated_union(alias)
        if tag is None:
            return super().render_alias(alias)
        union = alias.target.annotation()
        return f"type {alias.name} = Annotated[{union}, Field(discriminator={tag!r})]"

    @classmethod
    def _uses_field(cls, field_obj: IRField) -> bool:
        # A field needs ``Field(...)`` if it has an alias, has constraints, or its
        # python name must be rewritten (leading underscore / reserved member) — the
        # rewrite implies an alias so serialization stays on the wire name.
        return bool(
            field_obj.needs_alias
            or field_obj.constraints
            or cls._pydantic_field_name(field_obj.name) != field_obj.name
        )

    # Names that pydantic reserves on ``BaseModel`` (v1 + v2 attrs/methods). A model
    # field with any of these names would shadow an inherited member.
    _RESERVED_NAMES = frozenset(
        {
            "model_config",
            "model_fields",
            "model_extra",
            "model_computed_fields",
            "validate",
            "construct",
            "copy",
            "dict",
            "json",
            "schema",
            "schema_json",
            "parse_obj",
            "parse_raw",
            "parse_file",
            "from_orm",
            "model_dump",
            "model_dump_json",
            "model_validate",
            "model_validate_json",
            "model_construct",
            "model_copy",
            "model_rebuild",
            "model_json_schema",
        }
    )

    @classmethod
    def _pydantic_field_name(cls, name: str) -> str:
        """Map an IR field name to a pydantic-safe python attribute name.

        - Leading underscores are forbidden by pydantic: strip them, and prefix
          ``field_`` if the result is empty or starts with a digit.
        - Names that collide with a reserved ``BaseModel`` member get a ``_`` suffix.
        When the result differs from the wire name the renderer emits ``alias=``.
        """
        safe = name
        if safe.startswith("_"):
            safe = safe.lstrip("_")
            if not safe or safe[0].isdigit():
                safe = f"field_{safe}"
        # ``model_*`` is pydantic's protected namespace; a trailing ``_`` would keep the
        # prefix and still warn, so prefix these to move them out of the namespace.
        if safe.startswith("model_"):
            safe = f"field_{safe}"
        elif safe in cls._RESERVED_NAMES:
            safe = f"{safe}_"
        return safe

    def render_model(self, model: IRModel) -> str:
        lines = [f"class {model.name}({model.base_model or 'BaseModel'}):"]
        doc = docstring(model.description, "    ")
        if doc:
            lines.append(doc.rstrip("\n"))
        lines.append("    model_config = ConfigDict(populate_by_name=True)")
        for f in model.fields:
            lines.append("    " + self._field_line(f))
        return "\n".join(lines)

    def _field_line(self, f: IRField) -> str:
        annotation = f.type.annotation()
        py_name = self._pydantic_field_name(f.name)
        args: list[str] = []
        # Emit an alias whenever the rendered python name differs from the wire name
        # (covers genuine aliases as well as leading-underscore / reserved rewrites).
        if py_name != f.wire_name:
            args.append(f"alias={f.wire_name!r}")
        for key, pyd_key in _CONSTRAINT_MAP.items():
            if key in f.constraints:
                args.append(f"{pyd_key}={literal_repr(f.constraints[key])}")

        if f.has_default:
            default = self._default_arg(f.default)
            if args:
                return f"{py_name}: {annotation} = pydantic.Field({default}, {', '.join(args)})"
            if isinstance(f.default, list | dict):
                return f"{py_name}: {annotation} = pydantic.Field({default})"
            return f"{py_name}: {annotation} = {literal_repr(f.default)}"
        if args:
            return f"{py_name}: {annotation} = pydantic.Field({', '.join(args)})"
        return f"{py_name}: {annotation}"

    @staticmethod
    def _default_arg(value: Any) -> str:
        if isinstance(value, list | dict):
            return f"default_factory=lambda: {value!r}"
        return f"default={literal_repr(value)}"

    def needs_model_rebuild(self) -> bool:
        return True

    def serialization_module(self, doc: IRDocument, package: str, *, resolve: bool = False) -> str:
        imports = "from unihttp.serializers.pydantic import PydanticDumper, PydanticLoader\n"
        if resolve:
            imports += f"from {package}._forward_refs import resolve_forward_refs\n"
        body = "request_dumper = PydanticDumper()\nresponse_loader = PydanticLoader()\n"
        if resolve:
            body = f"resolve_forward_refs()\n\n{body}"
        return f'"""Serialization wiring (pydantic)."""\n\n{imports}\n{body}'
