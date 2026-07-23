"""IR data structures for operations (HTTP methods)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from unihttp_openapi_generator.ir.types import Import, IRType


class ParamLocation(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"


class BodyKind(StrEnum):
    JSON = "json"
    FORM = "form"
    MULTIPART = "multipart"


@dataclass
class IRParameter:
    name: str
    wire_name: str
    location: ParamLocation
    type: IRType
    required: bool
    description: str | None = None
    style: str | None = None
    explode: bool | None = None
    default: Any = None
    has_default: bool = False

    @property
    def needs_alias(self) -> bool:
        return self.name != self.wire_name


@dataclass
class IRBodyField:
    name: str
    wire_name: str
    type: IRType
    required: bool
    description: str | None = None
    is_file: bool = False
    default: Any = None
    has_default: bool = False

    @property
    def needs_alias(self) -> bool:
        return self.name != self.wire_name


@dataclass
class IRBody:
    kind: BodyKind
    required: bool
    content_type: str
    json_type: IRType | None = None
    fields: list[IRBodyField] = field(default_factory=list)


@dataclass
class IRResponse:
    status: str  # "200", "default", ...
    type: IRType | None
    description: str | None = None


@dataclass
class IROperation:
    operation_id: str
    class_name: str
    method_name: str
    http_method: str  # "GET", "POST", ...
    path: str
    tag: str
    parameters: list[IRParameter] = field(default_factory=list)
    body: IRBody | None = None
    success: IRResponse | None = None
    errors: list[IRResponse] = field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    deprecated: bool = False
    security: list[dict[str, list[str]]] = field(default_factory=list)

    @property
    def return_type(self) -> IRType | None:
        return self.success.type if self.success else None

    def imports(self) -> set[Import]:
        imports: set[Import] = set()
        for p in self.parameters:
            imports |= p.type.imports()
        if self.body is not None:
            if self.body.json_type is not None:
                imports |= self.body.json_type.imports()
            for f in self.body.fields:
                imports |= f.type.imports()
        if self.return_type is not None:
            imports |= self.return_type.imports()
        return imports

    def referenced_models(self) -> set[str]:
        names: set[str] = set()
        for p in self.parameters:
            names |= p.type.referenced_models()
        if self.body is not None:
            if self.body.json_type is not None:
                names |= self.body.json_type.referenced_models()
            for f in self.body.fields:
                names |= f.type.referenced_models()
        if self.return_type is not None:
            names |= self.return_type.referenced_models()
        for err in self.errors:
            if err.type is not None:
                names |= err.type.referenced_models()
        return names
