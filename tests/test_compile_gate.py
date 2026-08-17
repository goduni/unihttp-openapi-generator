"""Compile-gate: generated packages are deterministic and pass ruff + mypy --strict."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from unihttp_openapi_generator.config import (
    ClientKind,
    FileLayout,
    GeneratorConfig,
    Layout,
    MethodStyle,
    Serializer,
)
from unihttp_openapi_generator.pipeline import run_generation

_MATRIX = [
    (Serializer.ADAPTIX, ClientKind.BOTH),
    (Serializer.PYDANTIC, ClientKind.SYNC),
    (Serializer.MSGSPEC, ClientKind.ASYNC),
]


@pytest.fixture
def spec_file(sample_spec: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(sample_spec))
    return path


@pytest.fixture
def hierarchy_spec_file(hierarchy_spec: dict[str, Any], tmp_path: Path) -> Path:
    path = tmp_path / "hierarchy.json"
    path.write_text(json.dumps(hierarchy_spec))
    return path


def _collect_sources(root: Path) -> dict[str, str]:
    paths = sorted([*root.rglob("*.py"), *root.rglob("*.pyi")])
    return {str(p.relative_to(root)): p.read_text() for p in paths}


def _assert_ruff_clean(package_dir: Path) -> None:
    """Lint the package against the config the generator wrote into it.

    Not against this repository's, which is what a bare ``ruff check`` from the test
    session would discover: that checked the output under rules the generated package
    never claimed, and passed while a user running ``--check`` on the very same output
    got failures.
    """
    ruff = shutil.which("ruff")
    assert ruff is not None
    config = package_dir.parent / "pyproject.toml"
    assert config.is_file()
    result = subprocess.run(
        [ruff, "check", "--config", str(config), str(package_dir)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_mypy_strict_clean(package_dir: Path) -> None:
    # Run mypy via the current interpreter so it resolves imports (e.g. msgspec)
    # from this environment, not whatever bare ``mypy`` happens to be on PATH.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--disable-error-code",
            "no-untyped-call",
            "--explicit-package-bases",
            str(package_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(("serializer", "client"), _MATRIX)
def test_generated_package_passes_ruff_and_mypy(
    spec_file: Path, tmp_path: Path, serializer: Serializer, client: ClientKind
) -> None:
    package = f"gate_{serializer.value}"
    out = tmp_path / package
    run_generation(
        str(spec_file),
        GeneratorConfig(package_name=package, output_dir=out, serializer=serializer, client=client),
    )
    _assert_ruff_clean(out / package)
    _assert_mypy_strict_clean(out / package)


@pytest.mark.parametrize("layout", list(FileLayout))
@pytest.mark.parametrize(("serializer", "client"), _MATRIX)
def test_inheritance_package_passes_ruff_and_mypy(
    hierarchy_spec_file: Path,
    tmp_path: Path,
    serializer: Serializer,
    client: ClientKind,
    layout: FileLayout,
) -> None:
    """``--inheritance`` emits a package that still survives ``--check``.

    A subclass declaration is where a wrong IR turns into an ``[assignment]`` error
    rather than a slightly-off annotation, and the unit tests reason about the IR, not
    about what mypy makes of the rendered classes. Both layouts run because the base
    class is the one reference that has to be imported at *runtime* in the per-object
    layout, not deferred into the ``TYPE_CHECKING`` block.
    """
    package = f"inh_{serializer.value}_{layout.name.lower()}"
    out = tmp_path / package
    run_generation(
        str(hierarchy_spec_file),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=serializer,
            client=client,
            file_layout=layout,
            inheritance=True,
        ),
    )
    _assert_ruff_clean(out / package)
    _assert_mypy_strict_clean(out / package)


@pytest.mark.parametrize(("serializer", "client"), _MATRIX)
def test_stubbed_package_passes_ruff_and_both_mypy_passes(
    spec_file: Path, tmp_path: Path, serializer: Serializer, client: ClientKind
) -> None:
    """``--stubs --check`` runs the real gate, including the implementation pass.

    ``check=True`` is the point of the test rather than a shortcut: a stub takes
    ``client.py`` out of mypy's sight, so only the pipeline's second pass proves the
    runtime module is still clean, and only the first proves the stub itself is.
    """
    package = f"stub_{serializer.value}"
    out = tmp_path / package
    run_generation(
        str(spec_file),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            serializer=serializer,
            client=client,
            stubs=True,
            check=True,
        ),
    )
    assert (out / package / "client.pyi").is_file()


@pytest.mark.parametrize("layout", list(Layout))
@pytest.mark.parametrize("file_layout", list(FileLayout))
def test_stubs_survive_every_layout(
    spec_file: Path, tmp_path: Path, layout: Layout, file_layout: FileLayout
) -> None:
    # Grouped layout adds sub-client classes to the stub, and the per-object file
    # layout moves the models the signatures reference behind a re-exporting package.
    package = f"stublay_{layout.name.lower()}_{file_layout.name.lower()}"
    out = tmp_path / package
    run_generation(
        str(spec_file),
        GeneratorConfig(
            package_name=package,
            output_dir=out,
            layout=layout,
            file_layout=file_layout,
            stubs=True,
            check=True,
        ),
    )
    assert (out / package / "client.pyi").is_file()


@pytest.mark.parametrize("stubs", [False, True])
def test_generation_is_deterministic(spec_file: Path, tmp_path: Path, stubs: bool) -> None:
    config_a = GeneratorConfig(package_name="det_client", output_dir=tmp_path / "a", stubs=stubs)
    config_b = GeneratorConfig(package_name="det_client", output_dir=tmp_path / "b", stubs=stubs)
    run_generation(str(spec_file), config_a)
    run_generation(str(spec_file), config_b)
    sources_a = _collect_sources(tmp_path / "a" / "det_client")
    sources_b = _collect_sources(tmp_path / "b" / "det_client")
    assert sources_a == sources_b


def test_check_passes_when_generating_beneath_the_working_directory(
    spec_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--check`` must survive the ordinary invocation: ``--output-dir ./out``.

    Under ``--explicit-package-bases`` mypy derives module names relative to the working
    directory whenever the files sit beneath it, so a package generated into ``out/``
    from the project root came out as ``out.acme_client`` -- and every intra-package
    import, which spells the package's real name, was unresolvable. The result was
    ``--check`` reporting a correct package as broken, in what is the most obvious way
    to run the generator.

    The other gates here escape it only because pytest's ``tmp_path`` is nowhere near
    the working directory.
    """
    monkeypatch.chdir(tmp_path)

    run_generation(
        str(spec_file),
        GeneratorConfig(package_name="cwd_client", output_dir=Path("out"), check=True),
    )


def test_generation_ignores_an_ambient_ruff_config(
    spec_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same spec must produce the same bytes wherever the generator is run from.

    The formatting pass used to let ruff discover config the way ruff normally does --
    from the working directory and its parents -- so a package generated inside a
    project with its own ``line-length`` came out wrapped differently from the same
    package generated anywhere else. ``test_generation_is_deterministic`` could not see
    it: both of its runs share one working directory.

    Each run below puts the output *under* a directory carrying a hostile config, so
    both cwd-based and parent-based discovery are in play.
    """
    outputs = []
    for width in (50, 200):
        home = tmp_path / f"w{width}"
        home.mkdir()
        (home / "pyproject.toml").write_text(f"[tool.ruff]\nline-length = {width}\n")
        monkeypatch.chdir(home)
        run_generation(
            str(spec_file),
            GeneratorConfig(package_name="amb_client", output_dir=home / "out"),
        )
        outputs.append(_collect_sources(home / "out" / "amb_client"))

    assert outputs[0] == outputs[1]
    # and the bytes are the package's own: 88 columns, not 50 and not 200
    longest = max(len(line) for src in outputs[0].values() for line in src.splitlines())
    assert longest <= 88


def test_a_parameter_named_self_still_generates(tmp_path: Path) -> None:
    """``self`` as a parameter name must not break the spelled-out signatures.

    The request dataclass takes it as a field -- ``dataclasses`` moves its own
    receiver aside so ``GetA(self=...)`` works -- so a client method has to move
    its receiver too. Both styles that spell signatures out are checked.
    """
    spec = tmp_path / "self.json"
    spec.write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "info": {"title": "Shadow", "version": "1.0.0"},
                "paths": {
                    "/a": {
                        "get": {
                            "operationId": "getA",
                            "tags": ["t"],
                            "parameters": [
                                {
                                    "name": "self",
                                    "in": "query",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            ],
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        )
    )
    for name, extra in (
        ("shadow_stub", {"stubs": True}),
        ("shadow_imp", {"style": MethodStyle.IMPERATIVE}),
    ):
        out = tmp_path / name
        run_generation(
            str(spec),
            GeneratorConfig(package_name=name, output_dir=out, check=True, **extra),
        )
        assert (out / name / "client.py").is_file()
