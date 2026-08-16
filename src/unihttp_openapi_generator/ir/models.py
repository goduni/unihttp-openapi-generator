"""IR data structures for schema-derived declarations (models, enums, aliases)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from unihttp_openapi_generator.ir.types import Import, IRType


@dataclass(frozen=True)
class Discriminator:
    """OpenAPI discriminator for a tagged union."""

    property_name: str
    mapping: dict[str, str] = field(default_factory=dict)
    """Maps discriminator value -> generated class name."""


@dataclass
class IRField:
    """A single field of an object model."""

    name: str
    wire_name: str
    type: IRType
    required: bool
    description: str | None = None
    default: Any = None
    has_default: bool = False
    default_expr: str | None = None
    """Python source for the default, when it is not expressible as a bare literal.

    Set for an enum-typed discriminator tag (``ButtonKind.CALLBACK``), which has to be
    written as an attribute access rather than the ``'callback'`` that ``default``
    holds. Renderers emit this verbatim in place of ``repr(default)``; the referenced
    class is reported by ``runtime_refs`` so the module imports it at runtime.
    """
    omittable: bool = False
    read_only: bool = False
    write_only: bool = False
    constraints: dict[str, Any] = field(default_factory=dict)
    incompatible_override: bool = False
    """Whether this field re-declares an inherited one with a type the base does not admit.

    A fact about the spec, not a rendering decision: the subtype asked for something
    ``class Sub(Base)`` cannot express soundly. What to do about it belongs to the
    serializer strategies (see ``override_suppression``).
    """

    @property
    def needs_alias(self) -> bool:
        return self.name != self.wire_name


@dataclass
class IRModel:
    """An object schema rendered as a model class."""

    name: str
    fields: list[IRField] = field(default_factory=list)
    description: str | None = None
    additional_properties: IRType | None = None
    discriminator: Discriminator | None = None
    base_model: str | None = None
    """Name of the model this one inherits from (inheritance mode only).

    Set when the schema is ``allOf: [{$ref: Base}, ...]`` and the builder ran with
    ``inheritance=True``; ``fields`` then holds only this model's *own* properties.
    Without that flag the base's properties are merged in and this stays None.

    Deliberately *not* named ``base``: ``IREnum.base`` is the enum's value type
    ("str"/"int"), so a ``getattr(decl, "base", None)`` loop over declarations would
    silently read an enum's ``"str"`` as a superclass name.
    """

    def imports(self) -> set[Import]:
        imports: set[Import] = set()
        for f in self.fields:
            imports |= f.type.imports()
        if self.additional_properties is not None:
            imports |= self.additional_properties.imports()
        return imports

    def referenced_models(self) -> set[str]:
        names: set[str] = set()
        for f in self.fields:
            names |= f.type.referenced_models()
        if self.additional_properties is not None:
            names |= self.additional_properties.referenced_models()
        if self.base_model is not None:
            names.add(self.base_model)
        return names - {self.name}

    def runtime_refs(self) -> set[str]:
        """Declarations this model evaluates at class-definition time.

        Everything else lives inside an annotation and stays deferred, but a base class
        in the ``class Sub(Base)`` statement and a class referenced by a default
        expression are both evaluated when the module is imported, so a split layout
        has to import them for real rather than under ``TYPE_CHECKING``.
        """
        names = {self.base_model} if self.base_model is not None else set()
        for f in self.fields:
            if f.default_expr is not None:
                names.add(f.default_expr.partition(".")[0])
        return names - {self.name}


@dataclass
class IREnum:
    """A schema with an ``enum`` of scalar values."""

    name: str
    base: str  # "str" or "int"
    members: list[tuple[str, Any]] = field(default_factory=list)
    description: str | None = None

    def imports(self) -> set[Import]:
        return set()

    def referenced_models(self) -> set[str]:
        return set()


@dataclass
class IRAlias:
    """A named schema that is not an object (scalar, array, union, mapping)."""

    name: str
    target: IRType
    description: str | None = None
    discriminator: Discriminator | None = None

    def imports(self) -> set[Import]:
        return self.target.imports()

    def referenced_models(self) -> set[str]:
        return self.target.referenced_models() - {self.name}


Declaration = IRModel | IREnum | IRAlias
