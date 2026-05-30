#!/usr/bin/env bash
# Regenerate the Open-Meteo client library from the vendored spec.
#
# All generation settings live in unihttp-openapi-generator.toml (auto-discovered
# when the generator runs from this directory), so this script just invokes the
# generator and the quality gate.
#
# Requires `unihttp-openapi-generator`, `ruff`, and `mypy` on PATH
# (e.g. the project's dev virtualenv: `source .venv/bin/activate`).
set -euo pipefail
cd "$(dirname "$0")"

unihttp-openapi-generator generate

# Quality gate. Run ruff + mypy from *inside* the library directory so that
# `open_meteo_client` resolves as the top-level package.
cd open_meteo_library
ruff check --isolated open_meteo_client
mypy --strict --disable-error-code no-untyped-call --explicit-package-bases open_meteo_client
echo "regen OK"
