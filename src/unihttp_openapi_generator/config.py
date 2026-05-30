"""Typed configuration for the generator."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator


class Serializer(StrEnum):
    ADAPTIX = "adaptix"
    PYDANTIC = "pydantic"
    MSGSPEC = "msgspec"


class ClientKind(StrEnum):
    SYNC = "sync"
    ASYNC = "async"
    BOTH = "both"


class SyncBackend(StrEnum):
    HTTPX = "httpx"
    REQUESTS = "requests"
    NIQUESTS = "niquests"
    ZAPROS = "zapros"


class AsyncBackend(StrEnum):
    HTTPX = "httpx"
    AIOHTTP = "aiohttp"
    NIQUESTS = "niquests"
    ZAPROS = "zapros"


class MethodStyle(StrEnum):
    DECLARATIVE = "declarative"
    IMPERATIVE = "imperative"


class Layout(StrEnum):
    AUTO = "auto"  # flat when <=1 tag, grouped otherwise
    FLAT = "flat"  # all methods on a single client
    GROUPED = "grouped"  # per-tag sub-clients (client.<tag>.<method>)


class OptionalStyle(StrEnum):
    NONE = "none"  # optional model fields rendered as `T | None = None`
    OMITTED = "omitted"  # rendered as `Omittable[T] = Omitted()` (adaptix only)


class FileLayout(StrEnum):
    SINGLE = "single"  # one models.py + one methods/<tag>.py per tag (default)
    PER_OBJECT = "per-object"  # one file per model/enum/alias and per request method


class GeneratorConfig(BaseModel):
    """Resolved configuration for a single generation run."""

    model_config = ConfigDict(frozen=True)

    package_name: str
    output_dir: Path
    serializer: Serializer = Serializer.ADAPTIX
    client: ClientKind = ClientKind.BOTH
    sync_backend: SyncBackend = SyncBackend.REQUESTS
    async_backend: AsyncBackend = AsyncBackend.AIOHTTP
    style: MethodStyle = MethodStyle.DECLARATIVE
    layout: Layout = Layout.AUTO
    optional: OptionalStyle = OptionalStyle.NONE
    file_layout: FileLayout = FileLayout.SINGLE
    strip_prefix: str | None = None  # "auto" or a dotted prefix to drop from schema names
    check: bool = False

    @model_validator(mode="after")
    def _validate(self) -> GeneratorConfig:
        if not self.package_name.isidentifier():
            raise ValueError(
                f"package_name {self.package_name!r} is not a valid Python package identifier"
            )
        if self.optional is OptionalStyle.OMITTED and self.serializer is not Serializer.ADAPTIX:
            raise ValueError("--optional omitted is only supported with the adaptix serializer")
        return self

    @property
    def emit_sync(self) -> bool:
        return self.client in (ClientKind.SYNC, ClientKind.BOTH)

    @property
    def emit_async(self) -> bool:
        return self.client in (ClientKind.ASYNC, ClientKind.BOTH)

    def resolve_layout(self, tag_count: int) -> Layout:
        """Concrete layout for a document with ``tag_count`` tags."""
        if self.layout is Layout.AUTO:
            return Layout.FLAT if tag_count <= 1 else Layout.GROUPED
        return self.layout
