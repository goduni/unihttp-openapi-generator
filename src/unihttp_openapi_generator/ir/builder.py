"""Transform an OpenAPI 3.1 document into the IR."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from unihttp_openapi_generator.ir.document import IRDocument, SecurityScheme, Server
from unihttp_openapi_generator.ir.models import (
    Declaration,
    Discriminator,
    IRAlias,
    IREnum,
    IRField,
    IRModel,
)
from unihttp_openapi_generator.ir.naming import (
    NameRegistry,
    class_name,
    field_name,
    method_name,
)
from unihttp_openapi_generator.ir.operations import (
    BodyKind,
    IRBody,
    IRBodyField,
    IROperation,
    IRParameter,
    IRResponse,
    ParamLocation,
)
from unihttp_openapi_generator.ir.types import (
    ANY,
    BOOL,
    BYTES,
    DATE,
    DATETIME,
    DECIMAL,
    FLOAT,
    INT,
    STR,
    TIME,
    UUID,
    IRType,
    ListType,
    LiteralType,
    MappingType,
    OptionalType,
    PrimitiveType,
    RefType,
    UnionType,
    UploadFileType,
    optional,
)
from unihttp_openapi_generator.refs import RefResolver

logger = logging.getLogger(__name__)

_HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")

# Python's numeric tower as mypy applies it: an ``int`` is accepted wherever a ``float``
# is expected, and a ``bool`` wherever an ``int`` is. A subtype re-typing ``number`` as
# ``integer`` is an ordinary OpenAPI narrowing, so it must not read as incompatible.
_PROMOTIONS = frozenset({("int", "float"), ("bool", "int"), ("bool", "float")})

# Identifiers imported into generated modules; a model/method class must never reuse one
# or it would shadow the import (markers, unihttp core, serializer bases, common types).
_RESERVED_NAMES = frozenset(
    {
        "Path", "Query", "Header", "Body", "Form", "File",
        "BaseMethod", "Omitted", "Omittable", "UploadFile", "bind_method",
        "dataclass", "field", "StrEnum", "IntEnum",
        "BaseModel", "ConfigDict", "Field", "Struct", "Meta",
        "Any", "Literal", "Annotated", "TYPE_CHECKING",
        "datetime", "date", "time", "timedelta", "UUID", "Decimal",
    }
)  # fmt: skip

_STRING_FORMATS: dict[str, IRType] = {
    "date-time": DATETIME,
    "date": DATE,
    "time": TIME,
    "uuid": UUID,
    "binary": BYTES,
    "decimal": DECIMAL,
}

_CONSTRAINT_KEYS = (
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "format",
)


class IRBuilder:
    def __init__(
        self,
        spec: dict[str, Any],
        resolver: RefResolver,
        root_uri: str = "",
        *,
        omit_optionals: bool = False,
        strip_prefix: str | None = None,
        inheritance: bool = False,
    ) -> None:
        self._spec = spec
        self._resolver = resolver
        self._root_uri = root_uri
        self._omit_optionals = omit_optionals
        self._inheritance = inheritance
        # Wire names a model listed in its own ``required``, keyed by class name.
        # Under inheritance a subtype routinely tightens a base property by naming it
        # in ``required`` without restating the property, and nothing in ``fields``
        # records that; ``_restore_required_narrowing`` replays it once the base chain
        # is known. Kept out of the IR because it is builder bookkeeping.
        self._own_required: dict[str, set[str]] = {}
        self._strip_segments = self._resolve_strip_segments(strip_prefix)
        self._declarations: dict[str, Declaration] = {}
        # one registry for all top-level class names (models, enums, aliases, method
        # classes) seeded with reserved import names, so nothing shadows an import.
        self._names = NameRegistry()
        for reserved in _RESERVED_NAMES:
            self._names.reserve(reserved)
        self._ref_to_name: dict[tuple[str, str], str] = {}
        # ref-key of a discriminated subtype -> (discriminator wire property, tag value)
        self._disc_subtype: dict[tuple[str, str], tuple[str, Any]] = {}

    # -- public ----------------------------------------------------------------

    def build(self) -> IRDocument:
        self._collect_discriminator_subtypes()
        self._build_components()
        operations = self._build_operations()
        info = self._spec.get("info", {})
        servers = self._build_servers()
        base_url = self._select_base_url(servers)
        # A servers URL may carry a path prefix (e.g. ".../api/v3"). unihttp joins
        # requests with urljoin(base_url, "/op"), which drops that prefix, so fold
        # it into each operation url and reduce base_url/servers to bare origins.
        prefix = self._shared_base_path(servers)
        if prefix:
            for op in operations:
                op.path = prefix + op.path
            servers = [
                Server(origin, s.description) for s in servers if (origin := self._origin(s.url))
            ]
            if base_url is not None:
                base_url = self._origin(base_url) or None
        declarations = self._ordered_declarations()
        self._reconcile_inheritance(declarations)
        return IRDocument(
            title=info.get("title", "API"),
            version=info.get("version", "0.0.0"),
            base_url=base_url,
            declarations=declarations,
            operations=operations,
            security_schemes=self._build_security_schemes(),
            servers=servers,
        )

    def _ordered_declarations(self) -> list[Declaration]:
        """Declarations in emit order: a base class always precedes its subclasses.

        Subtypes are converted while their base is still being built, so insertion
        order alone would put a subclass before the class it inherits from - and a
        ``class Sub(Base)`` statement evaluates its base at definition time.
        """
        declarations = list(self._declarations.values())
        if not self._inheritance:
            return declarations
        by_name = {decl.name: decl for decl in declarations}
        ordered: list[Declaration] = []
        done: set[str] = set()
        on_stack: set[str] = set()
        broken: list[tuple[IRModel, str]] = []

        def visit(decl: Declaration) -> None:
            if decl.name in done:
                return
            # Grey marking: a name still on the stack means the base chain loops back
            # on itself. Emitting either end first is wrong, so break the cycle by
            # dropping the inheritance edge rather than emitting unresolvable code.
            on_stack.add(decl.name)
            base = decl.base_model if isinstance(decl, IRModel) else None
            if base is not None and base in by_name:
                if base in on_stack:
                    logger.warning(
                        "inheritance cycle at %r -> %r; merging the base in instead",
                        decl.name,
                        base,
                    )
                    assert isinstance(decl, IRModel)
                    decl.base_model = None
                    broken.append((decl, base))
                else:
                    visit(by_name[base])
            on_stack.discard(decl.name)
            done.add(decl.name)
            ordered.append(decl)

        for decl in declarations:
            visit(decl)
        # After the walk, so every ``base_model`` the merge reads is already final.
        for orphan, dropped in broken:
            self._merge_dropped_base(orphan, by_name, dropped)
        return ordered

    def _merge_dropped_base(
        self, model: IRModel, by_name: dict[str, Declaration], base: str
    ) -> None:
        """Copy a dropped base's fields back in, so breaking a cycle loses no data.

        Clearing ``base_model`` alone leaves the model with nothing but the properties
        it declared itself, and every field it used to inherit disappears from the
        output. Merge mode flattens the very same cycle and keeps them, so this is the
        one place inheritance mode would decode strictly less than the default.
        """
        own = {f.wire_name for f in model.fields}
        used = NameRegistry()
        for f in model.fields:
            used.reserve(f.name)
        for wire, inherited_field in self._inherited_fields(by_name, base).items():
            if wire in own:
                continue
            copied = replace(inherited_field, constraints=dict(inherited_field.constraints))
            copied.name = used.reserve(inherited_field.name)
            model.fields.append(copied)
        # ``additionalProperties`` is merged up the ``allOf`` chain in merge mode, so
        # dropping it here would still decode fewer wire keys than the default does.
        parent = by_name.get(base)
        if (
            isinstance(parent, IRModel)
            and model.additional_properties is None
            and parent.additional_properties is not None
        ):
            model.additional_properties = parent.additional_properties
        # No ``required`` replay is needed here even though ``_reconcile_inheritance``
        # skips this model from now on: ``_flatten_object`` unions ``required`` across
        # every ``allOf`` member, and a cycle means it flows both ways, so each end
        # already built the shared field as required.

    def _reconcile_inheritance(self, declarations: list[Declaration]) -> None:
        """Make every subclass agree with its base chain (inheritance mode only).

        Deliberately a whole-graph pass rather than a step inside ``_build_object``:
        the fields a subtype may keep depend on the *final* field set of every class
        above it, and while a subtype is being converted its base can still be
        mid-build (a recursive hierarchy) or be a base of its own. ``declarations``
        arrives base-before-subclass, so each model here sees ancestors that are
        already reconciled.
        """
        if not self._inheritance:
            return
        by_name = {decl.name: decl for decl in declarations}
        for decl in declarations:
            if isinstance(decl, IRModel) and decl.base_model is not None:
                inherited = self._inherited_fields(by_name, decl.base_model)
                self._restore_required_narrowing(decl, inherited)
                self._retype_discriminator_tag(decl, inherited, by_name)
                self._mark_unsafe_overrides(decl, inherited, by_name)
                self._rename_shadowed_fields(decl, inherited)
                self._align_override_names(decl, inherited)

    def _restore_required_narrowing(self, model: IRModel, inherited: dict[str, IRField]) -> None:
        """Re-declare an inherited field the subtype narrows only via ``required``.

        Naming a base property in the subtype's ``required`` without restating the
        property is the ordinary way a spec tightens a base. Merge mode picks the
        stronger requiredness up for free, because there is one merged property; under
        inheritance the property stays on the base and nothing carried the tightening
        down, so a spec-required field silently kept the base's ``T | None = None``.

        The re-declaration keeps the base's *annotation* and only drops the default:
        an optional field is rendered ``T | None`` whether it is optional or genuinely
        nullable, and the IR no longer distinguishes the two, so narrowing to ``T``
        could reject a null the spec allows. Same annotation is always a legal
        override, so ``_mark_unsafe_overrides`` leaves the re-declaration unflagged.
        """
        own = {f.wire_name for f in model.fields}
        for wire in sorted(self._own_required.get(model.name, set())):
            base_field = inherited.get(wire)
            if wire in own or base_field is None or base_field.required:
                continue
            model.fields.append(
                replace(
                    base_field,
                    required=True,
                    default=None,
                    has_default=False,
                    omittable=False,
                    constraints=dict(base_field.constraints),
                    # Judged against *this* model's base chain, not the one the copied
                    # field was flagged for; ``_mark_unsafe_overrides`` runs next.
                    incompatible_override=False,
                )
            )

    @staticmethod
    def _retype_discriminator_tag(
        model: IRModel, inherited: dict[str, IRField], by_name: dict[str, Declaration]
    ) -> None:
        """Pin an enum-typed discriminator tag as the enum member instead of a Literal.

        The idiomatic OpenAPI form types the discriminator property as a ``$ref`` to an
        enum. ``Literal['callback']`` is not assignable to ``ButtonKind``, so the tag
        used to be dropped as an unsound override and the subtype ended up with no
        pinned tag at all: constructible with any sibling's tag, and encoded without one
        unless the caller remembered to pass it. Re-typing it to the enum the base
        declares keeps the annotation identical, so it survives as a legal override that
        changes only the default.
        """
        for f in model.fields:
            if not (isinstance(f.type, LiteralType) and len(f.type.values) == 1 and f.has_default):
                continue
            base_field = inherited.get(f.wire_name)
            if base_field is None:
                continue
            declared = base_field.type
            target = declared.inner if isinstance(declared, OptionalType) else declared
            if not isinstance(target, RefType):
                continue
            enum_decl = by_name.get(target.name)
            if not isinstance(enum_decl, IREnum):
                continue
            member = next((m for m, value in enum_decl.members if value == f.default), None)
            if member is None:
                continue
            # The base's own annotation, not ``Literal[Kind.A]``. The literal form
            # would be tighter -- it rejects a sibling's tag and keeps pydantic's
            # tagged-union wiring, which needs a ``Literal`` -- but msgspec refuses to
            # build a struct from ``Literal[<StrEnum member>]`` ("Literal may only
            # contain None/integers/strings"), and the IR is shared by all three
            # serializers. So the subtype pins the member and stays constructible with
            # a sibling's tag; that is the narrower gap of the two.
            f.type = declared
            f.default_expr = f"{enum_decl.name}.{member}"

    @staticmethod
    def _inherited_fields(by_name: dict[str, Declaration], base: str) -> dict[str, IRField]:
        """Every field visible on ``base``, keyed by wire name (nearest declaration wins).

        Walks the whole chain: a subclass carries only its own fields, so a grandparent's
        declaration is invisible from the direct parent alone.
        """
        chain: list[IRModel] = []
        seen: set[str] = set()
        current: str | None = base
        while current is not None and current not in seen:
            seen.add(current)
            parent = by_name.get(current)
            if not isinstance(parent, IRModel):
                break
            chain.append(parent)
            current = parent.base_model
        fields: dict[str, IRField] = {}
        for parent in reversed(chain):  # root first, so the nearest declaration wins
            for f in parent.fields:
                fields[f.wire_name] = f
        return fields

    def _build_servers(self) -> list[Server]:
        raw = self._spec.get("servers") or []
        servers: list[Server] = []
        for entry in raw:
            if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                servers.append(Server(url=entry["url"], description=entry.get("description")))
        return servers

    @staticmethod
    def _select_base_url(servers: list[Server]) -> str | None:
        if not servers:
            return None
        for server in servers:
            if "prod" in (server.description or "").lower():
                return server.url
        return servers[0].url

    @staticmethod
    def _shared_base_path(servers: list[Server]) -> str:
        """The path component shared by every server, or "" if none/disagree.

        That shared prefix is what gets folded into operation urls.
        """
        if not servers:
            return ""
        paths = {urlsplit(server.url).path.rstrip("/") for server in servers}
        if len(paths) != 1:
            return ""
        return next(iter(paths))

    @staticmethod
    def _origin(url: str) -> str:
        """Scheme + host of a URL, or "" for a host-less (relative) server."""
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
        return ""

    # -- deref helpers ---------------------------------------------------------

    def _deref(self, node: Any, base_uri: str) -> tuple[Any, str]:
        if isinstance(node, dict) and isinstance(node.get("$ref"), str):
            resolved = self._resolver.resolve_ref(node["$ref"], base_uri)
            return resolved.value, resolved.base_uri
        return node, base_uri

    # -- components ------------------------------------------------------------

    def _build_components(self) -> None:
        schemas = self._spec.get("components", {}).get("schemas", {})
        for name in schemas:
            self._convert_ref(f"#/components/schemas/{name}", self._root_uri, name)

    def _resolve_strip_segments(self, strip_prefix: str | None) -> list[str]:
        """Dotted-segment prefix to drop from component schema names (or [])."""
        if not strip_prefix:
            return []
        if strip_prefix == "auto":
            names = list(self._spec.get("components", {}).get("schemas", {}))
            return self._common_segment_prefix(names)
        return [s for s in strip_prefix.split(".") if s]

    @staticmethod
    def _common_segment_prefix(names: list[str]) -> list[str]:
        seg_lists = [n.split(".") for n in names if "." in n]
        if len(seg_lists) < 2:
            return []
        common: list[str] = []
        for column in zip(*seg_lists, strict=False):
            if len(set(column)) == 1:
                common.append(column[0])
            else:
                break
        # never strip a name down to nothing (keep its final segment)
        return common[: min(len(s) for s in seg_lists) - 1]

    def _strip_name_prefix(self, name: str) -> str:
        n = len(self._strip_segments)
        if not n:
            return name
        segs = name.split(".")
        if len(segs) > n and segs[:n] == self._strip_segments:
            return ".".join(segs[n:])
        return name

    def _convert_ref(self, ref: str, base_uri: str, hint: str) -> IRType:
        resolved = self._resolver.resolve_ref(ref, base_uri)
        key = (resolved.base_uri, resolved.pointer)
        if key in self._ref_to_name:
            return RefType(self._ref_to_name[key])
        source = self._strip_name_prefix(resolved.name) if resolved.name else None
        preferred = class_name(source or hint)
        name = self._names.reserve(preferred)
        self._ref_to_name[key] = name
        self._build_named(
            name, resolved.value, resolved.base_uri, is_disc_subtype=key in self._disc_subtype
        )
        self._apply_discriminator_tag(key, name)
        return RefType(name)

    @staticmethod
    def _mapping_ref(target: Any) -> str | None:
        """A discriminator mapping value: a $ref string, a {"$ref": ...} object, or a bare name."""
        ref = target.get("$ref") if isinstance(target, dict) else target
        if not isinstance(ref, str):
            return None
        if "/" not in ref and "#" not in ref:  # bare schema name
            return f"#/components/schemas/{ref}"
        return ref

    def _collect_discriminator_subtypes(self) -> None:
        """Pre-scan: record each mapped subtype's discriminator property + tag value."""
        schemas = self._spec.get("components", {}).get("schemas", {})
        for schema in schemas.values():
            disc = schema.get("discriminator") if isinstance(schema, dict) else None
            if not isinstance(disc, dict) or not isinstance(disc.get("mapping"), dict):
                continue
            prop = disc.get("propertyName")
            if not isinstance(prop, str):
                continue
            for value, target in disc["mapping"].items():
                ref = self._mapping_ref(target)
                if ref is None:
                    continue
                resolved = self._resolver.resolve_ref(ref, self._root_uri)
                self._disc_subtype[(resolved.base_uri, resolved.pointer)] = (prop, value)

    def _apply_discriminator_tag(self, key: tuple[str, str], name: str) -> None:
        """Pin a discriminated subtype's tag field to a single-value Literal (its tag)."""
        if key not in self._disc_subtype:
            return
        decl = self._declarations.get(name)
        if not isinstance(decl, IRModel):
            return
        prop, value = self._disc_subtype[key]
        for f in decl.fields:
            if f.wire_name == prop:
                f.type = LiteralType((value,))
                f.has_default = True
                f.default = value
                f.omittable = False
                return
        if decl.base_model is None:
            # No base class to have taken the property: the subtype simply does not
            # declare the tag, which the *default* mode has always rendered the same
            # way. Synthesizing one here would invent a field no schema declares and
            # would change the output of every existing merge-mode user, so the gap
            # is left as it is in both modes.
            return
        # Inheritance mode: the tag property is declared by the base class, so the
        # subtype re-declares it pinned to its own tag. The python name has to be
        # reserved against the fields already on this model: a sibling property whose
        # wire name only differs in case (``Type`` vs ``type``) snake-cases to the same
        # identifier, and two identically named class attributes would silently
        # collapse into one -- destroying the tag.
        used = NameRegistry()
        for existing in decl.fields:
            used.reserve(existing.name)
        decl.fields.insert(
            0,
            IRField(
                name=used.reserve(field_name(prop)),
                wire_name=prop,
                type=LiteralType((value,)),
                required=True,
                default=value,
                has_default=True,
            ),
        )

    def _build_named(
        self, name: str, schema: Any, base_uri: str, *, is_disc_subtype: bool = False
    ) -> None:
        if not isinstance(schema, dict):
            self._declarations[name] = IRAlias(name=name, target=ANY)
            return
        description = schema.get("description")
        if "enum" in schema and "properties" not in schema:
            self._declarations[name] = self._build_enum(name, schema)
            return
        disc_raw = schema.get("discriminator")
        if isinstance(disc_raw, dict) and isinstance(disc_raw.get("mapping"), dict):
            # ``_has_own_structure`` is the load-bearing guard: only a base that
            # declares its own fields can *be* a class. The common OpenAPI idiom puts
            # the discriminator on a bare ``oneOf`` holder with no properties of its
            # own -- turning that into a class would emit an empty ``class Base: pass``
            # and silently swallow every payload annotated with it, so it stays a union
            # alias even in inheritance mode.
            if self._inheritance and self._has_own_structure(schema):
                # The base keeps its own properties and stays a class; subtypes
                # inherit from it instead of being folded into a union alias. It is
                # declared *before* they are converted, so their own `_build_object`
                # can see that their base resolves to a model.
                model = self._build_object(name, schema, base_uri)
                self._declarations[name] = model
                self._convert_mapped_subtypes(disc_raw["mapping"], base_uri, name)
                # Re-resolve now that every mapped subtype has a class name.
                model.discriminator = self._discriminator(schema, base_uri)
                return
            self._build_discriminated_base(name, schema, base_uri, description)
            return
        # A discriminator subtype (``allOf: [{$ref: base}, ...]``) is always a concrete
        # model — never collapse a marker subtype (`allOf: [{$ref: base}]`) to its base,
        # or the base union would reference itself.
        if is_disc_subtype and "allOf" in schema:
            self._declarations[name] = self._build_object(name, schema, base_uri)
            return
        if self._is_object(schema):
            self._declarations[name] = self._build_object(name, schema, base_uri)
            return
        for union_key in ("oneOf", "anyOf"):
            if union_key in schema:
                target = self._convert_union(schema[union_key], base_uri, name)
                disc = self._discriminator(schema, base_uri)
                self._declarations[name] = IRAlias(
                    name=name, target=target, description=description, discriminator=disc
                )
                return
        target = self._convert(schema, base_uri, name)
        self._declarations[name] = IRAlias(name=name, target=target, description=description)

    def _convert_mapped_subtypes(
        self, mapping: dict[str, Any], base_uri: str, hint: str
    ) -> list[IRType]:
        """Convert every subtype named in a discriminator ``mapping``, in mapping order.

        Shared by both discriminated-base strategies. In union mode the results are the
        union members; in inheritance mode they are discarded and this runs purely for
        its side effect -- without the union alias nothing else pulls a subtype in, so
        an unreferenced variant would silently vanish from the output. Either way the
        conversion also populates ``_ref_to_name`` so ``_discriminator`` can resolve the
        mapping to generated class names.
        """
        return [
            self._convert_ref(ref, base_uri, hint)
            for target in mapping.values()
            if (ref := self._mapping_ref(target)) is not None
        ]

    def _build_discriminated_base(
        self, name: str, schema: dict[str, Any], base_uri: str, description: str | None
    ) -> None:
        """A base type with a discriminator ``mapping`` is the union of its subtypes."""
        mapping = schema["discriminator"]["mapping"]
        members: list[IRType] = []
        seen: set[str] = set()
        for ir in self._convert_mapped_subtypes(mapping, base_uri, name):
            anno = ir.annotation()
            if anno not in seen:
                seen.add(anno)
                members.append(ir)
        if not members:
            self._declarations[name] = self._build_object(name, schema, base_uri)
            return
        target_type: IRType = members[0] if len(members) == 1 else UnionType(tuple(members))
        self._declarations[name] = IRAlias(
            name=name,
            target=target_type,
            description=description,
            discriminator=self._discriminator(schema, base_uri),
        )

    # -- schema -> IRType ------------------------------------------------------

    @staticmethod
    def _singleton_allof_ref(schema: dict[str, Any]) -> str | None:
        """A ``$ref`` wrapped in a one-member ``allOf`` (the 3.0 "describe a $ref" idiom).

        ``{"description": "...", "allOf": [{"$ref": "#/.../X"}]}`` means *just X* (plus
        metadata); it must resolve to X, not become an empty merged object. Only when the
        wrapper adds no real structure of its own.
        """
        allof = schema.get("allOf")
        if not (isinstance(allof, list) and len(allof) == 1):
            return None
        member = allof[0]
        if not isinstance(member, dict):
            return None
        ref = member.get("$ref")
        if not isinstance(ref, str):
            return None
        if any(k in schema for k in ("properties", "additionalProperties", "oneOf", "anyOf")):
            return None
        return ref

    @staticmethod
    def _is_object(schema: dict[str, Any]) -> bool:
        # An object is only worth a model class if it has structure. A bare
        # ``type: object`` (or ``{}``) with no properties/allOf/additionalProperties
        # is a free-form mapping (``dict[str, Any]``), not an empty class.
        if IRBuilder._singleton_allof_ref(schema) is not None:
            return False
        return "properties" in schema or "allOf" in schema

    @staticmethod
    def _has_own_structure(schema: dict[str, Any]) -> bool:
        """Whether the schema declares fields of its own, not merely the *keys* for them.

        Stricter than ``_is_object`` on purpose. Key presence is the right test for
        "model class vs ``dict[str, Any]``", but not for "may this be a base class":
        plenty of generators emit a bare discriminator holder as ``properties: {}``,
        which passes ``_is_object`` and would become an empty ``class Base: pass``
        that every payload annotated with it decodes into, losing all of its fields.
        """
        return IRBuilder._is_object(schema) and (
            bool(schema.get("properties")) or bool(schema.get("allOf"))
        )

    @staticmethod
    def _split_nullable(schema: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        nullable = False
        new = schema
        typ = schema.get("type")
        if isinstance(typ, list) and "null" in typ:  # 3.1 form
            rest = [t for t in typ if t != "null"]
            new = dict(schema)
            new["type"] = rest[0] if len(rest) == 1 else rest
            nullable = True
        if schema.get("nullable") is True:  # 3.0 form
            if new is schema:
                new = dict(schema)
            new.pop("nullable", None)
            nullable = True
        return new, nullable

    def _convert(self, schema: Any, base_uri: str, hint: str) -> IRType:
        if isinstance(schema, bool):
            return ANY
        if not isinstance(schema, dict):
            return ANY
        if isinstance(schema.get("$ref"), str):
            return self._convert_ref(schema["$ref"], base_uri, hint)
        schema, nullable = self._split_nullable(schema)
        result = self._convert_nonnull(schema, base_uri, hint)
        return optional(result) if nullable else result

    def _convert_nonnull(self, schema: dict[str, Any], base_uri: str, hint: str) -> IRType:
        if "const" in schema:
            value = schema["const"]
            if isinstance(value, (str, int, bool)):
                return LiteralType((value,))
            return ANY
        if "enum" in schema:
            values = tuple(v for v in schema["enum"] if v is not None)
            if values and all(isinstance(v, (str, int, bool)) for v in values):
                return LiteralType(values)
            return ANY
        singleton_ref = self._singleton_allof_ref(schema)
        if singleton_ref is not None:
            return self._convert_ref(singleton_ref, base_uri, hint)
        if "allOf" in schema or self._is_object(schema):
            return self._build_anonymous_object(schema, base_uri, hint)
        for union_key in ("oneOf", "anyOf"):
            if union_key in schema:
                return self._convert_union(schema[union_key], base_uri, hint)
        typ = schema.get("type")
        if typ == "array" or "items" in schema:
            items = schema.get("items", True)
            return ListType(self._convert(items, base_uri, hint + "Item"))
        if typ == "object" or "additionalProperties" in schema:
            ap = schema.get("additionalProperties")
            if ap in (None, True):
                return MappingType(ANY)
            if ap is False:
                return MappingType(ANY)
            return MappingType(self._convert(ap, base_uri, hint + "Value"))
        return self._scalar_type(schema)

    @staticmethod
    def _scalar_type(schema: dict[str, Any]) -> IRType:
        typ = schema.get("type")
        if isinstance(typ, list):
            typ = next((t for t in typ if t != "null"), None)
        if typ == "string":
            return _STRING_FORMATS.get(schema.get("format", ""), STR)
        if typ == "integer":
            return INT
        if typ == "number":
            return FLOAT
        if typ == "boolean":
            return BOOL
        return ANY

    def _convert_union(self, members: list[Any], base_uri: str, hint: str) -> IRType:
        converted: list[IRType] = []
        seen: set[str] = set()
        nullable = False
        for index, member in enumerate(members):
            if isinstance(member, dict) and member.get("type") == "null":
                nullable = True
                continue
            ir = self._convert(member, base_uri, f"{hint}Variant{index + 1}")
            anno = ir.annotation()
            if anno not in seen:
                seen.add(anno)
                converted.append(ir)
        result: IRType = converted[0] if len(converted) == 1 else UnionType(tuple(converted))
        return optional(result) if nullable else result

    def _discriminator(self, schema: dict[str, Any], base_uri: str) -> Discriminator | None:
        disc = schema.get("discriminator")
        if not isinstance(disc, dict) or "propertyName" not in disc:
            return None
        mapping: dict[str, str] = {}
        for value, target in (disc.get("mapping") or {}).items():
            # mapping values are normally a ref string or bare schema name, but some
            # generators emit a ``{"$ref": "..."}`` object — accept both.
            ref = target.get("$ref") if isinstance(target, dict) else target
            if not isinstance(ref, str):
                continue
            if "/" not in ref and "#" not in ref:  # bare schema name
                ref = f"#/components/schemas/{ref}"
            resolved = self._resolver.resolve_ref(ref, base_uri)
            key = (resolved.base_uri, resolved.pointer)
            if key in self._ref_to_name:
                mapping[value] = self._ref_to_name[key]
        return Discriminator(property_name=disc["propertyName"], mapping=mapping)

    # -- object models ---------------------------------------------------------

    def _build_anonymous_object(self, schema: dict[str, Any], base_uri: str, hint: str) -> IRType:
        name = self._names.reserve(class_name(hint))
        self._declarations[name] = self._build_object(name, schema, base_uri)
        return RefType(name)

    def _flatten_object(
        self,
        schema: dict[str, Any],
        base_uri: str,
        *,
        inherited: dict[str, Any] | None = None,
        _chain: frozenset[int] = frozenset(),
    ) -> tuple[dict[str, tuple[Any, str]], set[str], Any, Discriminator | None]:
        """Merge an ``allOf`` chain into one property set.

        ``inherited`` is the single ``allOf`` member the caller already turned into a
        real base class (inheritance mode); its properties stay on the base instead of
        being copied down. It is passed in rather than recomputed so the caller's
        decision and this merge can never disagree.

        A discriminator is never merged in from an ``allOf`` member: it belongs to the
        schema that declares it, and copying it down makes every subtype look like a
        tagged-union base of the whole family (which the renderer then announces in a
        ``# discriminator:`` header above a concrete class).

        ``_chain`` carries the schemas already open on the current ``allOf`` path. A
        spec whose chain loops back on itself (``X: allOf [Y]``, ``Y: allOf [X]``)
        describes an infinitely deep object, and without the guard the walk recurses
        until the interpreter's stack gives out. The repeated member is skipped
        instead, leaving the inheritance edge for ``_ordered_declarations`` to break.
        Identity is the key: every schema stays alive in the resolver's documents for
        the whole build, and the same pointer always derefs to the same object.
        """
        properties: dict[str, tuple[Any, str]] = {}
        required: set[str] = set()
        additional: Any = None
        discriminator = self._discriminator(schema, base_uri)
        chain = _chain | {id(schema)}
        for sub in schema.get("allOf", []):
            sub_schema, sub_base = self._deref(sub, base_uri)
            if not isinstance(sub_schema, dict):
                continue
            if id(sub_schema) in chain:
                logger.warning(
                    "allOf chain loops back on %s; skipping the repeated member",
                    sub.get("$ref") if isinstance(sub, dict) else "an inline schema",
                )
                continue
            p, r, a, _ = self._flatten_object(sub_schema, sub_base, _chain=chain)
            if sub is not inherited:
                properties.update(p)
                if a is not None:
                    additional = a
            # A base's ``required`` still applies to any property the subtype
            # re-declares (specs routinely restate one only to add a description),
            # so it is merged even when the properties themselves stay on the base.
            required |= r
        for prop_name, prop_schema in schema.get("properties", {}).items():
            properties[prop_name] = (prop_schema, base_uri)
        required |= set(schema.get("required", []))
        if "additionalProperties" in schema:
            additional = schema["additionalProperties"]
        return properties, required, additional, discriminator

    @staticmethod
    def _inherited_ref(schema: dict[str, Any]) -> dict[str, Any] | None:
        """The single ``allOf`` member that should become a real base class, if any.

        Only an unambiguous ``allOf`` with exactly one ``$ref`` maps onto Python
        inheritance. With several refs (mixin-style composition) there is no single
        parent to pick, so those keep the merge behaviour.
        """
        allof = schema.get("allOf")
        if not isinstance(allof, list):
            return None
        refs = [
            member
            for member in allof
            if isinstance(member, dict) and isinstance(member.get("$ref"), str)
        ]
        return refs[0] if len(refs) == 1 else None

    def _resolve_base_model(
        self, inherited: dict[str, Any], base_uri: str, hint: str
    ) -> str | None:
        """Generated class name to subclass for an ``allOf`` ref, or None to merge.

        Only a model can be subclassed, so a ref to an enum/alias/scalar keeps the merge
        behaviour. The check cannot go through ``self._declarations``: a base whose own
        body refers back to this subtype (a recursive hierarchy) is still mid-build and
        has no entry yet, which would silently downgrade the subtype to a merge based on
        nothing but graph traversal order. Decide from the *schema* instead, using the
        same predicate ``_build_named`` will apply when it declares the base.
        """
        base_type = self._convert_ref(inherited["$ref"], base_uri, hint)
        # ``_convert_ref`` names every target it resolves, so this is an invariant
        # rather than a case to degrade on -- a ``return None`` here would be a branch
        # no spec can reach.
        assert isinstance(base_type, RefType)
        declared = self._declarations.get(base_type.name)
        if declared is not None:
            return base_type.name if isinstance(declared, IRModel) else None
        resolved = self._resolver.resolve_ref(inherited["$ref"], base_uri)
        key = (resolved.base_uri, resolved.pointer)
        will_be_model = self._declares_model(
            resolved.value, is_disc_subtype=key in self._disc_subtype
        )
        return base_type.name if will_be_model else None

    def _declares_model(self, schema: Any, *, is_disc_subtype: bool = False) -> bool:
        """Whether ``_build_named`` will declare ``schema`` as an ``IRModel``.

        Mirrors the dispatch in ``_build_named``; kept next to nothing else so the two
        stay reviewable side by side.
        """
        if not isinstance(schema, dict):
            return False
        if "enum" in schema and "properties" not in schema:
            return False
        disc = schema.get("discriminator")
        if isinstance(disc, dict) and isinstance(disc.get("mapping"), dict):
            return self._inheritance and self._has_own_structure(schema)
        if is_disc_subtype and "allOf" in schema:
            return True
        return self._is_object(schema)

    def _build_object(self, name: str, schema: dict[str, Any], base_uri: str) -> IRModel:
        base: str | None = None
        inherited = self._inherited_ref(schema) if self._inheritance else None
        if inherited is not None:
            base = self._resolve_base_model(inherited, base_uri, name)
        properties, required, additional, discriminator = self._flatten_object(
            schema, base_uri, inherited=inherited if base is not None else None
        )
        model = IRModel(
            name=name,
            description=schema.get("description"),
            discriminator=discriminator,
            base_model=base,
        )
        field_names = NameRegistry()
        for prop_name, (prop_schema, prop_base) in properties.items():
            f = self._build_field(name, prop_name, prop_schema, prop_base, prop_name in required)
            f.name = field_names.reserve(f.name)  # distinct wire names can collapse (e.g. +1/-1)
            model.fields.append(f)
        # Overrides are reconciled against the full base chain once the graph is
        # complete; see ``_reconcile_inheritance``. ``required`` has to be carried
        # over separately: a subtype that only tightens an inherited property names it
        # here and contributes no property of its own.
        if self._inheritance:
            self._own_required[name] = set(required)
        if isinstance(additional, dict):
            model.additional_properties = self._convert(additional, base_uri, name + "Value")
        elif additional is True:
            model.additional_properties = ANY
        return model

    def _mark_unsafe_overrides(
        self,
        model: IRModel,
        inherited: dict[str, IRField],
        by_name: dict[str, Declaration],
    ) -> None:
        """Flag re-declared inherited fields whose type the base does not admit.

        Every property a subtype declares stays on the subtype, so the flag records
        only that the spec asked for something ``class Sub(Base)`` cannot express
        soundly; the serializers decide what to emit for it.

        A spec that does this is inconsistent -- the subtype is not substitutable for
        its base -- and that is worth fixing in the spec rather than in its clients, so
        every occurrence is logged with the schema and property it comes from.
        """
        for f in model.fields:
            base_field = inherited.get(f.wire_name)
            # Always assigned, never only set: ``_restore_required_narrowing`` copies
            # fields down from the base chain, flag and all, and the copy is judged
            # against a different base than the original was.
            f.incompatible_override = False
            if base_field is None:
                continue
            if f.type.annotation() == base_field.type.annotation() or self._is_narrowing(
                f.type, base_field.type, by_name
            ):
                continue
            f.incompatible_override = True
            logger.warning(
                "%s re-declares %r as %s, which the inherited %s does not admit; "
                "the subtype is not substitutable for its base -- fix the schema",
                model.name,
                f.wire_name,
                f.type.annotation(),
                base_field.type.annotation(),
            )

    @staticmethod
    def _rename_shadowed_fields(model: IRModel, inherited: dict[str, IRField]) -> None:
        """Rename an own field whose python name is already taken by a *different* one.

        Two wire names can snake-case onto one identifier (``packSize`` on the base,
        ``pack_size`` on the subtype). The subclass attribute would then shadow the
        inherited one with an unrelated type -- an ``[assignment]`` error under
        ``mypy --strict``, and the base's value unreachable. Only a re-declaration of
        the *same* wire name may keep the name: that one is a genuine override.
        """
        taken = {f.name: f.wire_name for f in inherited.values()}
        shadowed = [f for f in model.fields if taken.get(f.name, f.wire_name) != f.wire_name]
        if not shadowed:
            return
        renaming = {id(f) for f in shadowed}
        registry = NameRegistry()
        for f in model.fields:
            if id(f) not in renaming:
                registry.reserve(f.name)
        for name in taken:
            if name not in registry:
                registry.reserve(name)
        for f in shadowed:
            f.name = registry.reserve(f.name)

    @staticmethod
    def _align_override_names(model: IRModel, inherited: dict[str, IRField]) -> None:
        """Put a re-declared wire name on the attribute its base already uses.

        A subtype re-declares an inherited wire name in order to *override* it, but the
        python name is derived independently and a sibling can get there first (the tag
        for wire ``type`` landing on ``type2`` because a ``Type`` property took ``type``).
        The result is two attributes for one wire key: adaptix refuses to build the
        retort ("fields point to the same path"), and the base's declaration stays live
        underneath. Runs after ``_rename_shadowed_fields`` has freed the name.
        """
        for f in model.fields:
            base_field = inherited.get(f.wire_name)
            if base_field is not None:
                f.name = base_field.name

    @classmethod
    def _is_narrowing(
        cls, sub: IRType, base: IRType, by_name: Mapping[str, Declaration] | None = None
    ) -> bool:
        """Whether ``sub`` is safe to re-declare over an inherited ``base`` annotation.

        Only says yes for shapes that are provably assignable, and a no is answered by
        emitting the declaration under a suppression comment rather than by dropping
        it -- so a false no costs a line of noise in the output, not a lost property.
        The suppression carries ``unused-ignore`` for exactly that reason.

        ``by_name`` resolves ``$ref`` narrowings: ``Dog`` over ``Animal`` is assignable
        only if the generated ``Dog`` really does subclass ``Animal``, which nothing in
        either annotation says. Omitting it just makes those answer no.
        """
        if sub.annotation() == base.annotation():
            return False  # a pure restatement: nothing to gain, just inherit it
        if isinstance(base, PrimitiveType) and base.py == "Any":
            return True
        if isinstance(sub, PrimitiveType) and isinstance(base, PrimitiveType):
            return (sub.py, base.py) in _PROMOTIONS
        if isinstance(sub, RefType) and isinstance(base, RefType):
            return cls._extends(sub.name, base.name, by_name)
        if isinstance(sub, OptionalType) and isinstance(base, OptionalType):
            # ``T | None`` narrows ``U | None`` exactly when ``T`` narrows ``U``.
            return cls._is_narrowing(sub.inner, base.inner, by_name)
        if isinstance(base, OptionalType):
            # ``T | None`` admits ``T`` and anything that narrows ``T``.
            return sub.annotation() == base.inner.annotation() or cls._is_narrowing(
                sub, base.inner, by_name
            )
        if isinstance(sub, OptionalType):
            return False  # adding None to a non-optional base widens it
        if isinstance(sub, LiteralType):
            # The discriminator-tag case: Literal["a"] over a str/int base, or over a
            # wider Literal that already admits every value.
            if isinstance(base, LiteralType):
                return set(sub.values) <= set(base.values)
            # The values' own python types have to match too: ``Literal['one', 'two']``
            # over an ``int`` base is an ``[assignment]`` error under ``mypy --strict``,
            # and the base being *some* scalar says nothing about which one.
            return isinstance(base, PrimitiveType) and cls._literals_fit(sub.values, base.py)
        if isinstance(base, UnionType):
            return any(
                cls._is_narrowing(sub, m, by_name) or sub.annotation() == m.annotation()
                for m in base.members
            )
        # Containers land here: ``list``/``dict`` are invariant, so a narrowed element
        # type is not a narrowed container.
        return False

    @staticmethod
    def _extends(sub: str, base: str, by_name: Mapping[str, Declaration] | None) -> bool:
        """Whether the model named ``sub`` inherits from ``base``, however deep."""
        if by_name is None:
            return False
        seen: set[str] = set()
        current: str | None = sub
        while current is not None and current not in seen:
            seen.add(current)
            decl = by_name.get(current)
            if not isinstance(decl, IRModel):
                return False
            if decl.base_model == base:
                return True
            current = decl.base_model
        return False

    @staticmethod
    def _literals_fit(values: tuple[str | int | bool, ...], py: str) -> bool:
        """Whether every literal value is an instance of the base's primitive type."""
        if py == "bool":
            return all(isinstance(v, bool) for v in values)
        if py == "int":
            # ``bool`` is a subtype of ``int``: ``Literal[True]`` is assignable to it.
            return all(isinstance(v, int) for v in values)
        if py == "str":
            return all(isinstance(v, str) for v in values)
        return False

    @staticmethod
    def _default_assignable(default: Any, ftype: IRType) -> bool:
        """Whether ``default`` can be written as a Python literal of ``ftype``."""
        t = ftype.inner if isinstance(ftype, OptionalType) else ftype
        if default is None:
            return isinstance(ftype, OptionalType)
        if isinstance(t, UnionType):
            return any(IRBuilder._default_assignable(default, m) for m in t.members)
        if isinstance(t, LiteralType):
            return default in t.values
        if isinstance(t, PrimitiveType):
            if t.py == "Any":
                return True
            if t.py == "bool":
                return isinstance(default, bool)
            if t.py == "int":
                return isinstance(default, int) and not isinstance(default, bool)
            if t.py == "float":
                return isinstance(default, (int, float)) and not isinstance(default, bool)
            if t.py == "str":
                return isinstance(default, str)
            return False  # bytes/datetime/uuid/decimal: a bare literal default is unusual
        if isinstance(t, ListType):
            # Only assignable when the element type is a plain primitive; a literal
            # default like ``["audio"]`` is inferred as ``list[str]`` and would not be
            # assignable to e.g. ``list[Literal["text", "audio"]]``.
            return isinstance(default, list) and IRBuilder._is_plain_primitive(t.item)
        if isinstance(t, MappingType):
            return isinstance(default, dict) and IRBuilder._is_plain_primitive(t.value)
        return False  # RefType (model/enum), UploadFile, ...

    @staticmethod
    def _is_plain_primitive(t: IRType) -> bool:
        """True for str/int/float/bool/Any — element types a literal container admits."""
        return isinstance(t, PrimitiveType) and t.py in ("str", "int", "float", "bool", "Any")

    @staticmethod
    def _coerce_default(value: Any, schema: dict[str, Any]) -> Any:
        """Coerce a schema ``default`` to the declared type (specs often mistype it)."""
        typ = schema.get("type")
        if isinstance(typ, list):
            typ = next((t for t in typ if t != "null"), None)
        try:
            if typ == "integer" and not isinstance(value, bool):
                return int(value)
            if typ == "number" and not isinstance(value, bool):
                return float(value)
            if typ == "boolean" and isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes")
        except (ValueError, TypeError):
            return value
        return value

    @staticmethod
    def _collect_constraints(schema: dict[str, Any]) -> dict[str, Any]:
        raw = {k: schema[k] for k in _CONSTRAINT_KEYS if k in schema}
        # OpenAPI 3.0 expresses exclusive bounds as booleans paired with minimum/maximum;
        # normalize to the 3.1 numeric form so serializer constraint mapping stays uniform.
        for excl, incl in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
            value = raw.get(excl)
            if isinstance(value, bool):
                if value and incl in raw:
                    raw[excl] = raw.pop(incl)
                else:
                    raw.pop(excl, None)
        return raw

    def _build_field(
        self, owner: str, wire_name: str, schema: Any, base_uri: str, required: bool
    ) -> IRField:
        resolved_schema = schema if isinstance(schema, dict) else {}
        ftype = self._convert(schema, base_uri, owner + class_name(wire_name))
        has_default = "default" in resolved_schema
        default = self._coerce_default(resolved_schema.get("default"), resolved_schema)
        omittable = False
        if not required and not has_default:
            if self._omit_optionals:
                # leave the (possibly nullable) inner type as-is; the renderer emits
                # ``Omittable[...] = Omitted()``.
                omittable = True
            else:
                ftype = optional(ftype)
                has_default = True
                default = None
        elif has_default and not self._default_assignable(default, ftype):
            # A spec default that can't be a Python literal of this type (e.g. ``default:
            # null`` on an object, or a string default for a union/enum). Keep the field
            # optional but only carry a value the annotation actually admits.
            ftype = optional(ftype)
            if default is not None:
                default = None
        constraints = self._collect_constraints(resolved_schema)
        return IRField(
            name=field_name(wire_name),
            wire_name=wire_name,
            type=ftype,
            required=required,
            description=resolved_schema.get("description"),
            default=default,
            has_default=has_default,
            omittable=omittable,
            read_only=bool(resolved_schema.get("readOnly", False)),
            write_only=bool(resolved_schema.get("writeOnly", False)),
            constraints=constraints,
        )

    def _build_enum(self, name: str, schema: dict[str, Any]) -> IREnum:
        values = [v for v in schema["enum"] if v is not None]
        all_int = all(isinstance(v, int) and not isinstance(v, bool) for v in values)
        base = "int" if all_int else "str"
        members: list[tuple[str, Any]] = []
        used = NameRegistry()
        for value in values:
            member = used.reserve(self._enum_member_name(value))
            members.append((member, value))
        return IREnum(name=name, base=base, members=members, description=schema.get("description"))

    @staticmethod
    def _enum_member_name(value: Any) -> str:
        from unihttp_openapi_generator.ir.naming import sanitize_identifier, to_snake_case

        if isinstance(value, int):
            return f"VALUE_{value}" if value >= 0 else f"VALUE_MINUS_{abs(value)}"
        return sanitize_identifier(to_snake_case(str(value)).upper(), fallback="VALUE").upper()

    # -- operations ------------------------------------------------------------

    def _build_operations(self) -> list[IROperation]:
        operations: list[IROperation] = []
        tag_method_names: dict[str, NameRegistry] = {}
        paths = self._spec.get("paths", {})
        for path, raw_item in paths.items():
            path_item, item_base = self._deref(raw_item, self._root_uri)
            if not isinstance(path_item, dict):
                continue
            common = path_item.get("parameters", [])
            for http_method in _HTTP_METHODS:
                op_schema = path_item.get(http_method)
                if not isinstance(op_schema, dict):
                    continue
                operations.append(
                    self._build_operation(
                        path, http_method, op_schema, common, item_base, tag_method_names
                    )
                )
        return operations

    def _build_operation(
        self,
        path: str,
        http_method: str,
        op: dict[str, Any],
        common_params: list[Any],
        base_uri: str,
        tag_method_names: dict[str, NameRegistry],
    ) -> IROperation:
        operation_id = op.get("operationId") or f"{http_method}_{path}"
        cls = self._names.reserve(class_name(operation_id))
        tag = (op.get("tags") or ["default"])[0] or "default"
        registry = tag_method_names.setdefault(tag, NameRegistry())
        py_method = registry.reserve(method_name(operation_id))

        parameters = self._build_parameters(common_params, op.get("parameters", []), base_uri, cls)
        body = self._build_body(op.get("requestBody"), base_uri, cls)
        if body is not None and body.fields:
            # spread body fields share the method dataclass with the params, so a
            # body property named like a path/query param must be renamed (its wire
            # name is preserved via the alias the rename induces).
            used = NameRegistry()
            for param in parameters:
                used.reserve(param.name)
            for f in body.fields:
                f.name = used.reserve(f.name)
        success, errors = self._build_responses(op.get("responses", {}), base_uri, cls)

        return IROperation(
            operation_id=operation_id,
            class_name=cls,
            method_name=py_method,
            http_method=http_method.upper(),
            path=path,
            tag=tag,
            parameters=parameters,
            body=body,
            success=success,
            errors=errors,
            summary=op.get("summary"),
            description=op.get("description"),
            deprecated=bool(op.get("deprecated", False)),
            security=op.get("security") or [],
        )

    def _build_parameters(
        self, common: list[Any], own: list[Any], base_uri: str, hint: str
    ) -> list[IRParameter]:
        merged: dict[tuple[str, str], tuple[Any, str]] = {}
        for raw in [*common, *own]:
            param, param_base = self._deref(raw, base_uri)
            if not isinstance(param, dict) or "name" not in param:
                continue
            merged[(param["name"], param.get("in", "query"))] = (param, param_base)
        result: list[IRParameter] = []
        param_names = NameRegistry()
        for (wire_name, location), (param, param_base) in merged.items():
            schema = param.get("schema", {})
            required = bool(param.get("required", location == "path"))
            ptype = self._convert(schema, param_base, hint + class_name(wire_name))
            has_default = not required and isinstance(schema, dict) and "default" in schema
            default = self._coerce_default(schema.get("default"), schema) if has_default else None
            result.append(
                IRParameter(
                    name=param_names.reserve(field_name(wire_name)),
                    wire_name=wire_name,
                    location=ParamLocation(location),
                    type=ptype,
                    required=required,
                    description=param.get("description"),
                    style=param.get("style"),
                    explode=param.get("explode"),
                    default=default,
                    has_default=has_default,
                )
            )
        return result

    def _build_body(self, raw: Any, base_uri: str, hint: str) -> IRBody | None:
        if raw is None:
            return None
        request_body, rb_base = self._deref(raw, base_uri)
        if not isinstance(request_body, dict):
            return None
        content = request_body.get("content", {})
        required = bool(request_body.get("required", False))
        if "application/json" in content:
            schema = content["application/json"].get("schema", {})
            deref_schema, schema_base = self._deref(schema, rb_base)
            if isinstance(deref_schema, dict) and self._is_object(deref_schema):
                # unihttp's Body marker keys each body-marked field into the JSON
                # body, so an object body is spread into one Body field per
                # property (a single Body[Model] would nest the model under the
                # field name). readOnly properties are excluded by _build_body_fields.
                return IRBody(
                    kind=BodyKind.JSON,
                    required=required,
                    content_type="application/json",
                    fields=self._build_body_fields(deref_schema, schema_base, hint, BodyKind.JSON),
                )
            json_type = self._json_body_type(schema, rb_base, hint)
            return IRBody(
                kind=BodyKind.JSON,
                required=required,
                content_type="application/json",
                json_type=json_type,
            )
        for ctype, kind in (
            ("multipart/form-data", BodyKind.MULTIPART),
            ("application/x-www-form-urlencoded", BodyKind.FORM),
        ):
            if ctype in content:
                schema, schema_base = self._deref(content[ctype].get("schema", {}), rb_base)
                return IRBody(
                    kind=kind,
                    required=required,
                    content_type=ctype,
                    fields=self._build_body_fields(schema, schema_base, hint, kind),
                )
        return None

    def _build_body_fields(
        self, schema: Any, base_uri: str, hint: str, kind: BodyKind
    ) -> list[IRBodyField]:
        if not isinstance(schema, dict):
            return []
        properties, required, _, _ = self._flatten_object(schema, base_uri)
        fields: list[IRBodyField] = []
        field_names = NameRegistry()
        for wire_name, (prop_schema, prop_base) in properties.items():
            # readOnly fields are server-populated; exclude them from request bodies.
            if isinstance(prop_schema, dict) and prop_schema.get("readOnly"):
                continue
            is_file = kind is BodyKind.MULTIPART and self._is_binary(prop_schema)
            ftype: IRType = (
                UploadFileType()
                if is_file
                else self._convert(prop_schema, prop_base, hint + class_name(wire_name))
            )
            is_required = wire_name in required
            has_default = (
                not is_required and isinstance(prop_schema, dict) and "default" in prop_schema
            )
            default = (
                self._coerce_default(prop_schema.get("default"), prop_schema)
                if has_default
                else None
            )
            if has_default and not self._default_assignable(default, ftype):
                # a spec default that can't be a Python literal of this type (e.g. a
                # string default for a union of models) would not type-check; drop it
                # so the field is simply optional/omittable.
                has_default = False
                default = None
            fields.append(
                IRBodyField(
                    name=field_names.reserve(field_name(wire_name)),
                    wire_name=wire_name,
                    type=ftype,
                    required=is_required,
                    description=(
                        prop_schema.get("description") if isinstance(prop_schema, dict) else None
                    ),
                    is_file=is_file,
                    default=default,
                    has_default=has_default,
                )
            )
        return fields

    def _json_body_type(self, schema: Any, base_uri: str, hint: str) -> IRType:
        # Reached only for non-object JSON bodies (array / scalar / union); object
        # bodies are spread into individual Body fields by ``_build_body`` before
        # this is called.
        return self._convert(schema, base_uri, hint + "Body")

    @staticmethod
    def _is_binary(schema: Any) -> bool:
        return isinstance(schema, dict) and schema.get("format") == "binary"

    def _build_responses(
        self, responses: dict[str, Any], base_uri: str, hint: str
    ) -> tuple[IRResponse | None, list[IRResponse]]:
        success: IRResponse | None = None
        errors: list[IRResponse] = []
        for status in sorted(responses):
            response, resp_base = self._deref(responses[status], base_uri)
            if not isinstance(response, dict):
                continue
            schema = response.get("content", {}).get("application/json", {}).get("schema")
            rtype = (
                self._convert(schema, resp_base, hint + "Response") if schema is not None else None
            )
            ir = IRResponse(status=status, type=rtype, description=response.get("description"))
            if status.startswith("2") and success is None:
                success = ir
            elif status == "default" or status.startswith(("4", "5")):
                errors.append(ir)
        return success, errors

    # -- security --------------------------------------------------------------

    def _build_security_schemes(self) -> dict[str, SecurityScheme]:
        raw = self._spec.get("components", {}).get("securitySchemes", {})
        schemes: dict[str, SecurityScheme] = {}
        for name, definition in raw.items():
            definition, _ = self._deref(definition, self._root_uri)
            if not isinstance(definition, dict):
                continue
            schemes[name] = SecurityScheme(
                name=name,
                kind=definition.get("type", ""),
                location=definition.get("in"),
                parameter_name=definition.get("name"),
                scheme=definition.get("scheme"),
            )
        return schemes


def build_ir(
    spec: dict[str, Any],
    resolver: RefResolver,
    root_uri: str = "",
    *,
    omit_optionals: bool = False,
    strip_prefix: str | None = None,
    inheritance: bool = False,
) -> IRDocument:
    return IRBuilder(
        spec,
        resolver,
        root_uri,
        omit_optionals=omit_optionals,
        strip_prefix=strip_prefix,
        inheritance=inheritance,
    ).build()


__all__ = ["IRBuilder", "build_ir"]
