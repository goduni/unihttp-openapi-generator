"""Coverage for defensive / edge paths in the IR builder.

These specs deliberately exercise unusual-but-valid (and a few malformed-but-
tolerated) OpenAPI shapes that the normal fixtures never reach.
"""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.ir.models import IRAlias, IREnum, IRModel
from unihttp_openapi_generator.ir.types import (
    ANY,
    LiteralType,
    OptionalType,
)
from unihttp_openapi_generator.refs import RefResolver


def _decls(spec: dict[str, Any]) -> dict[str, Any]:
    doc = build_ir(spec, RefResolver(spec))
    return {d.name: d for d in doc.declarations}


def _schema_spec(schemas: dict[str, Any]) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": schemas},
    }


# --------------------------------------------------------------------------- #
# weird component schemas (schema -> IRType conversion paths)                  #
# --------------------------------------------------------------------------- #


_WEIRD_SCHEMAS: dict[str, Any] = {
    "Real": {
        "type": "object",
        "required": ["kind"],
        "properties": {"kind": {"type": "string"}, "value": {"type": "string"}},
    },
    # A component schema that is a bare boolean (not a mapping) -> IRAlias[Any].
    "NotDict": True,
    # ``{allOf: [{$ref}]}`` is just the referenced type (3.0 "describe a $ref" idiom).
    "SingletonWrapper": {"allOf": [{"$ref": "#/components/schemas/Real"}]},
    # singleton allOf whose member is not a dict -> not collapsed, treated as object.
    "WeirdAllOf": {"allOf": [True]},
    # singleton allOf whose member is a dict without a ``$ref`` -> treated as object.
    "AllOfNoRef": {"allOf": [{"type": "object", "properties": {"x": {"type": "string"}}}]},
    # singleton ``$ref`` allOf that also carries its own ``properties`` -> not collapsed.
    "AllOfRefPlusProps": {
        "allOf": [{"$ref": "#/components/schemas/Real"}],
        "properties": {"extra": {"type": "string"}},
    },
    # allOf member contributing only ``additionalProperties``.
    "AllOfAdditional": {
        "allOf": [
            {"type": "object", "additionalProperties": {"type": "string"}},
            {"type": "object", "properties": {"x": {"type": "string"}}},
        ]
    },
    # object with both properties and ``additionalProperties: true``.
    "ApTrue": {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "additionalProperties": True,
    },
    "Kitchen": {
        "type": "object",
        "properties": {
            "const_float": {"const": 1.5},
            "empty_enum": {"enum": [None]},
            "nested_obj": {"type": "object", "properties": {"a": {"type": "string"}}},
            "ap_false": {"type": "object", "additionalProperties": False},
            "multitype": {"type": ["string", "integer"]},
            "null_prop": None,
            "arr_no_items": {"type": "array"},
            "union_null": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "enum_default": {"enum": ["a", "b"], "default": "a"},
            "any_default": {"default": "hello"},
            "date_default": {"type": "string", "format": "date", "default": "2020-01-01"},
            "map_default": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "default": {"k": "v"},
            },
            "excl_bool": {"type": "integer", "minimum": 0, "exclusiveMinimum": False},
        },
    },
    # discriminator with a non-string propertyName (pre-scan skips it).
    "DiscBadProp": {
        "discriminator": {"mapping": {"a": "#/components/schemas/Real"}, "propertyName": 123},
    },
    # discriminator whose mapping values are all non-refs -> falls back to an object.
    "DiscNoRefs": {"discriminator": {"propertyName": "kind", "mapping": {"a": 123, "b": 456}}},
    # discriminator mapping mixing a valid ref with a junk value.
    "DiscMixed": {
        "discriminator": {
            "propertyName": "kind",
            "mapping": {"good": "#/components/schemas/Real", "bad": 123},
        }
    },
    # discriminator whose mapped subtype is an enum (a non-model declaration).
    "DiscEnumBase": {
        "discriminator": {"propertyName": "kind", "mapping": {"e": "#/components/schemas/EnumSub"}}
    },
    "EnumSub": {"type": "string", "enum": ["x", "y"]},
    # negative-valued integer enum -> VALUE_MINUS_N members.
    "IntEnumNeg": {"type": "integer", "enum": [-1, 0, 5]},
}


def test_weird_component_schemas_build() -> None:
    decls = _decls(_schema_spec(_WEIRD_SCHEMAS))

    # bare-boolean schema -> alias to Any
    not_dict = decls["NotDict"]
    assert isinstance(not_dict, IRAlias)
    assert not_dict.target is ANY

    # singleton allOf ref collapses to the referenced model
    wrapper = decls["SingletonWrapper"]
    assert isinstance(wrapper, IRAlias)
    assert wrapper.target.annotation() == "Real"

    # non-dict allOf member is skipped during flattening
    assert isinstance(decls["WeirdAllOf"], IRModel)
    assert isinstance(decls["AllOfNoRef"], IRModel)
    assert isinstance(decls["AllOfRefPlusProps"], IRModel)

    # allOf-contributed additionalProperties surfaces on the model
    add = decls["AllOfAdditional"]
    assert isinstance(add, IRModel)
    assert add.additional_properties is not None
    assert add.additional_properties.annotation() == "str"

    ap_true = decls["ApTrue"]
    assert isinstance(ap_true, IRModel)
    assert ap_true.additional_properties is ANY

    kitchen = decls["Kitchen"]
    assert isinstance(kitchen, IRModel)
    fields = {f.wire_name: f for f in kitchen.fields}
    # const with a non-scalar value and an empty enum both fall back to Any
    assert fields["const_float"].type.annotation() == "Any | None"
    assert fields["empty_enum"].type.annotation() == "Any | None"
    # multi-type scalar collapses to the first non-null member
    assert "str" in fields["multitype"].type.annotation()
    # array without items -> list[Any]
    assert "list[Any]" in fields["arr_no_items"].type.annotation()
    # a literal-typed field keeps an assignable default
    assert fields["enum_default"].default == "a"
    assert isinstance(fields["enum_default"].type, LiteralType)
    # an Any-typed field keeps its default
    assert fields["any_default"].default == "hello"
    # a date field's bare-string default is not Python-assignable -> dropped/optional
    assert isinstance(fields["date_default"].type, OptionalType)
    assert fields["date_default"].default is None
    # a mapping field keeps a dict default
    assert fields["map_default"].default == {"k": "v"}
    # the 3.0 boolean exclusiveMinimum (false) is dropped from constraints
    assert "exclusiveMinimum" not in fields["excl_bool"].constraints

    # discriminator fallbacks
    assert isinstance(decls["DiscNoRefs"], IRModel)  # no usable mapping -> object
    assert isinstance(decls["DiscMixed"], IRAlias)  # one good ref -> union/alias

    # the enum subtype stayed an enum despite being a discriminator target
    assert isinstance(decls["EnumSub"], IREnum)

    int_enum = decls["IntEnumNeg"]
    assert isinstance(int_enum, IREnum)
    assert int_enum.base == "int"
    member_names = [m for m, _ in int_enum.members]
    assert "VALUE_MINUS_1" in member_names
    assert "VALUE_0" in member_names


# --------------------------------------------------------------------------- #
# strip-prefix: ``auto`` with fewer than two dotted names                      #
# --------------------------------------------------------------------------- #


def test_strip_prefix_auto_too_few_dotted_names() -> None:
    spec = _schema_spec(
        {
            "com.acme.Foo": {"type": "object", "properties": {"x": {"type": "string"}}},
            "Bar": {"type": "object", "properties": {"y": {"type": "string"}}},
        }
    )
    doc = build_ir(spec, RefResolver(spec), strip_prefix="auto")
    names = {d.name for d in doc.declarations}
    # only one dotted name -> nothing common to strip -> the dotted name is kept whole
    assert "ComAcmeFoo" in names
    assert "Bar" in names


# --------------------------------------------------------------------------- #
# operation-side edge paths                                                    #
# --------------------------------------------------------------------------- #


_OPS_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Ops", "version": "1.0.0"},
    # two servers with disagreeing path prefixes -> no shared prefix folded in
    "servers": [{"url": "https://a.example.com/v1"}, {"url": "https://b.example.com/v2"}],
    "paths": {
        # a path item that is not a mapping -> skipped
        "/notdict": "i am not a dict",
        # a parameter without a ``name`` -> skipped
        "/params": {
            "get": {
                "operationId": "p",
                "parameters": [{"in": "query"}],
                "responses": {"200": {"description": "ok"}},
            }
        },
        # a requestBody that is not a mapping -> no body
        "/badbody": {
            "post": {
                "operationId": "bb",
                "requestBody": True,
                "responses": {"200": {"description": "ok"}},
            }
        },
        # a non-object JSON body -> carried as a single json_type
        "/arrbody": {
            "post": {
                "operationId": "ab",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                },
                "responses": {"200": {"description": "ok"}},
            }
        },
        # an unsupported content type -> no body
        "/textbody": {
            "post": {
                "operationId": "tb",
                "requestBody": {"content": {"text/plain": {"schema": {"type": "string"}}}},
                "responses": {"200": {"description": "ok"}},
            }
        },
        # multipart whose schema is not a mapping -> no fields
        "/multipart": {
            "post": {
                "operationId": "mp",
                "requestBody": {"content": {"multipart/form-data": {"schema": True}}},
                "responses": {"200": {"description": "ok"}},
            }
        },
        # a response that is not a mapping -> skipped
        "/badresp": {
            "get": {"operationId": "br", "responses": {"200": True, "201": {"description": "ok"}}}
        },
    },
    "components": {"securitySchemes": {"bad": True}},
}


def test_operation_edge_paths() -> None:
    doc = build_ir(_OPS_SPEC, RefResolver(_OPS_SPEC))
    ops = {op.operation_id: op for op in doc.operations}

    # the non-dict path item produced no operation
    assert "/notdict" not in [op.path for op in doc.operations]

    # parameter without a name was dropped
    assert ops["p"].parameters == []

    # malformed / unsupported bodies are absent
    assert ops["bb"].body is None
    assert ops["tb"].body is None

    # array JSON body carried as json_type, not spread fields
    assert ops["ab"].body is not None
    assert ops["ab"].body.json_type is not None
    assert ops["ab"].body.json_type.annotation() == "list[str]"

    # multipart with a non-dict schema -> empty fields
    assert ops["mp"].body is not None
    assert ops["mp"].body.fields == []

    # the non-dict 200 response was skipped, 201 became the success
    assert ops["br"].success is not None
    assert ops["br"].success.status == "201"

    # disagreeing server prefixes -> operation urls are left untouched
    assert ops["p"].path == "/params"

    # the non-dict security scheme definition was skipped
    assert "bad" not in doc.security_schemes
