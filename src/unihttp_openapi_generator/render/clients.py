"""Render ``client.py``: a flat client or per-tag sub-clients delegating to a root."""

from __future__ import annotations

from unihttp_openapi_generator.config import (
    AsyncBackend,
    GeneratorConfig,
    Layout,
    MethodStyle,
    SyncBackend,
)
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.naming import NameRegistry, class_name, field_name
from unihttp_openapi_generator.ir.operations import IROperation
from unihttp_openapi_generator.ir.types import Import
from unihttp_openapi_generator.render.auth import (
    AuthCredential,
    iter_auth_credentials,
    needs_base64,
)
from unihttp_openapi_generator.render.engine import render_template
from unihttp_openapi_generator.render.imports import render_import_lines
from unihttp_openapi_generator.render.methods import (
    operation_fields,
    tag_module_name,
)
from unihttp_openapi_generator.render.query import deep_object_query_keys

_SYNC_BACKENDS: dict[SyncBackend, tuple[str, str]] = {
    SyncBackend.HTTPX: ("HTTPXSyncClient", "unihttp.clients.httpx"),
    SyncBackend.REQUESTS: ("RequestsSyncClient", "unihttp.clients.requests"),
    SyncBackend.NIQUESTS: ("NiquestsSyncClient", "unihttp.clients.niquests"),
    SyncBackend.ZAPROS: ("ZaprosSyncClient", "unihttp.clients.zapros"),
}
_ASYNC_BACKENDS: dict[AsyncBackend, tuple[str, str]] = {
    AsyncBackend.HTTPX: ("HTTPXAsyncClient", "unihttp.clients.httpx"),
    AsyncBackend.AIOHTTP: ("AiohttpAsyncClient", "unihttp.clients.aiohttp"),
    AsyncBackend.NIQUESTS: ("NiquestsAsyncClient", "unihttp.clients.niquests"),
    AsyncBackend.ZAPROS: ("ZaprosAsyncClient", "unihttp.clients.zapros"),
}


def sync_client_name(title: str) -> str:
    return f"{class_name(title)}Client"


def async_client_name(title: str) -> str:
    return f"Async{class_name(title)}Client"


def _imperative_method_lines(op: IROperation, attr: str, *, is_async: bool) -> list[str]:
    """Render an explicit typed wrapper method delegating to ``self.call_method``.

    The parameter list mirrors the operation's ``BaseMethod`` dataclass fields
    exactly (names, types, defaults), keyword-only, required first.
    """
    fields = operation_fields(op)
    params: list[str] = []
    for spec in fields:
        if spec.required:
            params.append(f"{spec.py_name}: {spec.inner}")
        elif spec.has_default:
            if spec.is_factory:
                # Mutable defaults can't be literal arg defaults; wrap as Omittable.
                params.append(f"{spec.py_name}: Omittable[{spec.inner}] = Omitted()")
            else:
                params.append(f"{spec.py_name}: {spec.inner} = {spec.default!r}")
        else:
            params.append(f"{spec.py_name}: Omittable[{spec.inner}] = Omitted()")

    signature = ", ".join(["self", "*", *params]) if params else "self"
    return_anno = op.return_type.annotation() if op.return_type is not None else "None"
    ctor_args = ", ".join(f"{spec.py_name}={spec.py_name}" for spec in fields)
    call = f"self.call_method({op.class_name}({ctor_args}))"
    prefix = "async def" if is_async else "def"
    body = f"return await {call}" if is_async else f"return {call}"
    return [
        f"    {prefix} {attr}({signature}) -> {return_anno}:",
        f"        {body}",
    ]


def _imperative_uses_omitted(ops: list[IROperation]) -> bool:
    return any(
        not spec.required and (not spec.has_default or spec.is_factory)
        for op in ops
        for spec in operation_fields(op)
    )


def _auth_middleware_class(cred: AuthCredential, *, is_async: bool) -> str:
    base = "Header" if cred.transport == "header" else "Query"
    suffix = "Async" if is_async else "Sync"
    return f"{base}Auth{suffix}Middleware"


def _init_lines(doc: IRDocument, creds: list[AuthCredential], *, is_async: bool) -> list[str]:
    """The shared ``def __init__`` (params, middleware assembly, super().__init__)."""
    default = "DEFAULT_BASE_URL" if doc.base_url else '""'
    mapper = "AsyncErrorMapperMiddleware" if is_async else "SyncErrorMapperMiddleware"
    params = [
        f"base_url: str = {default}",
        "*",
        "session: Any = None",
        "middleware: list[Any] | None = None",
    ]
    params.extend(f"{c.param_name}: {c.py_type} = None" for c in creds)
    lines = [f"    def __init__(self, {', '.join(params)}) -> None:"]
    lines.append("        _mw: list[Any] = list(middleware or [])")
    for cred in creds:
        mw_cls = _auth_middleware_class(cred, is_async=is_async)
        lines.append(f"        if {cred.param_name} is not None:")
        lines.append(f"            _mw.append({mw_cls}({cred.target!r}, {cred.value_expr}))")
    deep_keys = deep_object_query_keys(doc)
    if deep_keys:
        mw_cls = "DeepObjectQueryAsyncMiddleware" if is_async else "DeepObjectQuerySyncMiddleware"
        keys_expr = "frozenset({" + ", ".join(repr(k) for k in deep_keys) + "})"
        lines.append(f"        _mw.append({mw_cls}({keys_expr}))")
    lines.append(f"        _mw.insert(0, {mapper}(ERROR_MAP))")
    lines.append("        super().__init__(")
    lines.append("            base_url=base_url,")
    lines.append("            request_dumper=request_dumper,")
    lines.append("            response_loader=response_loader,")
    lines.append("            middleware=_mw,")
    lines.append("            session=session,")
    lines.append("        )")
    return lines


def _subclient(doc: IRDocument, tag: str, style: MethodStyle, *, is_async: bool) -> str:
    prefix = "Async" if is_async else ""
    name = f"{prefix}{class_name(tag)}Client"
    lines = [f"class {name}:"]
    lines.append("    def __init__(self, root: Any) -> None:")
    lines.append("        self._root = root")
    if is_async:
        lines.append(
            "    async def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType:"
        )
        lines.append("        return cast(ResponseType, await self._root.call_method(method))")
    else:
        lines.append("    def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType:")
        lines.append("        return cast(ResponseType, self._root.call_method(method))")
    if style is MethodStyle.IMPERATIVE:
        for op in doc.operations_for_tag(tag):
            lines.extend(_imperative_method_lines(op, op.method_name, is_async=is_async))
    else:
        for op in doc.operations_for_tag(tag):
            lines.append(f"    {op.method_name} = bind_method({op.class_name})")
    return "\n".join(lines)


def _grouped_root_client(
    doc: IRDocument, backend_cls: str, creds: list[AuthCredential], *, is_async: bool
) -> str:
    name = async_client_name(doc.title) if is_async else sync_client_name(doc.title)
    lines = [f"class {name}({backend_cls}):", *_init_lines(doc, creds, is_async=is_async)]
    prefix = "Async" if is_async else ""
    for tag in doc.tags:
        lines.append(f"        self.{field_name(tag)} = {prefix}{class_name(tag)}Client(self)")
    return "\n".join(lines)


def _flat_root_client(
    doc: IRDocument,
    backend_cls: str,
    creds: list[AuthCredential],
    method_lines: list[str],
    *,
    is_async: bool,
) -> str:
    name = async_client_name(doc.title) if is_async else sync_client_name(doc.title)
    lines = [f"class {name}({backend_cls}):", *_init_lines(doc, creds, is_async=is_async)]
    lines.extend(method_lines)
    return "\n".join(lines)


def _flat_method_lines(doc: IRDocument, style: MethodStyle, *, is_async: bool) -> list[str]:
    """Per-operation client members for a flat client (names globally de-duplicated)."""
    registry = NameRegistry()
    lines: list[str] = []
    for op in doc.operations:
        attr = registry.reserve(op.method_name)
        if style is MethodStyle.IMPERATIVE:
            lines.extend(_imperative_method_lines(op, attr, is_async=is_async))
        else:
            lines.append(f"    {attr} = bind_method({op.class_name})")
    return lines


def render_client_module(doc: IRDocument, config: GeneratorConfig, package: str) -> str:
    layout = config.resolve_layout(len(doc.tags))
    grouped = layout is Layout.GROUPED
    imperative = config.style is MethodStyle.IMPERATIVE
    creds = iter_auth_credentials(doc)

    imports: set[Import] = {
        Import("typing", "Any"),
        Import(f"{package}._serialization", "request_dumper"),
        Import(f"{package}._serialization", "response_loader"),
        Import(f"{package}.exceptions", "ERROR_MAP"),
    }
    if not imperative:
        imports.add(Import("unihttp.bind_method", "bind_method"))
    if grouped:
        imports.add(Import("unihttp.method", "BaseMethod"))
        imports.add(Import("unihttp.method", "ResponseType"))
        imports.add(Import("typing", "cast"))
    for tag in doc.tags:
        module = f"{package}.methods.{tag_module_name(tag)}"
        for op in doc.operations_for_tag(tag):
            imports.add(Import(module, op.class_name))

    if imperative:
        # Imperative signatures inline the param/body/return annotations, so the
        # client module needs the types they reference (UUID, datetime, Literal,
        # UploadFile, generated models) plus Omittable/Omitted for optionals.
        model_refs: set[str] = set()
        for op in doc.operations:
            imports |= op.imports()
            model_refs |= op.referenced_models()
        imports |= {Import(f"{package}.models", name) for name in model_refs}
        if _imperative_uses_omitted(doc.operations):
            imports.add(Import("unihttp.omitted", "Omittable"))
            imports.add(Import("unihttp.omitted", "Omitted"))

    parts: list[str] = []
    if doc.servers:
        server_map = {
            (server.description or f"server{index}"): server.url
            for index, server in enumerate(doc.servers)
        }
        entries = ", ".join(f"{k!r}: {v!r}" for k, v in server_map.items())
        parts.append(f"SERVERS: dict[str, str] = {{{entries}}}")
    if doc.base_url:
        parts.append(f"DEFAULT_BASE_URL = {doc.base_url!r}")

    auth_classes: set[str] = set()

    def emit_side(backend_cls: str, *, is_async: bool) -> None:
        auth_classes.update(_auth_middleware_class(c, is_async=is_async) for c in creds)
        if grouped:
            for tag in doc.tags:
                parts.append(_subclient(doc, tag, config.style, is_async=is_async))
            parts.append(_grouped_root_client(doc, backend_cls, creds, is_async=is_async))
        else:
            flat_methods = _flat_method_lines(doc, config.style, is_async=is_async)
            parts.append(
                _flat_root_client(doc, backend_cls, creds, flat_methods, is_async=is_async)
            )

    deep_keys = deep_object_query_keys(doc)
    if config.emit_sync:
        backend_cls, backend_mod = _SYNC_BACKENDS[config.sync_backend]
        imports.add(Import(backend_mod, backend_cls))
        imports.add(Import("unihttp.middlewares.error_mapper", "SyncErrorMapperMiddleware"))
        if deep_keys:
            imports.add(Import(f"{package}._query", "DeepObjectQuerySyncMiddleware"))
        emit_side(backend_cls, is_async=False)
    if config.emit_async:
        backend_cls, backend_mod = _ASYNC_BACKENDS[config.async_backend]
        imports.add(Import(backend_mod, backend_cls))
        imports.add(Import("unihttp.middlewares.error_mapper", "AsyncErrorMapperMiddleware"))
        if deep_keys:
            imports.add(Import(f"{package}._query", "DeepObjectQueryAsyncMiddleware"))
        emit_side(backend_cls, is_async=True)

    imports |= {Import(f"{package}.auth", cls) for cls in auth_classes}

    import_block = render_import_lines(imports)
    if needs_base64(creds):
        import_block = "import base64\n" + import_block

    return render_template(
        "module.py.jinja",
        header_comment='"""Generated API client. Do not edit by hand."""',
        future=True,
        imports=import_block,
        body="\n\n\n".join(parts) if parts else "# no clients",
    )
