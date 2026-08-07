"""Render ``client.pyi``: the client's public surface with explicit method signatures.

``client.py`` binds operations declaratively (``get_pet = bind_method(GetPet)``).
mypy resolves the resulting ``ParamSpec``-through-descriptor overloads; PyCharm does
not, so the editor shows no signature for any operation. A stub sidesteps that
without touching the runtime module: type checkers and IDEs read ``client.pyi``
instead, and it spells every operation out as a plain ``def``.

Signatures come from :func:`~unihttp_openapi_generator.render.methods.method_signature`,
the same helper ``--style imperative`` uses, so the two renderings cannot drift.
"""

from __future__ import annotations

from unihttp_openapi_generator.config import GeneratorConfig, Layout
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.naming import class_name, field_name
from unihttp_openapi_generator.ir.operations import IROperation
from unihttp_openapi_generator.ir.types import Import
from unihttp_openapi_generator.render.auth import AuthCredential, iter_auth_credentials
from unihttp_openapi_generator.render.clients import (
    ASYNC_BACKENDS,
    SYNC_BACKENDS,
    async_client_name,
    flat_client_attributes,
    sync_client_name,
)
from unihttp_openapi_generator.render.engine import render_template
from unihttp_openapi_generator.render.imports import render_import_lines
from unihttp_openapi_generator.render.methods import method_signature, signatures_use_omitted
from unihttp_openapi_generator.render.serializers.base import docstring


def _method_lines(op: IROperation, attr: str, *, is_async: bool) -> list[str]:
    """One stubbed operation: its signature, the spec's prose, and an empty body."""
    lines = [f"    {method_signature(op, attr, is_async=is_async)}"]
    doc_parts = [p for p in (op.summary, op.description) if p]
    if op.deprecated:
        doc_parts.append("Deprecated.")
    # Same paragraph handling as the request dataclass docstring; PyCharm surfaces
    # this on hover and in parameter info, which is most of the point of the stub.
    doc = docstring("\n\n".join(doc_parts), "        ") if doc_parts else ""
    if doc:
        lines.append(doc.rstrip("\n"))
    lines.append("        ...")
    return lines


def _init_line(doc: IRDocument, creds: list[AuthCredential]) -> str:
    """``__init__`` as the runtime client declares it, minus the body."""
    default = "DEFAULT_BASE_URL" if doc.base_url else '""'
    params = [
        f"base_url: str = {default}",
        "*",
        "session: Any = None",
        "middleware: list[Any] | None = None",
    ]
    params.extend(f"{c.param_name}: {c.py_type} = None" for c in creds)
    return f"    def __init__(self, {', '.join(params)}) -> None: ..."


def _subclient(doc: IRDocument, tag: str, *, is_async: bool) -> str:
    prefix = "Async" if is_async else ""
    lines = [f"class {prefix}{class_name(tag)}Client:"]
    lines.append("    def __init__(self, root: Any) -> None: ...")
    kw = "async def" if is_async else "def"
    lines.append(
        f"    {kw} call_method(self, method: BaseMethod[ResponseType]) -> ResponseType: ..."
    )
    for op in doc.operations_for_tag(tag):
        lines.extend(_method_lines(op, op.method_name, is_async=is_async))
    return "\n".join(lines)


def _grouped_root(
    doc: IRDocument, backend_cls: str, creds: list[AuthCredential], *, is_async: bool
) -> str:
    name = async_client_name(doc.title) if is_async else sync_client_name(doc.title)
    prefix = "Async" if is_async else ""
    lines = [f"class {name}({backend_cls}):"]
    # The runtime assigns these in ``__init__``; a stub declares them as attributes.
    lines.extend(f"    {field_name(tag)}: {prefix}{class_name(tag)}Client" for tag in doc.tags)
    lines.append(_init_line(doc, creds))
    return "\n".join(lines)


def _flat_root(
    doc: IRDocument, backend_cls: str, creds: list[AuthCredential], *, is_async: bool
) -> str:
    name = async_client_name(doc.title) if is_async else sync_client_name(doc.title)
    lines = [f"class {name}({backend_cls}):", _init_line(doc, creds)]
    for attr, op in flat_client_attributes(doc):
        lines.extend(_method_lines(op, attr, is_async=is_async))
    return "\n".join(lines)


def _signature_imports(doc: IRDocument, package: str) -> set[Import]:
    """Everything the spelled-out signatures reference."""
    imports: set[Import] = {Import("typing", "Any")}
    model_refs: set[str] = set()
    for op in doc.operations:
        imports |= op.imports()
        model_refs |= op.referenced_models()
    imports |= {Import(f"{package}.models", name) for name in model_refs}
    if signatures_use_omitted(doc.operations):
        imports.add(Import("unihttp.omitted", "Omittable"))
        imports.add(Import("unihttp.omitted", "Omitted"))
    return imports


def render_client_stub(doc: IRDocument, config: GeneratorConfig, package: str) -> str:
    grouped = config.resolve_layout(len(doc.tags)) is Layout.GROUPED
    creds = iter_auth_credentials(doc)

    imports = _signature_imports(doc, package)
    if grouped:
        imports.add(Import("unihttp.method", "BaseMethod"))
        imports.add(Import("unihttp.method", "ResponseType"))

    parts: list[str] = []
    if doc.servers:
        parts.append("SERVERS: dict[str, str]")
    if doc.base_url:
        parts.append("DEFAULT_BASE_URL: str")

    def emit_side(backend_cls: str, *, is_async: bool) -> None:
        if grouped:
            parts.extend(_subclient(doc, tag, is_async=is_async) for tag in doc.tags)
            parts.append(_grouped_root(doc, backend_cls, creds, is_async=is_async))
        else:
            parts.append(_flat_root(doc, backend_cls, creds, is_async=is_async))

    if config.emit_sync:
        backend_cls, backend_mod = SYNC_BACKENDS[config.sync_backend]
        imports.add(Import(backend_mod, backend_cls))
        emit_side(backend_cls, is_async=False)
    if config.emit_async:
        backend_cls, backend_mod = ASYNC_BACKENDS[config.async_backend]
        imports.add(Import(backend_mod, backend_cls))
        emit_side(backend_cls, is_async=True)

    return render_template(
        "module.py.jinja",
        header_comment='"""Type stubs for the generated API client. Do not edit by hand."""',
        future=False,
        imports=render_import_lines(imports),
        body="\n\n".join(parts),
    )
