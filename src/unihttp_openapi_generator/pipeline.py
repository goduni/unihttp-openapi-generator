"""Top-level orchestration: spec source -> generated package on disk."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from unihttp_openapi_generator.config import GeneratorConfig, OptionalStyle
from unihttp_openapi_generator.emit import write_package
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.loader import load_spec
from unihttp_openapi_generator.postprocess import config_args
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.tooling import (
    mypy_command,
    ruff_executable,
    target_python_executable,
)

logger = logging.getLogger("unihttp_openapi_generator")


class CheckError(Exception):
    """Raised when ``--check`` finds problems in the generated package."""


def _run_check(tool: str, command: list[str], package_dir: Path) -> None:
    result = subprocess.run([*command, str(package_dir)], capture_output=True, text=True)
    if result.returncode != 0:
        raise CheckError(f"{tool} check failed for {package_dir}:\n{result.stdout}{result.stderr}")
    logger.info("%s check passed for %s", tool, package_dir)


def _mypy_args() -> list[str]:
    args = [
        "--strict",
        "--disable-error-code",
        "no-untyped-call",
        "--explicit-package-bases",
    ]
    # The generated code imports unihttp and the chosen serializer. Those resolve from
    # the environment mypy runs in, which is the generator's -- and when the generator
    # was installed standalone, that environment has neither. An activated virtualenv
    # is the better answer, so hand it to mypy explicitly.
    target = target_python_executable()
    if target is not None:
        args += ["--python-executable", target]
    return args


def _check_package(package_dir: Path, *, stubs: bool, config_path: Path | None = None) -> None:
    # Lint the package against the ``[tool.ruff]`` table written into it, never against
    # ruff's defaults: those are not a fixed target (0.16 folded the ``RUF`` rules into
    # them, failing this gate on output that was correct), and never against whatever
    # config the cwd happens to carry, which belongs to whoever ran the generator.
    _run_check("ruff", [ruff_executable(), "check", *config_args(config_path)], package_dir)
    _run_check("mypy", [*mypy_command(), *_mypy_args()], package_dir)
    if stubs:
        # ``client.pyi`` makes mypy skip ``client.py`` entirely, so the run above
        # checks what a consumer sees and nothing of the module that actually runs.
        # Exclude the stub and check the implementation too.
        _run_check(
            "mypy (implementation)",
            [*mypy_command(), *_mypy_args(), "--exclude", r"client\.pyi$"],
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
        inheritance=config.inheritance,
    )
    root = write_package(doc, config)
    logger.info("generated %s client at %s", config.package_name, root)
    if config.check:
        _check_package(
            root / config.package_name, stubs=config.stubs, config_path=root / "pyproject.toml"
        )
    return root
