"""Render ``methods/<tag>.py`` modules: one ``BaseMethod`` dataclass per operation.

Method classes are plain ``@dataclass`` subclasses regardless of serializer; the
serializer only differs in how aliases are wired in ``_serialization.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.naming import field_name
from unihttp_openapi_generator.ir.operations import (
    BodyKind,
    IROperation,
    ParamLocation,
)
from unihttp_openapi_generator.ir.types import Import
from unihttp_openapi_generator.render.engine import render_template
from unihttp_openapi_generator.render.imports import render_import_lines
from unihttp_openapi_generator.render.serializers.base import docstring

_LOCATION_MARKER = {
    ParamLocation.PATH: "Path",
    ParamLocation.QUERY: "Query",
    ParamLocation.HEADER: "Header",
    ParamLocation.COOKIE: "Header",  # unihttp has no Cookie marker
}


def tag_module_name(tag: str) -> str:
    return field_name(tag)


def _default_repr(value: object) -> tuple[str, bool]:
    """Render a field default; second item is True if a ``field(default_factory=)``."""
    if isinstance(value, list | dict):
        return f"field(default_factory=lambda: {value!r})", True
    return repr(value), False


@dataclass(frozen=True)
class OperationField:
    """A single ordered constructor field of an operation's BaseMethod dataclass.

    Shared between the dataclass renderer (``methods.py``) and the imperative
    client-method renderer (``clients.py``) so both agree on names/types/defaults.
    """

    py_name: str
    marker: str  # Path/Query/Header/Body/File/Form
    inner: str  # the inner Python annotation (no marker, no Omittable)
    required: bool
    has_default: bool
    default: object
    is_factory: bool  # default needs ``field(default_factory=...)`` semantics


def operation_fields(op: IROperation) -> list[OperationField]:
    """Yield ordered (required first, then optional) constructor fields for ``op``."""
    required: list[OperationField] = []
    optional: list[OperationField] = []

    def add(
        name: str,
        marker: str,
        inner: str,
        is_required: bool,
        has_default: bool,
        default: object,
    ) -> None:
        is_factory = has_default and not is_required and isinstance(default, list | dict)
        spec = OperationField(name, marker, inner, is_required, has_default, default, is_factory)
        (required if is_required else optional).append(spec)

    for param in op.parameters:
        marker = _LOCATION_MARKER[param.location]
        add(
            param.name,
            marker,
            param.type.annotation(),
            param.required,
            param.has_default,
            param.default,
        )

    if op.body is not None:
        if op.body.kind is BodyKind.JSON and op.body.json_type is not None:
            # non-object JSON body (array / scalar / union): can't be spread.
            add("body", "Body", op.body.json_type.annotation(), op.body.required, False, None)
        else:
            for f in op.body.fields:
                if f.is_file:
                    marker = "File"
                elif op.body.kind is BodyKind.JSON:
                    marker = "Body"
                else:
                    marker = "Form"
                add(f.name, marker, f.type.annotation(), f.required, f.has_default, f.default)

    return [*required, *optional]


def _collect_field_lines(op: IROperation) -> tuple[list[str], set[str], bool, bool]:
    """Return (ordered field lines, marker names used, uses_omitted, uses_field)."""
    lines: list[str] = []
    markers: set[str] = set()
    uses_omitted = False
    uses_field = False

    for spec in operation_fields(op):
        markers.add(spec.marker)
        if spec.required:
            lines.append(f"{spec.py_name}: {spec.marker}[{spec.inner}]")
        elif spec.has_default:
            rendered, is_factory = _default_repr(spec.default)
            uses_field = uses_field or is_factory
            lines.append(f"{spec.py_name}: {spec.marker}[{spec.inner}] = {rendered}")
        else:
            uses_omitted = True
            lines.append(f"{spec.py_name}: {spec.marker}[Omittable[{spec.inner}]] = Omitted()")

    return lines, markers, uses_omitted, uses_field


def render_method_class(op: IROperation) -> tuple[str, set[Import]]:
    return_anno = op.return_type.annotation() if op.return_type is not None else "None"
    lines = ["@dataclass", f"class {op.class_name}(BaseMethod[{return_anno}]):"]

    doc_parts = [p for p in (op.summary, op.description) if p]
    if op.deprecated:
        doc_parts.append("Deprecated.")
    # Summary, description, and the deprecation note become separate paragraphs
    # (joined by a blank line) so ``docstring`` renders them as distinct blocks.
    doc = docstring("\n\n".join(doc_parts), "    ") if doc_parts else ""
    if doc:
        lines.append(doc.rstrip("\n"))

    lines.append(f"    __url__ = {op.path!r}")
    lines.append(f"    __method__ = {op.http_method!r}")

    field_lines, markers, uses_omitted, uses_field = _collect_field_lines(op)
    if field_lines:
        lines.append("")  # blank line between the unihttp dunders and the parameters
    for line in field_lines:
        lines.append(f"    {line}")

    imports: set[Import] = {
        Import("dataclasses", "dataclass"),
        Import("unihttp.method", "BaseMethod"),
    }
    imports |= {Import("unihttp.markers", marker) for marker in markers}
    if uses_omitted:
        imports.add(Import("unihttp.omitted", "Omitted"))
        imports.add(Import("unihttp.omitted", "Omittable"))
    if uses_field:
        imports.add(Import("dataclasses", "field"))
    imports |= op.imports()
    return "\n".join(lines), imports


def render_methods_module(doc: IRDocument, tag: str, package: str) -> str:
    operations = doc.operations_for_tag(tag)
    imports: set[Import] = set()
    model_refs: set[str] = set()
    body_parts: list[str] = []
    for op in operations:
        code, op_imports = render_method_class(op)
        body_parts.append(code)
        imports |= op_imports
        model_refs |= op.referenced_models()

    imports |= {Import(f"{package}.models", name) for name in model_refs}
    return render_template(
        "module.py.jinja",
        header_comment=f'"""Generated request methods for tag {tag!r}. Do not edit by hand."""',
        future=True,
        imports=render_import_lines(imports),
        body="\n\n\n".join(body_parts) if body_parts else "# no operations",
    )
