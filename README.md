# unihttp-openapi-generator

[![codecov](https://codecov.io/gh/goduni/unihttp-openapi-generator/branch/main/graph/badge.svg)](https://codecov.io/gh/goduni/unihttp-openapi-generator)
[![PyPI version](https://img.shields.io/pypi/v/unihttp-openapi-generator.svg)](https://pypi.org/project/unihttp-openapi-generator)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/unihttp-openapi-generator)
![PyPI - Downloads](https://img.shields.io/pypi/dm/unihttp-openapi-generator)
![GitHub License](https://img.shields.io/github/license/goduni/unihttp-openapi-generator)
![GitHub Repo stars](https://img.shields.io/github/stars/goduni/unihttp-openapi-generator)
[![Telegram](https://img.shields.io/badge/💬-Telegram-blue)](https://t.me/+OsmQESHc1xU1MGVi)

Turn an OpenAPI spec into a typed Python API client built on
[unihttp](https://github.com/goduni/unihttp).

Point it at a spec; get back an installable package with data models, request
classes, a sync and/or async client, an exception hierarchy, and authentication
wiring. The output is formatted with `ruff` and type-checks clean under `mypy --strict`.

## Why

- **Actually typed.** Models, parameters, and return values carry real annotations;
  the generated code passes `mypy --strict`. Your editor knows the shape of every
  request and response.
- **Three model backends.** Choose `adaptix` (default), `pydantic`, or `msgspec`
  for the generated models — same client, your serializer.
- **Sync, async, or both.** Backed by `httpx`, `aiohttp`, `requests`, `niquests`, or
  `zapros`, chosen per client.
- **Faithful to the spec.** `allOf`/`oneOf`/`anyOf`, discriminated unions, enums,
  formats, nullable, defaults, multipart uploads, query array styles, security
  schemes, and error responses are all carried through.
- **Proven on large specs.** The Stripe, GitHub, OpenAI, and Kubernetes specs each
  generate clean, importable code that passes `ruff` and `mypy --strict` on every
  serializer.
- **Readable, regenerable output.** Deterministic, `ruff`-formatted, organized by tag.

## Install

```bash
pip install unihttp-openapi-generator
# or, with uv:
uv tool install unihttp-openapi-generator
```

## Quick start

```bash
unihttp-openapi-generator generate openapi.yaml \
  --output-dir ./out --package-name acme_client
```

The spec can be a local path or a URL, in JSON or YAML. Install the result and use it:

```bash
pip install ./out
```

```python
from acme_client import AcmeClient

with AcmeClient(base_url="https://api.example.com", token="...") as client:
    pet = client.pets.get_pet(pet_id=1)   # -> a typed model
    print(pet.name)
```

## What you get

```
out/
├── pyproject.toml          # installable; pins unihttp + your serializer + backend
├── README.md
└── acme_client/
    ├── __init__.py         # exports the client(s), DEFAULT_BASE_URL, SERVERS
    ├── py.typed
    ├── models.py           # dataclass / BaseModel / msgspec.Struct
    ├── _serialization.py    # request/response (de)serialization wiring
    ├── exceptions.py       # ApiError hierarchy + status -> exception map
    ├── auth.py             # credential middlewares (when the spec defines security)
    ├── methods/<tag>.py    # one request class per operation
    └── client.py           # the client(s)
```

A request class and the client constructor (real output):

```python
@dataclass
class GetBooking(BaseMethod[GetBookingResponse]):
    """Get a booking

    Returns the details of a specific booking.
    """
    __url__ = "/bookings/{bookingId}"
    __method__ = "GET"

    booking_id: Path[UUID]


class TrainTravelAPIClient(RequestsSyncClient):
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *,
                 session: Any = None, middleware: list[Any] | None = None,
                 token: str | None = None) -> None:
        ...
```

## Using the client

Clients are context managers and close their transport on exit.

```python
from acme_client import AcmeClient

with AcmeClient(base_url="https://api.example.com", token="secret") as client:
    booking = client.bookings.get_booking(booking_id=some_uuid)   # grouped layout
    # client.get_booking(...)   # flat layout
```

Async clients expose the same surface; their methods are awaitables:

```python
import asyncio
from acme_client import AsyncAcmeClient

async def main() -> None:
    async with AsyncAcmeClient(token="secret") as client:
        trips = await client.trips.get_trips(origin=a, destination=b, date=when)

asyncio.run(main())
```

### Base URL and servers

The default base URL is taken from the spec's `servers` (preferring a production
entry). Every server is also exported:

```python
from acme_client import DEFAULT_BASE_URL, SERVERS

client = AcmeClient(base_url=SERVERS["Production"])
```

### Authentication

Each security scheme becomes a constructor keyword that is injected via middleware:

| Scheme | Keyword | Sent as |
|---|---|---|
| http bearer / oauth2 / openIdConnect | `token: str` | `Authorization: Bearer <token>` |
| apiKey (header or query) | `<scheme>: str` | the named header or query parameter |
| http basic | `<scheme>: tuple[str, str]` | `Authorization: Basic <base64>` |

### Custom headers, cookies, timeouts

Build the underlying HTTP client yourself and pass it as `session=` (its type matches
the chosen backend — `requests.Session` by default, `httpx.Client`, `aiohttp.ClientSession`, …):

```python
import requests

session = requests.Session()
session.headers["User-Agent"] = "acme/1.0"
client = AcmeClient(session=session)
```

### Errors

Non-2xx responses raise. `<package>.exceptions` defines a base `ApiError` plus a
subclass per status code (`NotFoundError`, `UnprocessableEntityError`, …), with
`4xx`/`5xx` falling back to unihttp's `ClientError`/`ServerError`.

```python
from acme_client.exceptions import ApiError, NotFoundError

try:
    booking = client.bookings.get_booking(booking_id=bad_id)
except NotFoundError as exc:
    print(exc.status_code, exc.response.data)
except ApiError:
    ...
```

### Middleware

Pass any unihttp middleware; auth and error mapping are composed around it.

```python
from unihttp.middlewares.retry import RetryMiddleware
client = AcmeClient(middleware=[RetryMiddleware(retries=3)])
```

## CLI options

```
unihttp-openapi-generator generate SPEC [options]
```

| Option | Values (default) |
|---|---|
| `-o`, `--output-dir` | path (required) |
| `--package-name` | identifier (required) |
| `--serializer` | `adaptix` · `pydantic` · `msgspec` (`adaptix`) |
| `--client` | `both` · `sync` · `async` (`both`) |
| `--sync-backend` | `httpx` · `requests` · `niquests` · `zapros` (`requests`) |
| `--async-backend` | `httpx` · `aiohttp` · `niquests` · `zapros` (`aiohttp`) |
| `--layout` | `auto` · `flat` · `grouped` (`auto`) |
| `--file-layout` | `single` · `per-object` (`single`) |
| `--style` | `declarative` · `imperative` (`declarative`) |
| `--optional` | `none` · `omitted` (`none`) — `omitted` distinguishes absent from null (adaptix) |
| `--strip-prefix` | `auto` or a dotted prefix to drop from schema names (e.g. `io.k8s.api.core.v1.Pod` → `CoreV1Pod`) |
| `--inheritance` | off by default — render `allOf: [$ref]` as a base class instead of merging its fields in |
| `--check` | run `ruff` and `mypy --strict` on the output |
| `--config` | TOML config file |

### Config file

Keep your generation settings in a TOML file so a regenerate is a single command and
the configuration lives in version control.

**Precedence.** For every setting: an explicit CLI flag wins, otherwise the config
file, otherwise the built-in default. So you can pin a project's settings in the file
and still override one of them ad hoc on the command line:

```bash
unihttp-openapi-generator generate                       # use the discovered config
unihttp-openapi-generator generate --serializer msgspec  # override just this one
```

**Discovery order** (the first that exists is used):

1. the file passed to `--config FILE`,
2. `unihttp-openapi-generator.toml` in the current directory,
3. a `[tool.unihttp-openapi-generator]` table in `pyproject.toml`.

**Keys** mirror the CLI options exactly. `spec`, `output_dir`, and `package_name` are
required (from the file or the command line); everything else is optional and falls
back to the default shown in the [CLI options](#cli-options) table. Unknown keys are
rejected so typos surface immediately.

A fully annotated `unihttp-openapi-generator.toml`:

```toml
spec = "https://api.example.com/openapi.json"  # path or URL; JSON or YAML
output_dir = "out"                             # where the package is written
package_name = "acme_client"                   # importable package name

serializer = "adaptix"        # adaptix | pydantic | msgspec
client = "both"               # both | sync | async
sync_backend = "requests"     # httpx | requests | niquests | zapros
async_backend = "aiohttp"     # httpx | aiohttp | niquests | zapros
layout = "auto"               # auto | flat | grouped     (client shape)
file_layout = "single"        # single | per-object       (files on disk)
style = "declarative"         # declarative | imperative  (method style)
optional = "none"             # none | omitted            (optional model fields)
strip_prefix = "auto"         # "auto" or a dotted prefix to drop from schema names
inheritance = false           # allOf: [$ref] -> a base class instead of merged fields
check = true                  # run ruff + mypy --strict on the output
```

Or, to keep it inside an existing project, drop the same keys under a table in
`pyproject.toml`:

```toml
[tool.unihttp-openapi-generator]
spec = "openapi.yaml"
output_dir = "out"
package_name = "acme_client"
serializer = "pydantic"
client = "async"
```

## Serializers

| | adaptix (default) | pydantic | msgspec |
|---|---|---|---|
| Model type | `@dataclass` | `BaseModel` | `msgspec.Struct` |
| Field aliasing | full (retort name mapping) | `Field(alias=…)` | `field(name=…)` |
| Query array styles | full | explode only | explode only |
| Runtime validation | — | yes | yes |

`adaptix` gives the highest fidelity (parameter aliases and all query array styles).
`pydantic` adds runtime validation; `msgspec` is the fastest.

## Generation options

These shape the surface and style of the generated code. All have sensible defaults;
reach for them to match an existing codebase or taste.

### Client layout — `--layout`

How methods are exposed on the client.

- `flat` — every operation is a method on one client class:
  ```python
  client.get_booking(booking_id=...)
  client.create_booking(body=...)
  ```
- `grouped` — operations are grouped into sub-clients by their OpenAPI tag (nicer for
  large APIs):
  ```python
  client.bookings.get_booking(booking_id=...)
  client.payments.create_payment(...)
  ```
- `auto` (default) — `flat` when the spec has at most one tag, `grouped` otherwise.

### File layout — `--file-layout`

How the package is split on disk. The import surface is identical either way.

- `single` (default) — one `models.py` and one `methods/<tag>.py` per tag. Fewer, larger
  files.
- `per-object` — one file per model/enum and per request method
  (`models/<name>.py`, `methods/<tag>/<method>.py`). Easier to navigate and gives small,
  focused diffs on regeneration, at the cost of many files. Cross-references between
  modules are resolved automatically without circular imports.

### Method style — `--style`

How client methods are written.

- `declarative` (default) — methods are bound from the request classes. Compact; the
  call signature comes from the request dataclass:
  ```python
  class BookingsClient:
      get_booking = bind_method(GetBooking)
  ```
- `imperative` — an explicit, fully-typed wrapper per operation. More generated code,
  but the signature is spelled out for the best editor experience:
  ```python
  def get_trips(self, *, origin: UUID, destination: UUID, date: datetime,
                page: int = 1, limit: int = 10) -> GetTripsResponse:
      return self.call_method(GetTrips(origin=origin, destination=destination,
                                       date=date, page=page, limit=limit))
  ```

### Optional fields — `--optional`

How optional model fields are represented (adaptix only).

- `none` (default) — `T | None = None`. Simple, but "field absent" and "field is null"
  both read as `None`.
  ```python
  middle_name: str | None = None
  ```
- `omitted` — `Omittable[T] = Omitted()`. Distinguishes a field you never set from one
  set to `null`; unset fields are dropped from the request body entirely. Useful for
  PATCH-style APIs where sending `null` clears a value:
  ```python
  middle_name: Omittable[str | None] = Omitted()
  ```

### Inheritance — `--inheritance`

What to do with `allOf: [{$ref: Base}, ...]`.

- off (default) — the base's properties are **merged into** each subtype, and a base
  with a `discriminator` becomes a union alias:
  ```python
  @dataclass
  class CallbackButton:
      text: str                              # copied from Button
      payload: str
      type: Literal['callback'] = 'callback'

  type Button = CallbackButton | LinkButton
  ```
- `--inheritance` — the base stays a class and subtypes **inherit** from it, keeping
  only their own properties plus the discriminator tag:
  ```python
  @dataclass(kw_only=True)
  class Button:
      type: str
      text: str

  @dataclass(kw_only=True)
  class CallbackButton(Button):
      payload: str
      type: Literal['callback'] = 'callback'
  ```
  `isinstance` then works across the hierarchy, and a subtype's own properties stay in
  one place instead of being copied into every variant.

  Scope and rules:

  - Only an `allOf` with exactly **one** `$ref` maps onto a base class — several refs
    are mixin-style composition with no single parent to pick, so those keep the merge
    behaviour. So does a `$ref` to an enum or a non-object schema.
  - Only a base that declares **its own properties** becomes a class. The usual
    polymorphism idiom puts the discriminator on a bare `oneOf` holder that has no
    properties at all; there is nothing to inherit from it, so it stays a union alias
    (`type Button = CallbackButton | LinkButton`) and keeps decoding into the concrete
    variant. `--inheritance` only changes how the subtypes get *their* shared fields.
  - Constructors become keyword-only **for the models in a hierarchy** — a subclass may
    pin an inherited field to a default while adding required fields of its own, which
    positional ordering cannot express. Models outside every hierarchy are untouched.
  - A subtype that restates an inherited property just to attach prose, or to relax it
    to nullable, simply **inherits** it: re-declaring `v: str | None` over the base's
    `v: str` is rejected by `mypy --strict`. Genuine narrowings (a `Literal` tag over a
    `str`) are kept.

  One thing to know: when a discriminated base *does* stay a class, no serializer
  resolves the concrete subtype from a base-class annotation on its own — a field typed
  `Button` decodes into `Button`. The generated class carries a
  `# discriminator: type (callback=CallbackButton, ...)` comment with the mapping so
  the tagged decoding can be wired in `_serialization.py`. Leave `--inheritance` off if
  you want polymorphic responses to parse into subtypes out of the box.

## OpenAPI coverage

- 3.0 and 3.1; JSON or YAML; file or URL; internal and external `$ref`.
- Schemas: objects, `allOf` (merged, or real inheritance with `--inheritance`),
  `oneOf`/`anyOf`, discriminator (including polymorphic bases), enums and `const`,
  formats, nullable, `additionalProperties`, constraints, recursion, and `readOnly`
  (excluded from request bodies).
- Operations: path/query/header parameters with defaults, JSON/form/multipart bodies,
  file uploads, typed responses, and `deprecated`.
- Security: apiKey, http bearer/basic, oauth2, openIdConnect.

## Limitations

- Response headers are not exposed; methods return the response body.
- `deepObject` query parameters and full parameter aliasing work on `adaptix`; on
  `pydantic` and `msgspec` they are limited.
- Swagger / OpenAPI 2.0 is not supported (use the OpenAPI 3 description if a service
  publishes both, as Kubernetes does).

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy
```

## License

MIT
