#!/usr/bin/env bash
# Regenerate the Frankfurter client library from the vendored spec.
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
# `frankfurter_client` resolves as the top-level package.
cd frankfurter_library
ruff check --isolated frankfurter_client
mypy --strict --disable-error-code no-untyped-call --explicit-package-bases frankfurter_client
echo "regen OK"
