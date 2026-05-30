"""Write a generated client package to disk."""

from __future__ import annotations

from pathlib import Path

from unihttp_openapi_generator.config import (
    AsyncBackend,
    FileLayout,
    GeneratorConfig,
    Serializer,
    SyncBackend,
)
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.postprocess import format_path, format_python
from unihttp_openapi_generator.render.auth import iter_auth_credentials, render_auth_module
from unihttp_openapi_generator.render.clients import (
    async_client_name,
    render_client_module,
    sync_client_name,
)
from unihttp_openapi_generator.render.exceptions import render_exceptions_module
from unihttp_openapi_generator.render.file_layout import (
    build_layout_plan,
    render_declaration_module,
    render_forward_refs_module,
    render_method_module,
    render_methods_init,
    render_models_init,
    render_tag_init,
)
from unihttp_openapi_generator.render.methods import render_methods_module, tag_module_name
from unihttp_openapi_generator.render.models import render_models_module
from unihttp_openapi_generator.render.query import deep_object_query_keys, render_query_module
from unihttp_openapi_generator.render.serializers import get_strategy
from unihttp_openapi_generator.render.serializers.base import SerializerStrategy

_BACKEND_DISTRIBUTION = {
    SyncBackend.HTTPX: "httpx>=0.28.1",
    SyncBackend.REQUESTS: "requests>=2.32.0",
    SyncBackend.NIQUESTS: "niquests>=3.17.0",
    SyncBackend.ZAPROS: "zapros>=0.11.0",
    AsyncBackend.AIOHTTP: "aiohttp>=3.10.0",
}
_SERIALIZER_DISTRIBUTION = {
    Serializer.ADAPTIX: "adaptix>=3.0.0b12",
    Serializer.PYDANTIC: "pydantic>=2.0.0",
    Serializer.MSGSPEC: "msgspec>=0.18.0",
}


def _write_py(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_python(source, filename=path.name))


def _render_methods_init(doc: IRDocument, package: str) -> str:
    lines = ['"""Generated request methods."""', "", "from __future__ import annotations", ""]
    all_names: list[str] = []
    for tag in doc.tags:
        names = [op.class_name for op in doc.operations_for_tag(tag)]
        all_names.extend(names)
        joined = ", ".join(names)
        lines.append(f"from {package}.methods.{tag_module_name(tag)} import {joined}")
    lines.append("")
    lines.append(f"__all__ = {sorted(all_names)!r}")
    return "\n".join(lines) + "\n"


def _render_package_init(doc: IRDocument, config: GeneratorConfig, package: str) -> str:
    exports: list[str] = []
    lines = [f'"""{doc.title} client (generated)."""', "", "from __future__ import annotations", ""]
    if config.emit_sync:
        name = sync_client_name(doc.title)
        exports.append(name)
        lines.append(f"from {package}.client import {name}")
    if config.emit_async:
        name = async_client_name(doc.title)
        exports.append(name)
        lines.append(f"from {package}.client import {name}")
    if doc.servers:
        client_exports = ["SERVERS"]
        if doc.base_url:
            client_exports.append("DEFAULT_BASE_URL")
        exports.extend(client_exports)
        lines.append(f"from {package}.client import {', '.join(client_exports)}")
    lines.append("")
    lines.append(f"__all__ = {sorted(exports)!r}")
    return "\n".join(lines) + "\n"


def _render_pyproject(doc: IRDocument, config: GeneratorConfig) -> str:
    # Open lower bound: newer unihttp releases resolve/install automatically.
    # 0.2.9 is the floor because that's where the msgspec serializer landed.
    deps = ["unihttp>=0.2.9", _SERIALIZER_DISTRIBUTION[config.serializer]]
    backends: set[SyncBackend | AsyncBackend] = set()
    if config.emit_sync:
        backends.add(config.sync_backend)
    if config.emit_async:
        backends.add(config.async_backend)
    for backend in backends:
        dist = _BACKEND_DISTRIBUTION.get(backend)
        if dist:
            deps.append(dist)
    dep_lines = ",\n    ".join(f'"{d}"' for d in sorted(set(deps)))
    return (
        "[project]\n"
        f'name = "{config.package_name.replace("_", "-")}"\n'
        'version = "0.0.0"\n'
        f'description = "Generated unihttp client for {doc.title}"\n'
        'requires-python = ">=3.12"\n'
        f"dependencies = [\n    {dep_lines},\n]\n\n"
        "[build-system]\n"
        'requires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        "[tool.hatch.build.targets.wheel]\n"
        f'packages = ["{config.package_name}"]\n'
    )


def _render_readme(doc: IRDocument, config: GeneratorConfig) -> str:
    client = sync_client_name(doc.title) if config.emit_sync else async_client_name(doc.title)
    return (
        f"# {config.package_name}\n\n"
        f"Generated [unihttp](https://github.com/goduni/unihttp) client for "
        f"**{doc.title}** ({doc.version}).\n\n"
        "```python\n"
        f"from {config.package_name} import {client}\n\n"
        f"client = {client}()\n"
        "```\n\n"
        f"Serializer: `{config.serializer.value}`. "
        "Regenerate with `unihttp-openapi-generator`; do not edit by hand.\n"
    )


def _write_single_layout(
    doc: IRDocument, strategy: SerializerStrategy, package: str, package_dir: Path
) -> None:
    """Current behavior: one ``models.py`` and one ``methods/<tag>.py`` per tag."""
    _write_py(package_dir / "models.py", render_models_module(doc, strategy))
    _write_py(package_dir / "_serialization.py", strategy.serialization_module(doc, package))
    _write_py(package_dir / "methods" / "__init__.py", _render_methods_init(doc, package))
    for tag in doc.tags:
        _write_py(
            package_dir / "methods" / f"{tag_module_name(tag)}.py",
            render_methods_module(doc, tag, package),
        )


def _write_per_object_layout(
    doc: IRDocument, strategy: SerializerStrategy, package: str, package_dir: Path
) -> None:
    """Emit one module per declaration and per request method, plus re-exports."""
    strategy.bind_document(doc)
    plan = build_layout_plan(doc)

    for decl in doc.declarations:
        stem = plan.model_modules[decl.name]
        _write_py(
            package_dir / "models" / f"{stem}.py",
            render_declaration_module(decl, strategy, package, plan),
        )
    _write_py(package_dir / "models" / "__init__.py", render_models_init(doc, package, plan))

    for tag in doc.tags:
        tag_mod = tag_module_name(tag)
        for op in doc.operations_for_tag(tag):
            stem = plan.method_modules[op.class_name][1]
            _write_py(
                package_dir / "methods" / tag_mod / f"{stem}.py",
                render_method_module(op, package, plan),
            )
        _write_py(
            package_dir / "methods" / tag_mod / "__init__.py",
            render_tag_init(doc, tag, package, plan),
        )
    _write_py(package_dir / "methods" / "__init__.py", render_methods_init(doc, package))

    _write_py(
        package_dir / "_forward_refs.py",
        render_forward_refs_module(doc, strategy, package, plan),
    )
    _write_py(
        package_dir / "_serialization.py",
        strategy.serialization_module(doc, package, resolve=True),
    )


def write_package(doc: IRDocument, config: GeneratorConfig) -> Path:
    """Write the full client package; returns the project root directory."""
    strategy = get_strategy(config.serializer)
    package = config.package_name
    project_root = config.output_dir
    package_dir = project_root / package

    if config.file_layout is FileLayout.PER_OBJECT:
        _write_per_object_layout(doc, strategy, package, package_dir)
    else:
        _write_single_layout(doc, strategy, package, package_dir)
    _write_py(package_dir / "exceptions.py", render_exceptions_module(doc))
    if iter_auth_credentials(doc):
        _write_py(package_dir / "auth.py", render_auth_module())
    if deep_object_query_keys(doc):
        _write_py(package_dir / "_query.py", render_query_module())
    _write_py(package_dir / "client.py", render_client_module(doc, config, package))
    _write_py(package_dir / "__init__.py", _render_package_init(doc, config, package))
    (package_dir / "py.typed").write_text("")

    (project_root / "pyproject.toml").write_text(_render_pyproject(doc, config))
    (project_root / "README.md").write_text(_render_readme(doc, config))

    # Final project-aware pass: groups first-party imports consistently on disk.
    format_path(package_dir)
    return project_root
