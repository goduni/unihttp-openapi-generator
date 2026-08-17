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

#: Indent every field line sits at inside a method class body.
_FIELD_INDENT = "    "

_LOCATION_MARKER = {
    ParamLocation.PATH: "Path",
    ParamLocation.QUERY: "Query",
    ParamLocation.HEADER: "Header",
    ParamLocation.COOKIE: "Header",  # unihttp has no Cookie marker
}


def tag_module_name(tag: str) -> str:
    return field_name(tag)


def _unindent(line: str) -> str:
    """Strip one class-body indent, so ``render_method_class`` can add it back."""
    return line[len(_FIELD_INDENT) :] if line.startswith(_FIELD_INDENT) else line


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
    description: str | None = None  # schema prose, rendered as an attribute docstring


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
        description: str | None = None,
    ) -> None:
        is_factory = has_default and not is_required and isinstance(default, list | dict)
        spec = OperationField(
            name, marker, inner, is_required, has_default, default, is_factory, description
        )
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
            param.description,
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
                add(
                    f.name,
                    marker,
                    f.type.annotation(),
                    f.required,
                    f.has_default,
                    f.default,
                    f.description,
                )

    return [*required, *optional]


def method_receiver(op: IROperation) -> str:
    """The name to give a client method's receiver -- ``self`` unless a parameter took it.

    ``self`` is a perfectly legal parameter name in a spec, and the request dataclass
    carries it as a field: ``dataclasses`` renames *its* receiver to
    ``__dataclass_self__`` in that case, so ``GetA(self=...)`` works at runtime. A
    client method has to do the same, or it emits ``def get_a(self, *, self: str)`` --
    a duplicate-argument syntax error that takes the whole generation down.
    """
    taken = {spec.py_name for spec in operation_fields(op)}
    receiver = "self"
    while receiver in taken:
        receiver += "_"
    return receiver


def method_signature(op: IROperation, attr: str, *, is_async: bool) -> str:
    """The ``def`` header for ``op`` as a client method, without a body.

    Shared by the imperative client renderer and the stub renderer so the two can
    never disagree on parameter names, types, order, or defaults. The parameter list
    mirrors the operation's ``BaseMethod`` dataclass fields exactly, keyword-only,
    required first.
    """
    params: list[str] = []
    for spec in operation_fields(op):
        if spec.required:
            params.append(f"{spec.py_name}: {spec.inner}")
        elif spec.has_default and not spec.is_factory:
            params.append(f"{spec.py_name}: {spec.inner} = {spec.default!r}")
        else:
            # No default, or a mutable one that can't be a literal arg default.
            params.append(f"{spec.py_name}: Omittable[{spec.inner}] = Omitted()")

    receiver = method_receiver(op)
    signature = ", ".join([receiver, "*", *params]) if params else receiver
    return_anno = op.return_type.annotation() if op.return_type is not None else "None"
    prefix = "async def" if is_async else "def"
    # A receiver that had to move aside for a parameter named ``self`` is the one place
    # the generated client knowingly breaks the naming rule its own lint config enforces
    # -- silence it here rather than switching N805 off for every method in the package.
    noqa = "  # noqa: N805" if receiver != "self" else ""
    return f"{prefix} {attr}({signature}) -> {return_anno}:{noqa}"


def signatures_use_omitted(ops: list[IROperation]) -> bool:
    """Whether any signature from ``method_signature`` needs ``Omittable``/``Omitted``."""
    return any(
        not spec.required and (not spec.has_default or spec.is_factory)
        for op in ops
        for spec in operation_fields(op)
    )


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
        # PEP 258 attribute docstring: the only place a parameter's / body field's
        # schema prose can land without changing the constructor signature. Rendered
        # at the indent it will actually sit at -- ``docstring`` wraps to
        # ``88 - len(indent)`` columns -- then unindented, because the caller adds the
        # class-body indent back to every line it gets.
        doc = docstring(spec.description, _FIELD_INDENT)
        if doc:
            lines.extend(_unindent(line) for line in doc.rstrip("\n").split("\n"))

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
        # A blank docstring paragraph separator must stay blank: indenting it would
        # write trailing whitespace inside the string literal, which no formatter strips.
        lines.append(f"{_FIELD_INDENT}{line}" if line else "")

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
