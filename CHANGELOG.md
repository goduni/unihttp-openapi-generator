# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) — while at `0.x`, a breaking
change bumps the minor version.

## [0.3.1] — 2026-08-17

### Fixed

- **`--check` failed on correct output.** It linted the generated package against
  ruff's *default* rule selection, which is not a fixed target: ruff 0.16 folded the
  `RUF` rules into it, and since the generator declares `ruff>=0.6.0`, any fresh
  install picked that up. Every generated package failed its own gate on both 0.2.0 and
  0.3.0 — `RUF009` on the `Omitted()` sentinel (a singleton, so the rule's premise does
  not hold) and `RUF022` on `__all__` ordering.

- **The same spec produced different bytes depending on where you ran the generator.**
  The formatting pass let ruff discover config the way ruff normally does — from the
  working directory and its parents — so a client generated inside a project with its
  own `line-length` came out wrapped differently from the same client generated
  anywhere else. Generation is deterministic again, which the README always claimed.

- **`--check` reported a correct package as broken when generating into `./out`.**
  mypy runs with `--explicit-package-bases`, under which module names are derived
  relative to the working directory: a package generated beneath it became
  `out.acme_client`, so every intra-package import — each spelling the package's real
  name — was unresolvable. It now runs from the package's parent. This was hidden
  behind the ruff failure above, which came first.

The first two come from the same root: the generated package had no lint configuration
of its own, so the tools reached for whatever was around. It has one now.

All three were invisible to CI, which pins `ruff` and `mypy` in `uv.lock` while the
generator declares open lower bounds — so the gate ran old versions of both while every
fresh install got new ones. The pinned versions have been brought up to date, and the
gate now checks what a user actually gets.

### Changed

- Generated `pyproject.toml` carries a `[tool.ruff]` table, and both the formatting pass
  and `--check` read it — never ruff's defaults, never an ambient config. The rule set
  is broad and was verified against generated packages across every serializer, both
  file layouts, both method styles, both optional styles, and with and without
  inheritance and stubs. What it disables, it disables because the *spec* decides it:
  parameter names come from the wire (`id`, `type`), `Omitted()` is a singleton rather
  than a mutable default, method size follows the operation's parameter count, and
  forward references are resolved by deferred imports.

  Regenerating an existing client will therefore show a new section in its
  `pyproject.toml`, and reformatting if it was generated inside a project whose
  `line-length` differed from 88.

- `__all__` is emitted in the order linters expect (constants, then classes) rather than
  plain alphabetical.

## [0.3.0] — 2026-08-17

### Breaking

- **`--inheritance`: a subtype's explicit re-declaration is now kept, which can change
  how a generated model decodes.** Previously a subtype that restated an inherited
  property was silently made to inherit the base's declaration instead. The declaration
  is now preserved, so where a subtype re-declares a property as nullable the model
  **accepts `null` for it**, having rejected it before.

  The annotation consumers see widens with it: code that read such a field as `str` now
  gets `str | None` and fails `mypy` until it handles the `None`. **Regenerating a client
  against a spec that does this is a breaking change for that client's callers** — check
  the fields the generator warns about (see below) after upgrading.

  A subtype that does *not* restate the property is unaffected, and models outside every
  hierarchy are untouched. Without `--inheritance` the output is byte-for-byte unchanged.

### Added

- A property's `description` is emitted as a
  [PEP 258](https://peps.python.org/pep-0258/) attribute docstring under the field, so
  editors show it on hover. Applies to every serializer and to both file layouts, and is
  inert at runtime — construction, decoding, and the emitted JSON schema are unchanged.

  ```python
  class Pet(BaseModel):
      id: int
      """Server-assigned identifier."""
  ```

  Schema descriptions already became class docstrings; parameters and body fields on
  request classes already had this. Models were the gap.

- `--inheritance` now recognises two more override shapes as compatible, so they render
  without a suppression comment: a `$ref` narrowed to a schema that inherits from the
  base's (`companion: Pet` over `companion: Creature`), and Python's numeric tower
  (`integer` over `number`, `boolean` over `integer`).

- An override the base cannot admit is reported as a warning naming the schema and the
  property, because a subtype that is not substitutable for its base is a defect worth
  fixing in the spec rather than in its clients.

### Fixed

- `--inheritance --check` no longer fails on ordinary specs. An override the builder
  judged incompatible was emitted with a bare `# type: ignore[assignment]`; where mypy
  disagreed — a `$ref` narrowed to a subtype, `boolean` over `integer` — that ignore was
  unused, which `mypy --strict` reports as an error of its own. The suppression now
  carries `unused-ignore` alongside `assignment`, so the gap between the IR's view of a
  type and mypy's costs a redundant comment instead of a failed build.

## [0.2.0] — 2026-08-14

### Added

- `--inheritance`: `allOf: [{$ref: Base}, ...]` emits real subclasses instead of merging
  the base's properties down, including discriminated bases, enum-typed discriminator
  tags pinned to the matching member, and multi-level chains.
- `--stubs`: emits `client.pyi` for editors that cannot follow `bind_method`.
- Body-field descriptions on request classes.

### Fixed

- `ruff` and `mypy` are resolved from the generator's own environment.

## [0.1.0]

Initial release.

[0.3.1]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.3.1
[0.3.0]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.3.0
[0.2.0]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.2.0
[0.1.0]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.1.0
