"""The fully-built IR document — the contract handed to renderers."""

from __future__ import annotations

from dataclasses import dataclass, field

from unihttp_openapi_generator.ir.models import Declaration
from unihttp_openapi_generator.ir.operations import IROperation


@dataclass(frozen=True)
class Server:
    """A server entry from the spec's ``servers`` list."""

    url: str
    description: str | None = None


@dataclass(frozen=True)
class SecurityScheme:
    name: str
    kind: str  # "apiKey" | "http" | "oauth2" | "openIdConnect"
    location: str | None = None  # for apiKey: "header" | "query" | "cookie"
    parameter_name: str | None = None  # for apiKey: header/query name
    scheme: str | None = None  # for http: "bearer" | "basic"


@dataclass
class IRDocument:
    title: str
    version: str
    base_url: str | None
    declarations: list[Declaration] = field(default_factory=list)
    operations: list[IROperation] = field(default_factory=list)
    security_schemes: dict[str, SecurityScheme] = field(default_factory=dict)
    servers: list[Server] = field(default_factory=list)

    @property
    def tags(self) -> list[str]:
        seen: list[str] = []
        for op in self.operations:
            if op.tag not in seen:
                seen.append(op.tag)
        return seen

    def operations_for_tag(self, tag: str) -> list[IROperation]:
        return [op for op in self.operations if op.tag == tag]
