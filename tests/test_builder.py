"""Tests for the OpenAPI -> IR builder."""

from __future__ import annotations

from typing import Any

import pytest

from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import IRAlias, IREnum, IRModel
from unihttp_openapi_generator.ir.operations import BodyKind, ParamLocation
from unihttp_openapi_generator.ir.types import (
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


def test_xquik_search_security_and_parameters() -> None:
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "Xquik API", "version": "1.0.0"},
        "servers": [{"url": "https://xquik.com"}],
        "paths": {
            "/api/v1/x/tweets/search": {
                "get": {
                    "operationId": "searchTweets",
                    "tags": ["x"],
                    "security": [{"apiKey": []}, {"oauthBearer": []}, {}],
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "queryType",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["Latest", "Top"],
                                "default": "Latest",
                            },
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer", "default": 20, "maximum": 200},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "securitySchemes": {
                "apiKey": {"type": "apiKey", "in": "header", "name": "x-api-key"},
                "oauthBearer": {"type": "http", "scheme": "bearer"},
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec))
    scheme = ir.security_schemes["apiKey"]
    op = next(o for o in ir.operations if o.method_name == "search_tweets")
    params = {p.name: p for p in op.parameters}

    assert ir.base_url == "https://xquik.com"
    assert scheme.kind == "apiKey"
    assert scheme.location == "header"
    assert scheme.parameter_name == "x-api-key"
    assert op.path == "/api/v1/x/tweets/search"
    assert op.security == [{"apiKey": []}, {"oauthBearer": []}, {}]
    assert params["q"].location is ParamLocation.QUERY
    assert params["q"].required is True
    assert params["query_type"].wire_name == "queryType"
    assert params["query_type"].needs_alias is True
    assert params["limit"].default == 20
    assert params["limit"].has_default is True


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
