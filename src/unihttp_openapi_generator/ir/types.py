"""The IR type system.

Each ``IRType`` knows how to render itself as a Python annotation string and which
imports that annotation requires. Annotation strings are backend-agnostic: the
difference between serializers lives in how *models* are declared, not in the
annotations of their fields. Generated modules use ``from __future__ import
annotations`` so forward references resolve lazily.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, order=True)
class Import:
    """A single ``from <module> import <name>`` requirement."""

    module: str
    name: str


class IRType:
    """Base class for all IR types."""

    def annotation(self) -> str:
        raise NotImplementedError

    def imports(self) -> set[Import]:
        return set()

    def referenced_models(self) -> set[str]:
        """Names of generated model/enum classes this type refers to."""
        return set()


@dataclass(frozen=True)
class PrimitiveType(IRType):
    py: str
    extra_imports: tuple[Import, ...] = ()

    def annotation(self) -> str:
        return self.py

    def imports(self) -> set[Import]:
        return set(self.extra_imports)


STR = PrimitiveType("str")
INT = PrimitiveType("int")
FLOAT = PrimitiveType("float")
BOOL = PrimitiveType("bool")
BYTES = PrimitiveType("bytes")
NONE = PrimitiveType("None")
ANY = PrimitiveType("Any", (Import("typing", "Any"),))
DATETIME = PrimitiveType("datetime", (Import("datetime", "datetime"),))
DATE = PrimitiveType("date", (Import("datetime", "date"),))
TIME = PrimitiveType("time", (Import("datetime", "time"),))
TIMEDELTA = PrimitiveType("timedelta", (Import("datetime", "timedelta"),))
UUID = PrimitiveType("UUID", (Import("uuid", "UUID"),))
DECIMAL = PrimitiveType("Decimal", (Import("decimal", "Decimal"),))


@dataclass(frozen=True)
class RefType(IRType):
    """Reference to a generated model/enum/alias by its class name."""

    name: str

    def annotation(self) -> str:
        return self.name

    def referenced_models(self) -> set[str]:
        return {self.name}


@dataclass(frozen=True)
class ListType(IRType):
    item: IRType

    def annotation(self) -> str:
        return f"list[{self.item.annotation()}]"

    def imports(self) -> set[Import]:
        return self.item.imports()

    def referenced_models(self) -> set[str]:
        return self.item.referenced_models()


@dataclass(frozen=True)
class MappingType(IRType):
    value: IRType

    def annotation(self) -> str:
        return f"dict[str, {self.value.annotation()}]"

    def imports(self) -> set[Import]:
        return self.value.imports()

    def referenced_models(self) -> set[str]:
        return self.value.referenced_models()


@dataclass(frozen=True)
class UnionType(IRType):
    members: tuple[IRType, ...]

    def annotation(self) -> str:
        return " | ".join(m.annotation() for m in self.members)

    def imports(self) -> set[Import]:
        return {imp for m in self.members for imp in m.imports()}

    def referenced_models(self) -> set[str]:
        return {name for m in self.members for name in m.referenced_models()}


@dataclass(frozen=True)
class OptionalType(IRType):
    inner: IRType

    def annotation(self) -> str:
        return f"{self.inner.annotation()} | None"

    def imports(self) -> set[Import]:
        return self.inner.imports()

    def referenced_models(self) -> set[str]:
        return self.inner.referenced_models()


@dataclass(frozen=True)
class LiteralType(IRType):
    values: tuple[str | int | bool, ...]

    def annotation(self) -> str:
        rendered = ", ".join(repr(v) for v in self.values)
        return f"Literal[{rendered}]"

    def imports(self) -> set[Import]:
        return {Import("typing", "Literal")}


def optional(inner: IRType) -> IRType:
    """Wrap in ``| None`` unless it already admits None."""
    if isinstance(inner, OptionalType) or inner is NONE:
        return inner
    if isinstance(inner, UnionType) and NONE in inner.members:
        return inner
    return OptionalType(inner)


@dataclass
class UploadFileType(IRType):
    """unihttp's ``UploadFile`` for multipart file parts."""

    imports_: set[Import] = field(default_factory=lambda: {Import("unihttp.http", "UploadFile")})

    def annotation(self) -> str:
        return "UploadFile"

    def imports(self) -> set[Import]:
        return set(self.imports_)
