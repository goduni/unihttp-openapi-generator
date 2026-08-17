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


def _export_sort_key(name: str) -> tuple[int, str]:
    """isort's ordering for ``__all__``: constants, then classes, then everything else.

    Plain alphabetical order is what a generator reaches for, but it is not what the
    linters that check ``__all__`` expect, and the emitted package is linted with the
    config the generator writes into it.
    """
    if name.isupper():
        return (0, name)
    if name[:1].isupper():
        return (1, name)
    return (2, name)


def render_dunder_all(names: Iterable[str]) -> str:
    """An ``__all__`` assignment whose entries are already in the expected order."""
    return f"__all__ = {sorted(names, key=_export_sort_key)!r}"
