# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) — while at `0.x`, a breaking
change bumps the minor version.

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

[0.3.0]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.3.0
[0.2.0]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.2.0
[0.1.0]: https://github.com/goduni/unihttp-openapi-generator/releases/tag/v0.1.0
