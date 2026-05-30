# Examples

Each subdirectory is a self-contained example: an OpenAPI spec, the **generated**
[unihttp](https://github.com/goduni/unihttp) client library, and **runners** —
runnable scripts that call the **live** API and assert the results.

The runners double as usage examples and as functional tests: every one prints a
human-readable walk-through *and* asserts invariants, so they prove the generated
clients actually work end to end (not just that they type-check).

## Structure

```
examples/
├── run_all.py                          # run every runner, report pass / skip / fail
└── <api>/
    ├── openapi.yaml                    # vendored spec (generation reads this)
    ├── unihttp-openapi-generator.toml  # generation settings (auto-discovered)
    ├── regen.sh                        # thin wrapper: generate + ruff/mypy gate
    ├── <api>_library/                  # the GENERATED client package (committed)
    └── <api>_runners/                  # hand-written demo + assertion scripts
```

Each example pins its generator settings in a committed
`unihttp-openapi-generator.toml` (spec, package name, serializer, backend,
layout, file layout). The generator auto-discovers it, so `regen.sh` is just
`unihttp-openapi-generator generate` plus a `ruff` + `mypy --strict` gate — and
the config file itself doubles as a showcase of that feature.

## Running

Runners use [`uv`](https://docs.astral.sh/uv/); each `*_runners/` is a tiny uv
project that pulls in its generated library via an editable path source.

```bash
# one example
cd frankfurter/frankfurter_runners && uv run python rates_demo.py

# everything
python examples/run_all.py
```

Runner exit codes: `0` pass · `2` skip (live API unreachable — not counted as a
failure) · anything else = fail (a real bug). `run_all.py` fails only on a real
failure, so a public API having a bad day never breaks the suite.

## Examples & feature coverage

Combos are chosen to fit each API and, across the set, to exercise the
generator's options (serializer / backend / sync·async / layout).

| Example | API | Serializer | Client | Layout | File layout | Notes |
|---|---|---|---|---|---|---|
| [frankfurter](frankfurter/) | FX rates | adaptix | sync httpx | flat | per-object | deterministic exact asserts; hand-authored spec |
| [open_meteo](open_meteo/) | weather | msgspec | async httpx | flat | per-object | concurrent `asyncio.gather`; nested structs + arrays; hand-authored spec |
| [jsonplaceholder](jsonplaceholder/) | fake REST | adaptix | sync requests | grouped | per-object | 4 tags, CRUD writes, nested models, camelCase query + body aliasing |

More are planned (scale-out): a multi-tag CRUD client (grouped layout) and
generation from a large real-world spec.
