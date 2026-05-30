"""Adaptix serializer strategy: plain dataclasses + a name_mapping retort."""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import Declaration, IRModel
from unihttp_openapi_generator.ir.operations import IROperation, ParamLocation
from unihttp_openapi_generator.ir.types import Import, ListType, OptionalType
from unihttp_openapi_generator.render.serializers.base import (
    SerializerStrategy,
    docstring,
    literal_repr,
)


class AdaptixStrategy(SerializerStrategy):
    key = Serializer.ADAPTIX

    def model_imports(self) -> set[Import]:
        return {Import("dataclasses", "dataclass")}

    def declaration_imports(self, decl: Declaration) -> set[Import]:
        imports = super().declaration_imports(decl)
        if isinstance(decl, IRModel):
            if self._has_factory_default(decl):
                # Qualify as ``dataclasses.field(...)`` (bare ``import dataclasses``) so a
                # model field named ``field`` can't shadow the imported helper.
                imports.add(Import("dataclasses", ""))
            if any(f.omittable for f in decl.fields):
                imports.add(Import("unihttp.omitted", "Omittable"))
                imports.add(Import("unihttp.omitted", "Omitted"))
        return imports

    @staticmethod
    def _has_factory_default(model: IRModel) -> bool:
        return any(f.has_default and isinstance(f.default, list | dict) for f in model.fields)

    def render_model(self, model: IRModel) -> str:
        lines = ["@dataclass", f"class {model.name}:"]
        doc = docstring(model.description, "    ")
        if doc:
            lines.append(doc.rstrip("\n"))
        fields = sorted(model.fields, key=lambda f: f.has_default or f.omittable)
        if not fields and not doc:
            lines.append("    pass")
        for f in fields:
            lines.append("    " + self._field_line(f.name, f.type.annotation(), f))
        return "\n".join(lines)

    @staticmethod
    def _default_repr(value: Any) -> str:
        if isinstance(value, list | dict):
            return f"dataclasses.field(default_factory=lambda: {value!r})"
        return literal_repr(value)

    def _field_line(self, name: str, annotation: str, field_obj: Any) -> str:
        # NOTE: adaptix has no built-in runtime constraint enforcement equivalent to
        # pydantic's Field(...) / msgspec.Meta(...), so IR ``constraints`` are not
        # emitted for the adaptix strategy (unsupported for now).
        if field_obj.omittable:
            return f"{name}: Omittable[{annotation}] = Omitted()"
        if not field_obj.has_default:
            return f"{name}: {annotation}"
        return f"{name}: {annotation} = {self._default_repr(field_obj.default)}"

    @staticmethod
    def _operation_alias_map(op: IROperation) -> dict[str, str]:
        amap = {p.name: p.wire_name for p in op.parameters if p.needs_alias}
        if op.body is not None:
            # JSON object bodies are spread into Body fields too, so alias them all.
            amap.update({f.name: f.wire_name for f in op.body.fields if f.needs_alias})
        return amap

    @staticmethod
    def _query_delimiter(param: Any) -> str | None:
        """Delimiter for non-exploded array query params (form/space/pipe), else None."""
        if param.location is not ParamLocation.QUERY:
            return None
        inner = param.type.inner if isinstance(param.type, OptionalType) else param.type
        if not isinstance(inner, ListType):
            return None
        if param.style == "spaceDelimited":
            return " "
        if param.style == "pipeDelimited":
            return "|"
        # ``simple`` is only spec-valid for path/header, but generators use it on query
        # arrays to mean comma-separated (same wire form as form + explode=false).
        if param.style == "simple" or param.explode is False:
            return ","
        return None

    def _query_dumpers(self, doc: IRDocument) -> list[tuple[str, str, str]]:
        result: list[tuple[str, str, str]] = []
        for op in doc.operations:
            for param in op.parameters:
                delim = self._query_delimiter(param)
                if delim is not None:
                    result.append((op.class_name, param.name, delim))
        return result

    def serialization_module(self, doc: IRDocument, package: str, *, resolve: bool = False) -> str:
        model_maps: list[tuple[str, dict[str, str]]] = []
        for decl in doc.declarations:
            if isinstance(decl, IRModel):
                alias_map = {f.name: f.wire_name for f in decl.fields if f.needs_alias}
                if alias_map:
                    model_maps.append((decl.name, alias_map))

        method_maps: list[tuple[str, dict[str, str]]] = []
        for op in doc.operations:
            amap = self._operation_alias_map(op)
            if amap:
                method_maps.append((op.class_name, amap))

        query_dumpers = self._query_dumpers(doc)
        method_targets = sorted(
            {name for name, _ in method_maps} | {cls for cls, _, _ in query_dumpers}
        )

        adaptix_names = []
        if model_maps or method_maps:
            adaptix_names.append("name_mapping")
        if query_dumpers:
            adaptix_names.extend(["P", "dumper"])

        lines = ['"""Serialization wiring (adaptix)."""', ""]
        lines.append("from unihttp.serializers.adaptix import DEFAULT_RETORT")
        if resolve:
            lines.append(f"from {package}._forward_refs import resolve_forward_refs")
        resolve_call = ["resolve_forward_refs()", ""] if resolve else []
        has_recipe = bool(model_maps or method_maps or query_dumpers)
        if has_recipe:
            if adaptix_names:
                lines.append(f"from adaptix import {', '.join(sorted(adaptix_names))}")
            if model_maps:
                names = ", ".join(sorted(name for name, _ in model_maps))
                lines.append(f"from {package}.models import {names}")
            if method_targets:
                lines.append(f"from {package}.methods import {', '.join(method_targets)}")
            lines.append("")
            lines.extend(resolve_call)
            lines.append("_RECIPE = [")
            for target, alias_map in [*model_maps, *method_maps]:
                rendered = ", ".join(f"{py!r}: {wire!r}" for py, wire in alias_map.items())
                lines.append(f"    name_mapping({target}, map={{{rendered}}}),")
            for cls, field_name_, delim in query_dumpers:
                lines.append(
                    f"    dumper(P[{cls}].{field_name_}, lambda v: "
                    f"{delim!r}.join(str(x) for x in v) if isinstance(v, list) else v),"
                )
            lines.append("]")
            lines.append("RETORT = DEFAULT_RETORT.extend(recipe=_RECIPE)")
        else:
            lines.append("")
            lines.extend(resolve_call)
            lines.append("RETORT = DEFAULT_RETORT")
        lines.append("")
        lines.append("request_dumper = RETORT")
        lines.append("response_loader = RETORT")
        return "\n".join(lines) + "\n"
