"""Top-level orchestration: spec source -> generated package on disk."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from unihttp_openapi_generator.config import GeneratorConfig, OptionalStyle
from unihttp_openapi_generator.emit import write_package
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.loader import load_spec
from unihttp_openapi_generator.refs import RefResolver

logger = logging.getLogger("unihttp_openapi_generator")


class CheckError(Exception):
    """Raised when ``--check`` finds problems in the generated package."""


def _run_check(tool: str, args: list[str], package_dir: Path) -> None:
    found = shutil.which(tool)
    if found is None:
        raise CheckError(f"{tool} executable not found on PATH (required by --check)")
    result = subprocess.run([found, *args, str(package_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise CheckError(f"{tool} check failed for {package_dir}:\n{result.stdout}{result.stderr}")
    logger.info("%s check passed for %s", tool, package_dir)


def _check_package(package_dir: Path) -> None:
    # Generated packages ship without a ``[tool.ruff]`` table and are meant to lint
    # under ruff's defaults; ``--isolated`` ignores any ambient config that ruff
    # would otherwise discover from the cwd/parent dirs.
    _run_check("ruff", ["check", "--isolated"], package_dir)
    _run_check(
        "mypy",
        [
            "--strict",
            "--disable-error-code",
            "no-untyped-call",
            "--explicit-package-bases",
        ],
        package_dir,
    )


def run_generation(spec_source: str, config: GeneratorConfig) -> Path:
    """Run the full generation pipeline for ``spec_source`` into ``config.output_dir``."""
    spec = load_spec(spec_source, strict=False)
    resolver = RefResolver(spec, root_uri=spec_source)
    doc = build_ir(
        spec,
        resolver,
        root_uri=spec_source,
        omit_optionals=config.optional is OptionalStyle.OMITTED,
        strip_prefix=config.strip_prefix,
    )
    root = write_package(doc, config)
    logger.info("generated %s client at %s", config.package_name, root)
    if config.check:
        _check_package(root / config.package_name)
    return root
