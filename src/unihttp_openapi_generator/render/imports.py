"""Turn a set of Import requirements into import statements (ruff sorts them later)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from unihttp_openapi_generator.ir.types import Import


def render_import_lines(imports: Iterable[Import]) -> str:
    by_module: dict[str, set[str]] = defaultdict(set)
    bare: set[str] = set()
    for imp in imports:
        if imp.name:
            by_module[imp.module].add(imp.name)
        else:
            # A bare ``import <module>`` requirement (empty ``name``).
            bare.add(imp.module)
    lines = [f"import {module}" for module in sorted(bare)]
    for module in sorted(by_module):
        names = ", ".join(sorted(by_module[module]))
        lines.append(f"from {module} import {names}")
    return "\n".join(lines)
