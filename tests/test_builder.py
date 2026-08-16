"""Tests for the OpenAPI -> IR builder."""

from __future__ import annotations

from typing import Any

import pytest

from unihttp_openapi_generator.ir.builder import IRBuilder, build_ir
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import IRAlias, IREnum, IRModel
from unihttp_openapi_generator.ir.operations import BodyKind, ParamLocation
from unihttp_openapi_generator.ir.types import (
    BOOL,
    FLOAT,
    INT,
    STR,
    ListType,
    LiteralType,
    MappingType,
    OptionalType,
    RefType,
    UnionType,
    UploadFileType,
)
from unihttp_openapi_generator.refs import RefResolver


@pytest.fixture
def ir(sample_spec: dict[str, Any]) -> IRDocument:
    return build_ir(sample_spec, RefResolver(sample_spec))


def _decl(ir: IRDocument, name: str) -> Any:
    return next(d for d in ir.declarations if d.name == name)


def test_basic_document(ir: IRDocument) -> None:
    assert ir.title == "Sample"
    # The "/v1" path on the server is folded into operation urls (see the
    # dedicated server-path tests); base_url keeps only the origin.
    assert ir.base_url == "https://api.example.com"
    assert ir.tags == ["pets"]


def test_object_model_fields(ir: IRDocument) -> None:
    pet = _decl(ir, "Pet")
    assert isinstance(pet, IRModel)
    by_name = {f.name: f for f in pet.fields}
    assert by_name["id"].required is True
    assert by_name["id"].type.annotation() == "int"
    assert by_name["created_at"].wire_name == "createdAt"
    assert by_name["created_at"].needs_alias is True
    # createdAt is not required -> optional with default None
    assert by_name["created_at"].type.annotation() == "datetime | None"
    assert by_name["created_at"].required is False
    # nullable + optional
    assert isinstance(by_name["tag"].type, OptionalType)
    # inline enum -> Literal (optional since not required)
    assert by_name["status"].type.annotation() == "Literal['available', 'sold'] | None"


def test_allof_merges_fields(ir: IRDocument) -> None:
    new_pet = _decl(ir, "NewPet")
    assert isinstance(new_pet, IRModel)
    names = {f.name for f in new_pet.fields}
    assert {"id", "name", "owner_id"} <= names


def test_named_enum(ir: IRDocument) -> None:
    kind = _decl(ir, "PetKind")
    assert isinstance(kind, IREnum)
    assert kind.base == "str"
    assert {v for _, v in kind.members} == {"cat", "dog"}


def test_oneof_alias_with_discriminator(ir: IRDocument) -> None:
    animal = _decl(ir, "Animal")
    assert isinstance(animal, IRAlias)
    assert isinstance(animal.target, UnionType)
    assert animal.discriminator is not None
    assert animal.discriminator.property_name == "kind"
    assert animal.discriminator.mapping == {"pet": "Pet", "new": "NewPet"}


def test_additional_properties_mapping(ir: IRDocument) -> None:
    meta = _decl(ir, "Metadata")
    assert isinstance(meta, IRAlias)
    assert isinstance(meta.target, MappingType)
    assert meta.target.annotation() == "dict[str, str]"


def test_list_pets_operation(ir: IRDocument) -> None:
    op = next(o for o in ir.operations if o.method_name == "list_pets")
    assert op.http_method == "GET"
    assert op.class_name == "ListPets"
    params = {p.name: p for p in op.parameters}
    assert params["limit"].location is ParamLocation.QUERY
    assert params["limit"].required is False
    assert params["tags"].style == "form"
    assert params["tags"].explode is False
    assert params["x_request_id"].needs_alias is True
    assert params["x_request_id"].required is True
    # success type is list[Pet]
    assert isinstance(op.return_type, ListType)
    assert op.return_type.annotation() == "list[Pet]"
    # default error response captured
    assert any(e.status == "default" for e in op.errors)
    assert op.errors[0].type == RefType("Error")


def test_create_pet_json_body(ir: IRDocument) -> None:
    op = next(o for o in ir.operations if o.method_name == "create_pet")
    assert op.body is not None
    assert op.body.kind is BodyKind.JSON
    # the object body is spread into individual Body fields (no single body model)
    assert op.body.json_type is None
    fields = {f.name: f for f in op.body.fields}
    assert "name" in fields
    assert fields["owner_id"].wire_name == "ownerId"
    assert fields["created_at"].wire_name == "createdAt"
    assert op.return_type == RefType("Pet")


def test_multipart_body(ir: IRDocument) -> None:
    op = next(o for o in ir.operations if o.method_name == "upload_photo")
    assert op.body is not None
    assert op.body.kind is BodyKind.MULTIPART
    fields = {f.name: f for f in op.body.fields}
    assert isinstance(fields["file"].type, UploadFileType)
    assert fields["file"].is_file is True
    assert fields["caption"].is_file is False
    assert op.return_type is None


def test_security_schemes(ir: IRDocument) -> None:
    assert ir.security_schemes["apiKey"].kind == "apiKey"
    assert ir.security_schemes["apiKey"].parameter_name == "X-API-Key"
    assert ir.security_schemes["bearer"].scheme == "bearer"


# -- item 1: server selection -------------------------------------------------


def test_base_url_prefers_production_server() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "servers": [
            {"url": "https://mock.example.com", "description": "Mock Server"},
            {"url": "https://api.example.com", "description": "Production"},
        ],
        "paths": {},
    }
    ir = build_ir(spec, RefResolver(spec))
    assert ir.base_url == "https://api.example.com"
    assert [(s.url, s.description) for s in ir.servers] == [
        ("https://mock.example.com", "Mock Server"),
        ("https://api.example.com", "Production"),
    ]


def test_base_url_falls_back_to_first_server() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "servers": [{"url": "https://first.example.com"}, {"url": "https://second.example.com"}],
        "paths": {},
    }
    ir = build_ir(spec, RefResolver(spec))
    assert ir.base_url == "https://first.example.com"


def _spec_with_server(url: str) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "servers": [{"url": url}],
        "paths": {
            "/store/inventory": {
                "get": {
                    "operationId": "getInventory",
                    "tags": ["store"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }


def test_server_path_prefix_folded_into_operation_urls() -> None:
    # unihttp joins via urljoin(base_url, "/op"), which drops a path component
    # on base_url. So a servers URL like ".../api/v3" must be split: the path
    # prefix is folded into each operation url, base_url keeps only the origin.
    ir = build_ir(
        _spec_with_server("https://api.example.com/api/v3"),
        RefResolver(_spec_with_server("https://api.example.com/api/v3")),
    )
    assert ir.base_url == "https://api.example.com"
    op = next(o for o in ir.operations if o.method_name == "get_inventory")
    assert op.path == "/api/v3/store/inventory"
    assert [s.url for s in ir.servers] == ["https://api.example.com"]


def test_relative_server_path_folded_and_base_url_dropped() -> None:
    # A relative servers entry (e.g. Swagger Petstore's "/api/v3") has no origin,
    # so the prefix folds into the urls and base_url becomes None (the user must
    # supply the host).
    spec = _spec_with_server("/api/v3")
    ir = build_ir(spec, RefResolver(spec))
    assert ir.base_url is None
    op = next(o for o in ir.operations if o.method_name == "get_inventory")
    assert op.path == "/api/v3/store/inventory"
    # a host-less server yields no usable origin, so it is dropped (no empty
    # "" entry left in the SERVERS map).
    assert ir.servers == []


def test_origin_only_server_leaves_urls_untouched() -> None:
    # No path component -> nothing to fold; behaviour is unchanged.
    spec = _spec_with_server("https://api.example.com")
    ir = build_ir(spec, RefResolver(spec))
    assert ir.base_url == "https://api.example.com"
    op = next(o for o in ir.operations if o.method_name == "get_inventory")
    assert op.path == "/store/inventory"


# -- item 2: schema defaults on optional params/form fields -------------------


def _defaults_spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "getX",
                    "tags": ["x"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 10},
                        },
                        {
                            "name": "flag",
                            "in": "query",
                            "schema": {"type": "boolean", "default": False},
                        },
                        {"name": "plain", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
                "post": {
                    "operationId": "postX",
                    "tags": ["x"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"type": "string", "default": "basic"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                },
            }
        },
    }


def test_param_defaults_recorded() -> None:
    spec = _defaults_spec()
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "get_x")
    params = {p.name: p for p in op.parameters}
    assert params["limit"].has_default is True
    assert params["limit"].default == 10
    assert params["flag"].has_default is True
    assert params["flag"].default is False
    # optional without a default keeps Omitted behavior
    assert params["plain"].has_default is False


def test_form_field_defaults_recorded() -> None:
    spec = _defaults_spec()
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "post_x")
    assert op.body is not None
    kind = op.body.fields[0]
    assert kind.has_default is True
    assert kind.default == "basic"


# -- item 3: empty object schema -> dict[str, Any] ----------------------------


def test_empty_object_schema_becomes_mapping() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Bag": {"type": "object"},
                "Wrapper": {
                    "type": "object",
                    "properties": {"data": {"type": "array", "items": {"type": "object"}}},
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    bag = _decl(ir, "Bag")
    assert isinstance(bag, IRAlias)
    assert isinstance(bag.target, MappingType)
    assert bag.target.annotation() == "dict[str, Any]"
    # the array's anonymous empty-object item must NOT become a model class
    assert all(not isinstance(d, IRModel) or d.name == "Wrapper" for d in ir.declarations)
    wrapper = _decl(ir, "Wrapper")
    assert isinstance(wrapper, IRModel)
    assert wrapper.fields[0].type.annotation() == "list[dict[str, Any]] | None"


# -- item 5: const support ----------------------------------------------------


def test_const_becomes_literal() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Card": {
                    "type": "object",
                    "properties": {"object": {"type": "string", "const": "card"}},
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    card = _decl(ir, "Card")
    assert isinstance(card, IRModel)
    obj = next(f for f in card.fields if f.name == "object")
    assert "Literal['card']" in obj.type.annotation()


# -- item 6: readOnly excluded from request bodies ----------------------------


def _readonly_body_spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/r": {
                "post": {
                    "operationId": "createThing",
                    "tags": ["r"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Thing"}}
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Thing"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Thing": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "id": {"type": "string", "readOnly": True},
                        "name": {"type": "string"},
                    },
                }
            }
        },
    }


def test_readonly_json_body_spreads_writable_fields() -> None:
    spec = _readonly_body_spec()
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "create_thing")
    assert op.body is not None
    # the body is spread into Body fields; readOnly ``id`` is excluded
    assert op.body.json_type is None
    names = {f.name for f in op.body.fields}
    assert "name" in names
    assert "id" not in names
    assert not any(d.name == "CreateThingBody" for d in ir.declarations)
    # the read model still carries id
    thing = _decl(ir, "Thing")
    assert "id" in {f.name for f in thing.fields}


def test_body_fields_carry_description() -> None:
    """Spread body fields keep their schema ``description`` (as parameters do)."""
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/d": {
                "post": {
                    "operationId": "createDoc",
                    "tags": ["d"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["title"],
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "Document title.",
                                        },
                                        "body": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"204": {"description": "no content"}},
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "create_doc")
    assert op.body is not None
    fields = {f.name: f for f in op.body.fields}
    assert fields["title"].description == "Document title."
    assert fields["body"].description is None


def test_readonly_form_field_dropped() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/f": {
                "post": {
                    "operationId": "postForm",
                    "tags": ["f"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "readOnly": True},
                                        "name": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "post_form")
    assert op.body is not None
    assert {f.name for f in op.body.fields} == {"name"}


def test_body_without_readonly_reuses_model() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/n": {
                "post": {
                    "operationId": "createNew",
                    "tags": ["n"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Plain"}}
                        },
                    },
                    "responses": {"201": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Plain": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "create_new")
    assert op.body is not None
    # the object body is spread into Body fields; no dedicated body model
    assert op.body.json_type is None
    assert {f.name for f in op.body.fields} == {"name"}
    assert not any(d.name == "CreateNewBody" for d in ir.declarations)


def test_body_field_colliding_with_path_param_is_renamed() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/things/{name}": {
                "put": {
                    "operationId": "renameThing",
                    "tags": ["t"],
                    "parameters": [
                        {
                            "name": "name",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["name"],
                                    "properties": {"name": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "rename_thing")
    assert "name" in {p.name for p in op.parameters}
    assert op.body is not None
    # the body's `name` property is renamed so it doesn't clash with the path
    # param on the method dataclass; its wire name is preserved as an alias
    body_field = op.body.fields[0]
    assert body_field.name != "name"
    assert body_field.wire_name == "name"
    assert body_field.needs_alias


def test_body_field_unassignable_default_is_dropped() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {
            "/x": {
                "post": {
                    "operationId": "doX",
                    "tags": ["x"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "choice": {
                                            "oneOf": [
                                                {"$ref": "#/components/schemas/A"},
                                                {"$ref": "#/components/schemas/B"},
                                            ],
                                            "default": "auto",
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "A": {"type": "object", "properties": {"a": {"type": "string"}}},
                "B": {"type": "object", "properties": {"b": {"type": "string"}}},
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    op = next(o for o in ir.operations if o.method_name == "do_x")
    assert op.body is not None
    field = next(f for f in op.body.fields if f.name == "choice")
    # a string default that isn't a literal of the union type is dropped, so the
    # field renders as Omittable instead of ``= "auto"`` (which would not type-check)
    assert field.required is False
    assert field.has_default is False


# -- bug 4: list/dict default whose element type isn't a plain primitive ------


def test_list_literal_default_not_assignable_becomes_optional() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "M": {
                    "type": "object",
                    "properties": {
                        "modalities": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["text", "audio"]},
                            "default": ["audio"],
                        },
                        # control: a plain-primitive list default stays assignable
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["x"],
                        },
                    },
                }
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    model = _decl(ir, "M")
    fields = {f.name: f for f in model.fields}
    modalities = fields["modalities"]
    # list[Literal[...]] default is not a plain-primitive list -> field made optional,
    # value dropped (None).
    assert isinstance(modalities.type, OptionalType)
    assert isinstance(modalities.type.inner, ListType)
    assert isinstance(modalities.type.inner.item, LiteralType)
    assert modalities.default is None
    # the plain list[str] default is still carried
    tags = fields["tags"]
    assert isinstance(tags.type, ListType)
    assert tags.default == ["x"]


def test_strip_prefix_explicit() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "K", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "io.k8s.api.core.v1.Pod": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                },
                "io.k8s.apimachinery.meta.v1.ObjectMeta": {"type": "object", "properties": {}},
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), strip_prefix="io.k8s.api")
    names = {d.name for d in ir.declarations}
    assert "CoreV1Pod" in names  # matched prefix stripped
    # a name not under the prefix is left intact
    assert any(n.startswith("IoK8sApimachinery") for n in names)


def test_strip_prefix_auto() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "K", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "io.k8s.api.core.v1.Pod": {"type": "object", "properties": {}},
                "io.k8s.apimachinery.meta.v1.ObjectMeta": {"type": "object", "properties": {}},
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), strip_prefix="auto")
    names = {d.name for d in ir.declarations}
    # longest common segment prefix is io.k8s -> stripped from both
    assert "ApiCoreV1Pod" in names
    assert "ApimachineryMetaV1ObjectMeta" in names


# -- inheritance mode ---------------------------------------------------------------


_INHERITANCE_SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "I", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "Button": {
                "type": "object",
                "required": ["type", "text"],
                "properties": {
                    "type": {"type": "string"},
                    "text": {"type": "string"},
                    "label": {"type": "string"},
                },
                "discriminator": {
                    "propertyName": "type",
                    "mapping": {
                        "callback": "#/components/schemas/CallbackButton",
                        "link": "#/components/schemas/LinkButton",
                    },
                },
            },
            "CallbackButton": {
                "allOf": [
                    {"$ref": "#/components/schemas/Button"},
                    {
                        "required": ["payload"],
                        "properties": {
                            # restated only to add prose: it must stay required
                            "text": {"type": "string", "description": "Visible label."},
                            # byte-for-byte restatement: explicit presence still matters
                            "label": {"type": "string"},
                            "payload": {"type": "string"},
                        },
                    },
                ]
            },
            # marker subtype: nothing but the tag distinguishes it
            "LinkButton": {"allOf": [{"$ref": "#/components/schemas/Button"}]},
            "Owner": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}},
            },
            "NamedOwner": {
                "allOf": [
                    {"$ref": "#/components/schemas/Owner"},
                    {"properties": {"name": {"type": "string"}}},
                ]
            },
            "Mixed": {
                "allOf": [
                    {"$ref": "#/components/schemas/Owner"},
                    {"$ref": "#/components/schemas/Button"},
                ]
            },
        }
    },
}


@pytest.fixture
def inherited() -> IRDocument:
    spec = _INHERITANCE_SPEC
    return build_ir(spec, RefResolver(spec), inheritance=True)


def test_inheritance_keeps_parent_fields_on_parent(inherited: IRDocument) -> None:
    base = _decl(inherited, "Button")
    assert isinstance(base, IRModel)
    assert base.base_model is None
    assert [f.name for f in base.fields] == ["type", "text", "label"]

    sub = _decl(inherited, "CallbackButton")
    assert sub.base_model == "Button"
    # Explicit child fields remain declarations even when they repeat a base field
    assert {f.name for f in sub.fields} == {"type", "text", "label", "payload"}


def test_inheritance_keeps_explicit_restatement(inherited: IRDocument) -> None:
    sub = _decl(inherited, "CallbackButton")
    text = next(f for f in sub.fields if f.name == "text")

    assert text.required is True
    assert text.type.annotation() == "str"
    assert text.description == "Visible label."
    assert text.incompatible_override is False
    label = next(f for f in sub.fields if f.name == "label")
    assert label.description is None
    assert label.incompatible_override is False


def test_inheritance_keeps_widening_restatement() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "P": {"type": "object", "required": ["v"], "properties": {"v": {"type": "string"}}},
                "C": {
                    "allOf": [
                        {"$ref": "#/components/schemas/P"},
                        {"properties": {"v": {"type": "string", "nullable": True}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    sub = _decl(ir, "C")
    assert isinstance(sub, IRModel)
    assert sub.base_model == "P"
    assert [field.name for field in sub.fields] == ["v"]
    assert sub.fields[0].incompatible_override is True


def test_inheritance_keeps_narrowing_restatement() -> None:
    """A genuine narrowing (``Literal`` over ``str``) is a sound override, so it stays."""
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "P": {
                    "type": "object",
                    "required": ["k"],
                    "properties": {"k": {"type": "string"}},
                },
                "C": {
                    "allOf": [
                        {"$ref": "#/components/schemas/P"},
                        {"required": ["k"], "properties": {"k": {"enum": ["one", "two"]}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    sub = _decl(ir, "C")
    assert isinstance(sub, IRModel)
    assert [f.type.annotation() for f in sub.fields] == ["Literal['one', 'two']"]


def test_inheritance_pins_discriminator_tag(inherited: IRDocument) -> None:
    sub = _decl(inherited, "CallbackButton")
    tag = next(f for f in sub.fields if f.name == "type")
    assert tag.type == LiteralType(("callback",))
    assert tag.has_default is True
    assert tag.default == "callback"


def test_inheritance_keeps_marker_subtype_as_class(inherited: IRDocument) -> None:
    marker = _decl(inherited, "LinkButton")
    assert isinstance(marker, IRModel)
    assert marker.base_model == "Button"
    assert [f.name for f in marker.fields] == ["type"]


def test_inheritance_discriminated_base_is_a_model(inherited: IRDocument) -> None:
    base = _decl(inherited, "Button")
    assert isinstance(base, IRModel)
    assert base.discriminator is not None
    assert base.discriminator.mapping == {
        "callback": "CallbackButton",
        "link": "LinkButton",
    }


def test_inheritance_subtype_does_not_inherit_discriminator(inherited: IRDocument) -> None:
    # A discriminator belongs to the class that declares it: copying it down would
    # make every subtype look like a tagged-union base of the whole family.
    assert _decl(inherited, "CallbackButton").discriminator is None
    assert _decl(inherited, "LinkButton").discriminator is None


def test_inheritance_orders_bases_before_subclasses(inherited: IRDocument) -> None:
    order = [d.name for d in inherited.declarations]
    assert order.index("Button") < order.index("CallbackButton")
    assert order.index("Button") < order.index("LinkButton")
    assert order.index("Owner") < order.index("NamedOwner")


def test_inheritance_plain_allof_ref_becomes_base(inherited: IRDocument) -> None:
    sub = _decl(inherited, "NamedOwner")
    assert sub.base_model == "Owner"
    assert [f.name for f in sub.fields] == ["name"]
    assert sub.referenced_models() == {"Owner"}


def test_inheritance_multiple_refs_still_merge(inherited: IRDocument) -> None:
    # Two `$ref`s give no single parent to pick, so the merge behaviour is kept.
    mixed = _decl(inherited, "Mixed")
    assert mixed.base_model is None
    assert {f.name for f in mixed.fields} == {"id", "type", "text", "label"}


def test_without_inheritance_parent_fields_are_merged() -> None:
    spec = _INHERITANCE_SPEC
    ir = build_ir(spec, RefResolver(spec))
    sub = _decl(ir, "CallbackButton")
    assert isinstance(sub, IRModel)
    assert sub.base_model is None
    assert {f.name for f in sub.fields} == {"type", "text", "label", "payload"}
    # the discriminated base collapses into a union alias, as before
    assert isinstance(_decl(ir, "Button"), IRAlias)


def test_inheritance_oneof_discriminator_base_stays_a_union() -> None:
    """The common polymorphism idiom must not be turned into an empty class.

    ``{oneOf: [...], discriminator: {mapping}}`` declares no properties of its own, so
    there is nothing to inherit. Rendering it as ``class Button`` would emit an empty
    class and every ``list[Button]`` payload would decode into it, silently dropping
    each variant's fields -- so it stays a union alias even in inheritance mode.
    """
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Button": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/CallbackButton"},
                        {"$ref": "#/components/schemas/LinkButton"},
                    ],
                    "discriminator": {
                        "propertyName": "type",
                        "mapping": {
                            "callback": "#/components/schemas/CallbackButton",
                            "link": "#/components/schemas/LinkButton",
                        },
                    },
                },
                "ButtonBase": {
                    "type": "object",
                    "required": ["type", "text"],
                    "properties": {"type": {"type": "string"}, "text": {"type": "string"}},
                },
                "CallbackButton": {
                    "allOf": [
                        {"$ref": "#/components/schemas/ButtonBase"},
                        {"required": ["payload"], "properties": {"payload": {"type": "string"}}},
                    ]
                },
                "LinkButton": {
                    "allOf": [
                        {"$ref": "#/components/schemas/ButtonBase"},
                        {"required": ["url"], "properties": {"url": {"type": "string"}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    button = _decl(ir, "Button")
    assert isinstance(button, IRAlias)
    assert button.target.annotation() == "CallbackButton | LinkButton"
    # the real base of the family is still turned into a superclass
    assert _decl(ir, "CallbackButton").base_model == "ButtonBase"
    assert _decl(ir, "LinkButton").base_model == "ButtonBase"


def test_inheritance_recursive_base_still_subclasses() -> None:
    """Inheritance must not depend on the order the schema graph happens to be walked.

    ``Node`` is built first and reaches ``LeafNode`` through its own ``child`` property,
    so ``LeafNode`` resolves its base while ``Node`` has no ``_declarations`` entry yet.
    Deciding from the schema (not from the half-built registry) keeps it a subclass.
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "child": {"$ref": "#/components/schemas/LeafNode"},
                    },
                },
                "LeafNode": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Node"},
                        {"properties": {"value": {"type": "string"}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    leaf = _decl(ir, "LeafNode")
    assert leaf.base_model == "Node"
    assert [f.name for f in leaf.fields] == ["value"]  # not a copy of Node's fields


def test_inheritance_tag_field_never_collides_with_a_sibling() -> None:
    """One identifier cannot carry two wire names, and the tag is the one that keeps it.

    ``Type`` and ``type`` snake-case to the same identifier. Emitting both unqualified
    would put two identical attribute names in one class body: the later wins and the
    discriminator tag is silently destroyed. The tag re-declares the base's ``type``, so
    it has to stay on the base's attribute -- putting it anywhere else leaves two
    attributes pointing at the same wire key, which adaptix rejects outright. The
    sibling is the one that gives way and gets an alias.
    """
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "B": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {"type": {"type": "string"}},
                    "discriminator": {
                        "propertyName": "type",
                        "mapping": {"a": "#/components/schemas/A"},
                    },
                },
                "A": {
                    "allOf": [
                        {"$ref": "#/components/schemas/B"},
                        {"properties": {"Type": {"type": "integer"}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    sub = _decl(ir, "A")
    names = [f.name for f in sub.fields]
    assert len(names) == len(set(names)), f"duplicate class attributes: {names}"
    tag = next(f for f in sub.fields if f.wire_name == "type")
    assert tag.type == LiteralType(("a",))
    assert tag.name == "type"  # overrides B.type, so it must be B.type's attribute
    sibling = next(f for f in sub.fields if f.wire_name == "Type")
    assert sibling.name != tag.name
    assert sibling.needs_alias is True  # renamed, so the wire name is restored by an alias


def test_inheritance_tag_is_pinned_as_the_enum_member_the_base_declares() -> None:
    """A base that types the tag as a ``$ref`` to an enum still gets its tag pinned.

    That is the idiomatic OpenAPI form, and ``Literal['callback']`` is not assignable
    to the enum: emitting it fails ``mypy --strict``. Dropping the tag instead is worse
    than it sounds -- the subtype is then constructible with any sibling's tag, and
    encodes without one unless the caller passes it. Re-typing the tag to the enum and
    pinning the matching *member* keeps the base's annotation, so it survives as an
    override that changes nothing but the default.
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "ButtonKind": {"type": "string", "enum": ["callback", "link"]},
                "Button": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {"type": {"$ref": "#/components/schemas/ButtonKind"}},
                    "discriminator": {
                        "propertyName": "type",
                        "mapping": {
                            "callback": "#/components/schemas/CallbackButton",
                            "link": "#/components/schemas/LinkButton",
                        },
                    },
                },
                "CallbackButton": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Button"},
                        {"required": ["payload"], "properties": {"payload": {"type": "string"}}},
                    ]
                },
                "LinkButton": {"allOf": [{"$ref": "#/components/schemas/Button"}]},
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    sub = _decl(ir, "CallbackButton")
    assert sub.base_model == "Button"
    assert [f.name for f in sub.fields] == ["type", "payload"]
    tag = sub.fields[0]
    # the base's annotation, so mypy sees a legal override; the member as the default
    assert tag.type.annotation() == "ButtonKind"
    assert tag.default_expr == "ButtonKind.CALLBACK"
    assert tag.has_default is True
    marker = _decl(ir, "LinkButton")
    assert marker.base_model == "Button"
    assert [f.default_expr for f in marker.fields] == ["ButtonKind.LINK"]
    base = _decl(ir, "Button")
    assert [f.type.annotation() for f in base.fields] == ["ButtonKind"]


def test_inheritance_checks_the_whole_base_chain() -> None:
    """A subclass carries only its own fields, so a grandparent's are one hop further.

    ``C`` re-declares ``v`` as an integer over ``A``'s string. Looking only at the
    direct parent ``B`` finds nothing and misses the required assignment ignore
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "A": {"type": "object", "required": ["v"], "properties": {"v": {"type": "string"}}},
                "B": {
                    "allOf": [
                        {"$ref": "#/components/schemas/A"},
                        {"properties": {"b": {"type": "string"}}},
                    ]
                },
                "C": {
                    "allOf": [
                        {"$ref": "#/components/schemas/B"},
                        {"properties": {"v": {"type": "integer"}, "c": {"type": "string"}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    fields = _decl(ir, "C").fields

    assert [field.name for field in fields] == ["v", "c"]
    assert fields[0].incompatible_override is True


def test_inheritance_renames_a_field_shadowing_an_inherited_identifier() -> None:
    """Distinct wire names can collapse onto one identifier *across* the hierarchy.

    ``packSize`` on the base and ``pack_size`` on the subtype are different properties,
    so neither may be dropped -- but one attribute cannot hold both, and the subclass
    one would shadow the base's with an unrelated type.
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "B": {
                    "type": "object",
                    "required": ["packSize"],
                    "properties": {"packSize": {"type": "integer"}},
                },
                "A": {
                    "allOf": [
                        {"$ref": "#/components/schemas/B"},
                        {"properties": {"pack_size": {"type": "string"}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    own = next(f for f in _decl(ir, "A").fields if f.wire_name == "pack_size")
    assert own.name != "pack_size"  # taken by the inherited ``packSize``
    assert own.needs_alias is True


def test_inheritance_keeps_a_restatement_that_changes_the_default() -> None:
    """An identical annotation is a legal override, so a new ``default`` survives.

    Dropping it would silently hand the subtype the base's value.
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "P": {"type": "object", "properties": {"mode": {"type": "string", "default": "f"}}},
                "C": {
                    "allOf": [
                        {"$ref": "#/components/schemas/P"},
                        {"properties": {"mode": {"type": "string", "default": "s"}}},
                    ]
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    mode = next(f for f in _decl(ir, "C").fields if f.wire_name == "mode")
    assert mode.default == "s"


def test_allof_subtype_does_not_inherit_the_discriminator() -> None:
    """A discriminator describes the schema that declares it, not the ones merging it in.

    Copying it down through ``allOf`` marks every concrete subtype as a tagged-union
    base -- which the renderer then announces in a ``# discriminator:`` header above a
    class that is nothing of the sort, with a mapping resolved only as far as the walk
    had got.
    """
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "required": ["petType"],
                    "properties": {"petType": {"type": "string"}},
                    "discriminator": {
                        "propertyName": "petType",
                        "mapping": {"dog": "#/components/schemas/Dog"},
                    },
                },
                "Dog": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Pet"},
                        {"properties": {"bark": {"type": "boolean"}}},
                    ]
                },
            }
        },
    }
    for inheritance in (False, True):
        ir = build_ir(spec, RefResolver(spec), inheritance=inheritance)
        assert _decl(ir, "Dog").discriminator is None, f"inheritance={inheritance}"


def test_allof_cycle_terminates_instead_of_recursing() -> None:
    """An ``allOf`` chain that loops back on itself must not blow the stack.

    ``X: allOf [Y]`` / ``Y: allOf [X]`` describes an infinitely deep object. The merge
    used to follow it until the interpreter ran out of stack, which also meant the
    inheritance-cycle break in ``_ordered_declarations`` could never run: nothing ever
    got as far as having a base chain to break.
    """
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "X": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Y"},
                        {"properties": {"x": {"type": "string"}}},
                    ]
                },
                "Y": {
                    "allOf": [
                        {"$ref": "#/components/schemas/X"},
                        {"properties": {"y": {"type": "string"}}},
                    ]
                },
            }
        },
    }
    merged = build_ir(spec, RefResolver(spec))
    # merge mode: each side ends up with both properties, once
    assert {f.name for f in _decl(merged, "X").fields} == {"x", "y"}
    assert {f.name for f in _decl(merged, "Y").fields} == {"x", "y"}

    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    bases = {decl.name: decl.base_model for decl in ir.declarations if isinstance(decl, IRModel)}
    # exactly one of the two inheritance edges survives, so the emitted classes resolve
    assert sorted(bases) == ["X", "Y"]
    assert len([base for base in bases.values() if base is not None]) == 1
    names = [decl.name for decl in ir.declarations]
    for name, base in bases.items():
        if base is not None:
            assert names.index(base) < names.index(name)


def _hier(schemas: dict[str, Any]) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "S", "version": "1.0.0"},
        "paths": {},
        "components": {"schemas": schemas},
    }


def test_inheritance_literal_over_a_mismatched_primitive_is_not_a_narrowing() -> None:
    """``Literal['one', 'two']`` does not narrow an ``int`` base, whatever the shape.

    Knowing the base is *some* scalar says nothing about which one, so accepting every
    ``Literal`` over ``str``/``int``/``bool`` emitted ``class C(P): k: Literal['one',
    'two']`` over ``k: int`` -- an ``[assignment]`` error that made ``--inheritance
    --check`` fail on an ordinary spec.
    """
    spec = _hier(
        {
            "P": {"type": "object", "required": ["k"], "properties": {"k": {"type": "integer"}}},
            "C": {
                "allOf": [
                    {"$ref": "#/components/schemas/P"},
                    {"required": ["k"], "properties": {"k": {"enum": ["one", "two"]}}},
                ]
            },
        }
    )
    sub = _decl(build_ir(spec, RefResolver(spec), inheritance=True), "C")
    assert sub.base_model == "P"
    assert [field.name for field in sub.fields] == ["k"]
    assert sub.fields[0].incompatible_override is True

    # the same restatement over a ``str`` base *is* a genuine narrowing and stays
    spec["components"]["schemas"]["P"]["properties"]["k"] = {"type": "string"}
    kept = _decl(build_ir(spec, RefResolver(spec), inheritance=True), "C")
    assert [f.type.annotation() for f in kept.fields] == ["Literal['one', 'two']"]


def test_inheritance_carries_a_required_only_tightening_down() -> None:
    """Naming a base property in ``required`` without restating it must still tighten it.

    The subtype contributes no property of its own here, so nothing used to reach the
    subclass and a spec-required field silently kept the base's optional declaration.
    """
    spec = _hier(
        {
            "P": {"type": "object", "properties": {"v": {"type": "string"}}},
            "C": {
                "allOf": [
                    {"$ref": "#/components/schemas/P"},
                    {
                        "type": "object",
                        "required": ["v"],
                        "properties": {"c": {"type": "string"}},
                    },
                ]
            },
        }
    )
    sub = _decl(build_ir(spec, RefResolver(spec), inheritance=True), "C")
    v = next(f for f in sub.fields if f.wire_name == "v")
    assert v.required is True
    assert v.has_default is False
    # the annotation is the base's: the IR cannot tell "optional" from "nullable", and
    # narrowing to ``str`` would reject a null the spec may well allow
    assert v.type.annotation() == "str | None"


def test_inheritance_keeps_a_restatement_that_only_adds_constraints() -> None:
    """``Annotated[str, Meta(max_length=8)]`` over ``str`` is a legal override.

    Comparing annotations alone dropped it, so the generated client stopped enforcing
    the constraints the spec mandates and accepted payloads the API rejects.
    """
    spec = _hier(
        {
            "P": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
            "C": {
                "allOf": [
                    {"$ref": "#/components/schemas/P"},
                    {
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string", "maxLength": 8, "pattern": "^[a-z]+$"}
                        },
                    },
                ]
            },
        }
    )
    sub = _decl(build_ir(spec, RefResolver(spec), inheritance=True), "C")
    assert [f.constraints for f in sub.fields] == [{"maxLength": 8, "pattern": "^[a-z]+$"}]


def test_inheritance_empty_properties_holder_stays_a_union_alias() -> None:
    """``properties: {}`` is not "declares its own structure".

    Testing key presence let a bare discriminator holder become an empty
    ``class Shape: pass`` that every payload annotated with it decoded into, losing
    every field of the concrete variant.
    """
    spec = _hier(
        {
            "Shape": {
                "type": "object",
                "properties": {},
                "discriminator": {
                    "propertyName": "kind",
                    "mapping": {
                        "circle": "#/components/schemas/Circle",
                        "square": "#/components/schemas/Square",
                    },
                },
            },
            "Circle": {
                "allOf": [
                    {"$ref": "#/components/schemas/Shape"},
                    {
                        "required": ["kind", "r"],
                        "properties": {"kind": {"type": "string"}, "r": {"type": "number"}},
                    },
                ]
            },
            "Square": {
                "allOf": [
                    {"$ref": "#/components/schemas/Shape"},
                    {
                        "required": ["kind", "side"],
                        "properties": {"kind": {"type": "string"}, "side": {"type": "number"}},
                    },
                ]
            },
        }
    )
    shape = _decl(build_ir(spec, RefResolver(spec), inheritance=True), "Shape")
    assert isinstance(shape, IRAlias)
    assert shape.target.annotation() == "Circle | Square"


def test_allof_cycle_merges_the_dropped_base_instead_of_losing_its_fields() -> None:
    """Breaking an inheritance cycle must not cost the model its inherited fields.

    ``_ordered_declarations`` clears ``base_model`` to keep the emitted classes
    resolvable; without merging the base back in, the orphaned end kept only the
    properties it declared itself and decoded strictly less than merge mode does.
    """
    spec = _hier(
        {
            "X": {
                "allOf": [
                    {"$ref": "#/components/schemas/Y"},
                    {"properties": {"x": {"type": "string"}}},
                ]
            },
            "Y": {
                "allOf": [
                    {"$ref": "#/components/schemas/X"},
                    {"properties": {"y": {"type": "string"}}},
                ]
            },
        }
    )
    merged = build_ir(spec, RefResolver(spec))
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    orphan = next(d for d in ir.declarations if isinstance(d, IRModel) and d.base_model is None)
    # whichever end lost its base edge still reaches every wire key merge mode has
    assert {f.wire_name for f in orphan.fields} == {
        f.wire_name for f in _decl(merged, orphan.name).fields
    }


# -- narrowing predicate: branches reached only from specific type shapes ------


@pytest.mark.parametrize(
    ("sub", "base", "expected"),
    [
        # non-optional sub over an optional base: admitted directly, or via the inner
        (STR, OptionalType(STR), True),
        (LiteralType(("a",)), OptionalType(STR), True),
        (INT, OptionalType(STR), False),
        # literal over literal: only a subset narrows
        (LiteralType(("a",)), LiteralType(("a", "b")), True),
        (LiteralType(("c",)), LiteralType(("a", "b")), False),
        # union base: narrowing any one member is enough
        (STR, UnionType((STR, INT)), True),
        # via the ``int`` member, since a bool is an int as far as mypy is concerned
        (BOOL, UnionType((STR, INT)), True),
        (FLOAT, UnionType((STR, INT)), False),
        # a Literal is answered against the base's *own* shape before the union branch
        # is reached, so this is a deliberate false no: the subtype inherits the wider
        # annotation instead of narrowing it. Safe, since a false yes emits code that
        # fails ``mypy --strict`` while a false no only loses precision.
        (LiteralType(("a",)), UnionType((STR, INT)), False),
        # both optional: compare the inners
        (OptionalType(LiteralType(("a",))), OptionalType(STR), True),
        (OptionalType(STR), OptionalType(INT), False),
        # mypy's numeric tower admits an integer wherever a float is expected, and a
        # bool wherever an int is
        (INT, FLOAT, True),
        (BOOL, INT, True),
        (FLOAT, INT, False),
        # containers are invariant: a narrowed element is not a narrowed container
        (ListType(INT), ListType(FLOAT), False),
        # a $ref answers no without a declaration map to check the base chain in
        (RefType("Dog"), RefType("Animal"), False),
    ],
)
def test_is_narrowing_type_shapes(sub: Any, base: Any, expected: bool) -> None:
    assert IRBuilder._is_narrowing(sub, base) is expected


@pytest.mark.parametrize(
    ("values", "py", "expected"),
    [
        (("a", "b"), "str", True),
        ((1, 2), "int", True),
        # bool is a subtype of int, so Literal[True] is assignable to an int base
        ((True,), "int", True),
        ((True, False), "bool", True),
        ((1,), "bool", False),
        (("a",), "int", False),
        ((1,), "str", False),
        # anything else (float, bytes, datetime, ...) is not a Literal-able base
        ((1.5,), "float", False),
    ],
)
def test_literals_fit_primitive(values: Any, py: str, expected: bool) -> None:
    assert IRBuilder._literals_fit(values, py) is expected


def _builder(spec: dict[str, Any], *, inheritance: bool = True) -> IRBuilder:
    return IRBuilder(spec, RefResolver(spec), inheritance=inheritance)


def test_declares_model_mirrors_build_named_dispatch() -> None:
    """``_resolve_base_model`` decides from the schema, so the two must not drift."""
    builder = _builder(_hier({}))
    assert builder._declares_model("not a dict") is False
    assert builder._declares_model({"enum": ["a", "b"], "type": "string"}) is False
    # an enum that also declares properties is still an object
    assert builder._declares_model({"enum": ["a"], "properties": {"x": {}}}) is True
    # a discriminated holder is a class only in inheritance mode, and only with structure
    holder = {"properties": {"k": {}}, "discriminator": {"propertyName": "k", "mapping": {}}}
    assert builder._declares_model(holder) is True
    assert _builder(_hier({}), inheritance=False)._declares_model(holder) is False
    assert builder._declares_model({"properties": {}, "discriminator": {"mapping": {}}}) is False
    # a discriminator subtype is always concrete, even as a bare marker
    assert builder._declares_model({"allOf": [{"$ref": "#/x"}]}, is_disc_subtype=True) is True
    assert builder._declares_model({"allOf": [{"$ref": "#/x"}]}) is False


def test_inherited_fields_stops_at_a_non_model_base() -> None:
    """A base name that resolves to an enum or alias contributes nothing."""
    by_name: dict[str, Any] = {"E": IREnum(name="E", base="str", members=[("A", "a")])}
    assert IRBuilder._inherited_fields(by_name, "E") == {}
    assert IRBuilder._inherited_fields({}, "Missing") == {}


def test_retype_discriminator_tag_leaves_non_enum_bases_alone() -> None:
    """Only a tag whose base declares it as a ``$ref`` to an *enum* is re-typed.

    A ``str``-typed base keeps the plain ``Literal`` (already assignable), a ``$ref`` to
    a model is not something a tag value can be pinned to, and a defaulted single-value
    Literal that the base never declares is not a tag at all.
    """
    spec = _hier(
        {
            "KindObj": {"type": "object", "properties": {"n": {"type": "string"}}},
            # base types the tag as a plain string -> Literal stays as-is
            "StrBase": {
                "type": "object",
                "required": ["kind"],
                "properties": {"kind": {"type": "string"}},
                "discriminator": {
                    "propertyName": "kind",
                    "mapping": {"one": "#/components/schemas/StrSub"},
                },
            },
            "StrSub": {
                "allOf": [
                    {"$ref": "#/components/schemas/StrBase"},
                    {"required": ["a"], "properties": {"a": {"type": "string"}}},
                ]
            },
            # base types the tag as a ref to a *model* -> nothing to pin a member from
            "ObjBase": {
                "type": "object",
                "required": ["kind"],
                "properties": {"kind": {"$ref": "#/components/schemas/KindObj"}},
                "discriminator": {
                    "propertyName": "kind",
                    "mapping": {"two": "#/components/schemas/ObjSub"},
                },
            },
            "ObjSub": {
                "allOf": [
                    {"$ref": "#/components/schemas/ObjBase"},
                    {"required": ["b"], "properties": {"b": {"type": "string"}}},
                ]
            },
            # a defaulted single-value Literal the base never declares
            "P": {"type": "object", "properties": {"p": {"type": "string"}}},
            "OwnLiteral": {
                "allOf": [
                    {"$ref": "#/components/schemas/P"},
                    {"properties": {"mode": {"enum": ["only"], "default": "only"}}},
                ]
            },
        }
    )
    ir = build_ir(spec, RefResolver(spec), inheritance=True)

    str_tag = next(f for f in _decl(ir, "StrSub").fields if f.wire_name == "kind")
    assert str_tag.type.annotation() == "Literal['one']"
    assert str_tag.default_expr is None

    # A model-typed tag admits no member to pin, so the explicit tag is kept with an
    # assignment ignore
    obj_fields = _decl(ir, "ObjSub").fields
    assert [field.wire_name for field in obj_fields] == ["kind", "b"]
    assert obj_fields[0].incompatible_override is True

    own = next(f for f in _decl(ir, "OwnLiteral").fields if f.wire_name == "mode")
    assert own.default_expr is None


def test_allof_cycle_carries_additional_properties_and_required_across() -> None:
    """The cycle-broken end keeps everything merge mode would have given it.

    Its base edge is gone, so ``_reconcile_inheritance`` skips it -- and the base's
    ``additionalProperties`` is the one thing ``_flatten_object`` does *not* pull
    through an inherited member, so it has to be carried over by the merge itself.
    """
    spec = _hier(
        {
            "X": {
                "allOf": [
                    {"$ref": "#/components/schemas/Y"},
                    {"required": ["y"], "properties": {"x": {"type": "string"}}},
                ]
            },
            "Y": {
                "allOf": [
                    {"$ref": "#/components/schemas/X"},
                    {
                        "properties": {"y": {"type": "string"}},
                        "additionalProperties": {"type": "string"},
                    },
                ]
            },
        }
    )
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    orphan = next(d for d in ir.declarations if isinstance(d, IRModel) and d.base_model is None)
    # every wire key merge mode would give it, including the other end's
    assert {f.wire_name for f in orphan.fields} == {"x", "y"}
    # ``required`` is unioned across the cycle by ``_flatten_object`` before the fields
    # are built, so the shared property arrives already tightened
    assert next(f for f in orphan.fields if f.wire_name == "y").required is True
    # the base's free-form tail, which an inherited member never propagates
    assert orphan.additional_properties is not None
    assert orphan.additional_properties.annotation() == "str"


def test_retype_discriminator_tag_needs_the_value_to_be_an_enum_member() -> None:
    """A mapping key outside the base's enum leaves the tag alone.

    The spec is inconsistent -- it tags a subtype with a value the enum it typed the
    property as does not admit - so there is no member to pin and the explicit
    ``Literal`` is kept with an assignment ignore
    """
    spec = _hier(
        {
            "Kind": {"type": "string", "enum": ["known"]},
            "Base": {
                "type": "object",
                "required": ["kind"],
                "properties": {"kind": {"$ref": "#/components/schemas/Kind"}},
                "discriminator": {
                    "propertyName": "kind",
                    "mapping": {"absent": "#/components/schemas/Sub"},
                },
            },
            "Sub": {
                "allOf": [
                    {"$ref": "#/components/schemas/Base"},
                    {"required": ["a"], "properties": {"a": {"type": "string"}}},
                ]
            },
        }
    )
    sub = _decl(build_ir(spec, RefResolver(spec), inheritance=True), "Sub")
    assert sub.base_model == "Base"
    assert [field.wire_name for field in sub.fields] == ["kind", "a"]
    assert sub.fields[0].incompatible_override is True


def test_required_narrowing_recomputes_inherited_assignment_ignore() -> None:
    spec = _hier(
        {
            "A": {"type": "object", "properties": {"v": {"type": "string"}}},
            "B": {
                "allOf": [
                    {"$ref": "#/components/schemas/A"},
                    {"properties": {"v": {"type": "integer"}}},
                ]
            },
            "C": {
                "allOf": [
                    {"$ref": "#/components/schemas/B"},
                    {"required": ["v"]},
                ]
            },
        }
    )
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    b_field = next(field for field in _decl(ir, "B").fields if field.wire_name == "v")
    c_field = next(field for field in _decl(ir, "C").fields if field.wire_name == "v")

    assert b_field.incompatible_override is True
    assert c_field.required is True
    assert c_field.incompatible_override is False


def test_inheritance_ref_narrowed_to_a_subclass_is_compatible() -> None:
    """``Dog`` over ``Animal`` is a legal override once the base chain is consulted.

    Both sides are a bare ``RefType``; only the declaration map says one subclasses the
    other. Flagging it would put a suppression comment on a line mypy is happy with.
    """
    spec = _hier(
        {
            "Animal": {"type": "object", "properties": {"name": {"type": "string"}}},
            "Dog": {
                "allOf": [
                    {"$ref": "#/components/schemas/Animal"},
                    {"properties": {"breed": {"type": "string"}}},
                ]
            },
            "Keeper": {
                "type": "object",
                "required": ["pet"],
                "properties": {"pet": {"$ref": "#/components/schemas/Animal"}},
            },
            "DogKeeper": {
                "allOf": [
                    {"$ref": "#/components/schemas/Keeper"},
                    {
                        "required": ["pet"],
                        "properties": {"pet": {"$ref": "#/components/schemas/Dog"}},
                    },
                ]
            },
        }
    )
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    pet = next(field for field in _decl(ir, "DogKeeper").fields if field.wire_name == "pet")

    assert pet.type.annotation() == "Dog"
    assert pet.incompatible_override is False

    # the same override the other way round *is* incompatible
    schemas = spec["components"]["schemas"]
    schemas["Keeper"]["properties"]["pet"] = {"$ref": "#/components/schemas/Dog"}
    schemas["DogKeeper"]["allOf"][1]["properties"]["pet"] = {"$ref": "#/components/schemas/Animal"}
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    pet = next(field for field in _decl(ir, "DogKeeper").fields if field.wire_name == "pet")

    assert pet.incompatible_override is True

    # and a ``$ref`` to something that is not a class at all has no chain to walk
    schemas["Kind"] = {"type": "string", "enum": ["dog", "cat"]}
    schemas["DogKeeper"]["allOf"][1]["properties"]["pet"] = {"$ref": "#/components/schemas/Kind"}
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    pet = next(field for field in _decl(ir, "DogKeeper").fields if field.wire_name == "pet")

    assert pet.incompatible_override is True


def test_inheritance_integer_over_number_is_compatible() -> None:
    spec = _hier(
        {
            "P": {
                "type": "object",
                "required": ["v"],
                "properties": {"v": {"type": "number"}},
            },
            "C": {
                "allOf": [
                    {"$ref": "#/components/schemas/P"},
                    {"required": ["v"], "properties": {"v": {"type": "integer"}}},
                ]
            },
        }
    )
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    v = next(field for field in _decl(ir, "C").fields if field.wire_name == "v")

    assert v.type.annotation() == "int"
    assert v.incompatible_override is False
