"""Assemble the generated ``models.py`` module."""

from __future__ import annotations

from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.types import Import
from unihttp_openapi_generator.render.engine import render_template
from unihttp_openapi_generator.render.imports import render_import_lines
from unihttp_openapi_generator.render.serializers.base import SerializerStrategy


def render_models_module(doc: IRDocument, strategy: SerializerStrategy) -> str:
    strategy.bind_document(doc)
    imports: set[Import] = set()
    body_parts: list[str] = []
    for decl in doc.declarations:
        imports |= strategy.declaration_imports(decl)
        body_parts.append(strategy.render_declaration(decl))
    if not body_parts:
        body_parts.append("# no component schemas")
    return render_template(
        "module.py.jinja",
        header_comment='"""Generated data models. Do not edit by hand."""',
        future=True,
        imports=render_import_lines(imports),
        body="\n\n\n".join(body_parts),
    )
