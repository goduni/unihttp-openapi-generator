"""Command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from unihttp_openapi_generator import __version__
from unihttp_openapi_generator.config import (
    AsyncBackend,
    ClientKind,
    FileLayout,
    GeneratorConfig,
    Layout,
    MethodStyle,
    OptionalStyle,
    Serializer,
    SyncBackend,
)

app = typer.Typer(
    name="unihttp-openapi-generator",
    help="Generate typed unihttp client libraries from OpenAPI 3.1 specifications.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def _main(
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """unihttp-openapi-generator."""


@app.command()
def generate(
    spec: Annotated[str | None, typer.Argument(help="Path or URL to an OpenAPI 3.1 spec.")] = None,
    output_dir: Annotated[Path | None, typer.Option("-o", "--output-dir")] = None,
    package_name: Annotated[str | None, typer.Option("--package-name")] = None,
    serializer: Annotated[Serializer | None, typer.Option("--serializer")] = None,
    client: Annotated[ClientKind | None, typer.Option("--client")] = None,
    sync_backend: Annotated[SyncBackend | None, typer.Option("--sync-backend")] = None,
    async_backend: Annotated[AsyncBackend | None, typer.Option("--async-backend")] = None,
    style: Annotated[MethodStyle | None, typer.Option("--style")] = None,
    layout: Annotated[Layout | None, typer.Option("--layout")] = None,
    optional: Annotated[OptionalStyle | None, typer.Option("--optional")] = None,
    file_layout: Annotated[FileLayout | None, typer.Option("--file-layout")] = None,
    strip_prefix: Annotated[
        str | None,
        typer.Option("--strip-prefix", help="'auto' or a dotted prefix to drop from schema names."),
    ] = None,
    inheritance: Annotated[
        bool | None,
        typer.Option(
            "--inheritance/--no-inheritance",
            help="Render 'allOf: [$ref]' as a base class instead of merging its fields in.",
        ),
    ] = None,
    check: Annotated[bool | None, typer.Option("--check/--no-check")] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="TOML config file (overridden by explicit flags)."),
    ] = None,
) -> None:
    """Generate a client package from an OpenAPI specification.

    Settings may come from a TOML config file (``--config``, or an auto-discovered
    ``unihttp-openapi-generator.toml`` / ``[tool.unihttp-openapi-generator]`` in
    ``pyproject.toml``); explicit command-line flags take precedence.
    """
    from unihttp_openapi_generator.config_file import ConfigFileError, merge_settings
    from unihttp_openapi_generator.pipeline import run_generation

    cli_overrides: dict[str, Any] = {
        "spec": spec,
        "output_dir": output_dir,
        "package_name": package_name,
        "serializer": serializer,
        "client": client,
        "sync_backend": sync_backend,
        "async_backend": async_backend,
        "style": style,
        "layout": layout,
        "optional": optional,
        "file_layout": file_layout,
        "strip_prefix": strip_prefix,
        "inheritance": inheritance,
        "check": check,
    }

    try:
        merged = merge_settings(cli_overrides, config, Path.cwd())
    except ConfigFileError as exc:
        raise typer.BadParameter(str(exc)) from exc

    spec_source = merged.pop("spec")
    try:
        gen_config = GeneratorConfig(**merged)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    run_generation(spec_source, gen_config)


if __name__ == "__main__":
    app()
