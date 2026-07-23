"""Resolve generation settings from a TOML config file merged with CLI overrides.

Precedence: explicit CLI value > config file value > built-in default.

A config file may be:
- passed explicitly via ``--config FILE`` (keys at the top level, or under a
  ``[tool.unihttp-openapi-generator]`` table), or
- auto-discovered in the current directory: ``unihttp-openapi-generator.toml``
  (top-level or namespaced), then ``pyproject.toml`` (``[tool.unihttp-openapi-generator]``).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

_TOOL_TABLE = "unihttp-openapi-generator"
_AUTO_FILENAME = "unihttp-openapi-generator.toml"

#: Settings accepted in a config file (mirrors the CLI options).
ALLOWED_KEYS = frozenset(
    {
        "spec",
        "output_dir",
        "package_name",
        "serializer",
        "client",
        "sync_backend",
        "async_backend",
        "style",
        "layout",
        "optional",
        "file_layout",
        "strip_prefix",
        "inheritance",
        "check",
    }
)
_REQUIRED_KEYS = ("spec", "output_dir", "package_name")


class ConfigFileError(Exception):
    """Raised for missing/invalid config files or settings."""


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigFileError(f"failed to read config {path}: {exc}") from exc


def _namespaced(data: dict[str, Any]) -> dict[str, Any] | None:
    tool = data.get("tool")
    if isinstance(tool, dict) and isinstance(tool.get(_TOOL_TABLE), dict):
        return dict(tool[_TOOL_TABLE])
    return None


def load_file_settings(config_path: Path | None, cwd: Path) -> dict[str, Any]:
    """Return the raw settings table from the chosen/discovered config file (or {})."""
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigFileError(f"config file not found: {config_path}")
        data = _read_toml(config_path)
        namespaced = _namespaced(data)
        # A dedicated file may namespace under [tool.*] or put keys at the top level.
        return (
            namespaced if namespaced is not None else {k: v for k, v in data.items() if k != "tool"}
        )

    auto = cwd / _AUTO_FILENAME
    if auto.is_file():
        data = _read_toml(auto)
        namespaced = _namespaced(data)
        return (
            namespaced if namespaced is not None else {k: v for k, v in data.items() if k != "tool"}
        )

    pyproject = cwd / "pyproject.toml"
    if pyproject.is_file():
        return _namespaced(_read_toml(pyproject)) or {}

    return {}


def merge_settings(cli: dict[str, Any], config_path: Path | None, cwd: Path) -> dict[str, Any]:
    """Merge file settings with CLI overrides (CLI wins when not ``None``)."""
    file_settings = load_file_settings(config_path, cwd)
    unknown = set(file_settings) - ALLOWED_KEYS
    if unknown:
        raise ConfigFileError(
            f"unknown config key(s): {', '.join(sorted(unknown))}; "
            f"allowed: {', '.join(sorted(ALLOWED_KEYS))}"
        )
    merged: dict[str, Any] = dict(file_settings)
    for key, value in cli.items():
        if value is not None:
            merged[key] = value

    missing = [k for k in _REQUIRED_KEYS if not merged.get(k)]
    if missing:
        raise ConfigFileError(
            f"missing required setting(s): {', '.join(missing)} (provide via CLI or config file)"
        )
    return merged
