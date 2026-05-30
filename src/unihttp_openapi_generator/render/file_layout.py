"""Per-object file layout: one declaration/method per module.

In ``per-object`` mode each model/enum/alias becomes ``models/<snake>.py`` and each
request method becomes ``methods/<tag>/<snake>.py``. Cross-module references are
emitted under ``if TYPE_CHECKING:`` (with ``from __future__ import annotations`` the
names are never imported at runtime, so cycles A<->B cannot deadlock the import
graph); the referenced classes are injected into each module's globals at runtime by
``_forward_refs.resolve_forward_refs`` before any loader/retort is built.
"""

from __future__ import annotations

from dataclasses import dataclass

from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import Declaration, IRModel
from unihttp_openapi_generator.ir.naming import NameRegistry, to_snake_case
from unihttp_openapi_generator.ir.operations import IROperation
from unihttp_openapi_generator.ir.types import Import
from unihttp_openapi_generator.render.engine import render_template
from unihttp_openapi_generator.render.imports import render_import_lines
from unihttp_openapi_generator.render.methods import render_method_class, tag_module_name
from unihttp_openapi_generator.render.serializers.base import SerializerStrategy


def _module_stem(name: str) -> str:
    """Snake-case module stem for a class name (sanitized so it is import-safe)."""
    snake = to_snake_case(name) or name.lower()
    if not snake.isidentifier():
        snake = f"_{snake}"
    return snake


@dataclass(frozen=True)
class LayoutPlan:
    """Resolved per-object module locations for one document.

    ``model_modules`` maps a declaration name to its ``models/<stem>`` module stem;
    ``method_modules`` maps an operation class name to its ``methods/<tag>/<stem>``
    (tag, stem) pair.
    """

    model_modules: dict[str, str]
    method_modules: dict[str, tuple[str, str]]

    def model_dotted(self, package: str, name: str) -> str:
        return f"{package}.models.{self.model_modules[name]}"

    def method_dotted(self, package: str, class_name: str) -> str:
        tag, stem = self.method_modules[class_name]
        return f"{package}.methods.{tag}.{stem}"


def build_layout_plan(doc: IRDocument) -> LayoutPlan:
    """Assign a unique, collision-free module stem to every declaration and method."""
    model_modules: dict[str, str] = {}
    model_registry = NameRegistry()
    for decl in doc.declarations:
        model_modules[decl.name] = model_registry.reserve(_module_stem(decl.name))

    method_modules: dict[str, tuple[str, str]] = {}
    for tag in doc.tags:
        method_registry = NameRegistry()
        for op in doc.operations_for_tag(tag):
            stem = method_registry.reserve(_module_stem(op.class_name))
            method_modules[op.class_name] = (tag_module_name(tag), stem)
    return LayoutPlan(model_modules, method_modules)


def _type_checking_block(package: str, plan: LayoutPlan, refs: set[str]) -> list[str]:
    """An ``if TYPE_CHECKING:`` block importing ``refs`` from their own model modules."""
    refs = {r for r in refs if r in plan.model_modules}
    if not refs:
        return []
    lines = ["if TYPE_CHECKING:"]
    for name in sorted(refs):
        lines.append(f"    from {plan.model_dotted(package, name)} import {name}")
    return lines


def render_declaration_module(
    decl: Declaration, strategy: SerializerStrategy, package: str, plan: LayoutPlan
) -> str:
    """Render a single ``models/<stem>.py`` module for one declaration."""
    imports = set(strategy.declaration_imports(decl))
    refs = decl.referenced_models()
    # Strip cross-model refs from the runtime imports: they live in the
    # TYPE_CHECKING block (and ``from __future__ import annotations`` keeps the
    # annotations lazy). Stdlib/typing/serializer imports stay at runtime.
    imports = {imp for imp in imports if imp.name not in plan.model_modules}
    body = strategy.render_declaration(decl)
    tc_lines = _type_checking_block(package, plan, refs)
    if tc_lines:
        imports.add(Import("typing", "TYPE_CHECKING"))
    import_block = render_import_lines(imports)
    if tc_lines:
        import_block = (
            f"{import_block}\n\n{chr(10).join(tc_lines)}" if import_block else ("\n".join(tc_lines))
        )
    return render_template(
        "module.py.jinja",
        header_comment=f'"""Generated declaration ``{decl.name}``. Do not edit by hand."""',
        future=True,
        imports=import_block,
        body=body,
    )


def render_method_module(op: IROperation, package: str, plan: LayoutPlan) -> str:
    """Render a single ``methods/<tag>/<stem>.py`` module for one operation.

    The operation's return type appears in the ``BaseMethod[...]`` base class, which
    ``from __future__ import annotations`` does NOT defer (base-class subscripts are
    evaluated at class-definition time). So return-type model refs are imported at
    runtime (safe: models never import methods, so no cycle). Every other model ref
    appears only inside annotations and stays under ``TYPE_CHECKING``.
    """
    code, imports = render_method_class(op)
    imports = {imp for imp in imports if imp.name not in plan.model_modules}

    runtime_refs: set[str] = set()
    if op.return_type is not None:
        runtime_refs = {r for r in op.return_type.referenced_models() if r in plan.model_modules}
    for name in sorted(runtime_refs):
        imports.add(Import(plan.model_dotted(package, name), name))

    deferred_refs = op.referenced_models() - runtime_refs
    tc_lines = _type_checking_block(package, plan, deferred_refs)
    if tc_lines:
        imports.add(Import("typing", "TYPE_CHECKING"))
    import_block = render_import_lines(imports)
    if tc_lines:
        import_block = (
            f"{import_block}\n\n{chr(10).join(tc_lines)}" if import_block else "\n".join(tc_lines)
        )
    return render_template(
        "module.py.jinja",
        header_comment=f'"""Generated request method ``{op.class_name}``. Do not edit by hand."""',
        future=True,
        imports=import_block,
        body=code,
    )


def render_models_init(doc: IRDocument, package: str, plan: LayoutPlan) -> str:
    """``models/__init__.py`` re-exporting every declaration."""
    lines = [
        '"""Generated data models. Do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    names: list[str] = []
    for decl in doc.declarations:
        names.append(decl.name)
        lines.append(f"from {plan.model_dotted(package, decl.name)} import {decl.name}")
    lines.append("")
    lines.append(f"__all__ = {sorted(names)!r}")
    return "\n".join(lines) + "\n"


def render_tag_init(doc: IRDocument, tag: str, package: str, plan: LayoutPlan) -> str:
    """``methods/<tag>/__init__.py`` re-exporting that tag's methods."""
    lines = [
        f'"""Generated request methods for tag {tag!r}. Do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    names: list[str] = []
    for op in doc.operations_for_tag(tag):
        names.append(op.class_name)
        lines.append(f"from {plan.method_dotted(package, op.class_name)} import {op.class_name}")
    lines.append("")
    lines.append(f"__all__ = {sorted(names)!r}")
    return "\n".join(lines) + "\n"


def render_methods_init(doc: IRDocument, package: str) -> str:
    """``methods/__init__.py`` re-exporting every tag's methods."""
    lines = ['"""Generated request methods."""', "", "from __future__ import annotations", ""]
    all_names: list[str] = []
    for tag in doc.tags:
        names = [op.class_name for op in doc.operations_for_tag(tag)]
        all_names.extend(names)
        lines.append(f"from {package}.methods.{tag_module_name(tag)} import {', '.join(names)}")
    lines.append("")
    lines.append(f"__all__ = {sorted(all_names)!r}")
    return "\n".join(lines) + "\n"


def render_forward_refs_module(
    doc: IRDocument, strategy: SerializerStrategy, package: str, plan: LayoutPlan
) -> str:
    """``_forward_refs.py``: inject sibling classes into module globals at runtime.

    Importing ``<pkg>.models`` materializes every declaration class. We build the full
    ``{name: class}`` namespace and splice it into the globals of each model and method
    module (each is imported here too), so the serializer can resolve the annotations it
    deferred under ``TYPE_CHECKING``. For pydantic we additionally call
    ``model_rebuild()`` on each model once the namespace is in place.
    """
    model_stems = sorted(set(plan.model_modules.values()))
    model_class_names = sorted(d.name for d in doc.declarations if isinstance(d, IRModel))

    lines = [
        '"""Resolve cross-module forward references for the per-object layout."""',
        "",
        "from __future__ import annotations",
        "",
        "import importlib",
        "",
        "",
        "def resolve_forward_refs() -> None:",
        '    """Inject referenced classes into every generated module\'s globals."""',
    ]
    # Import the models package to register every declaration class.
    lines.append(f"    from {package} import models as _models")
    lines.append("")
    lines.append("    namespace = {name: getattr(_models, name) for name in _models.__all__}")
    lines.append("")
    lines.append("    module_names = [")
    for stem in model_stems:
        lines.append(f"        {f'{package}.models.{stem}'!r},")
    for tag in doc.tags:
        tag_mod = tag_module_name(tag)
        for op in doc.operations_for_tag(tag):
            stem = plan.method_modules[op.class_name][1]
            lines.append(f"        {f'{package}.methods.{tag_mod}.{stem}'!r},")
    lines.append("    ]")
    lines.append("    for module_name in module_names:")
    lines.append("        module = importlib.import_module(module_name)")
    lines.append("        vars(module).update(namespace)")
    if strategy.needs_model_rebuild() and model_class_names:
        lines.append("")
        lines.append("    for name in (")
        for name in model_class_names:
            lines.append(f"        {name!r},")
        lines.append("    ):")
        lines.append("        namespace[name].model_rebuild()")
    if not model_stems and not doc.operations:
        # Nothing to resolve; keep a valid, lint-clean no-op body.
        lines = [
            '"""Resolve cross-module forward references for the per-object layout."""',
            "",
            "from __future__ import annotations",
            "",
            "",
            "def resolve_forward_refs() -> None:",
            '    """No generated declarations or methods need forward-ref resolution."""',
        ]
    return "\n".join(lines) + "\n"
