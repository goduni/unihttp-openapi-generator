"""Regression tests for real-world spec quirks (Max API, Java-generated specs)."""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import IRAlias, IRModel
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.serializers import get_strategy


def _build(spec: dict[str, Any]) -> IRDocument:
    return build_ir(spec, RefResolver(spec))


def test_discriminator_mapping_accepts_ref_objects() -> None:
    """Some generators emit mapping values as {"$ref": ...} objects or bare names."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "A": {"type": "object", "properties": {"kind": {"type": "string"}}},
                "B": {"type": "object", "properties": {"kind": {"type": "string"}}},
                "Event": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/A"},
                        {"$ref": "#/components/schemas/B"},
                    ],
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {
                            "a": {"$ref": "#/components/schemas/A"},  # object form
                            "b": "B",  # bare schema name
                        },
                    },
                },
            }
        },
    }
    event = next(d for d in _build(spec).declarations if d.name == "Event")
    assert isinstance(event, IRAlias)
    assert event.discriminator is not None
    assert event.discriminator.mapping == {"a": "A", "b": "B"}


def test_default_is_coerced_to_declared_type() -> None:
    """Specs often mistype defaults (e.g. integer field with a string default)."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "getX",
                    "tags": ["x"],
                    "parameters": [
                        {
                            "name": "count",
                            "in": "query",
                            "schema": {"type": "integer", "default": "20"},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Cfg": {
                    "type": "object",
                    "properties": {
                        "size": {"type": "integer", "default": "5"},
                        "ratio": {"type": "number", "default": "1.5"},
                        "enabled": {"type": "boolean", "default": "true"},
                    },
                }
            }
        },
    }
    ir = _build(spec)

    op = next(o for o in ir.operations if o.method_name == "get_x")
    count = next(p for p in op.parameters if p.name == "count")
    assert count.default == 20 and isinstance(count.default, int)

    cfg = next(d for d in ir.declarations if d.name == "Cfg")
    assert isinstance(cfg, IRModel)
    defaults = {f.name: f.default for f in cfg.fields}
    assert defaults["size"] == 5 and isinstance(defaults["size"], int)
    assert defaults["ratio"] == 1.5 and isinstance(defaults["ratio"], float)
    assert defaults["enabled"] is True


def test_simple_style_query_array_is_comma_joined() -> None:
    """`style: simple` on a query array (invalid but common) -> comma-separated."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {
            "/m": {
                "get": {
                    "operationId": "getMembers",
                    "tags": ["m"],
                    "parameters": [
                        {
                            "name": "user_ids",
                            "in": "query",
                            "style": "simple",
                            "schema": {"type": "array", "items": {"type": "integer"}},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    ir = _build(spec)
    module = get_strategy(Serializer.ADAPTIX).serialization_module(ir, "pkg")
    assert "P[GetMembers].user_ids" in module
    assert "','.join(str(x) for x in v)" in module  # comma-join dumper


def test_msgspec_required_aliased_field_ordering() -> None:
    """A required aliased field must sort before optional fields (msgspec ordering)."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "required": ["name", "photoUrls"],
                    "properties": {
                        "name": {"type": "string"},
                        "photoUrls": {"type": "array", "items": {"type": "string"}},
                        "id": {"type": "integer"},
                    },
                }
            }
        },
    }
    import msgspec

    from unihttp_openapi_generator.postprocess import format_python
    from unihttp_openapi_generator.render.models import render_models_module

    ir = _build(spec)
    source = format_python(render_models_module(ir, get_strategy(Serializer.MSGSPEC)))
    # exec-ing validates msgspec field ordering at class-definition time
    ns: dict[str, Any] = {}
    exec(compile(source, "models.py", "exec"), ns)  # noqa: S102
    pet = ns["Pet"](name="rex", photo_urls=["a"])
    assert msgspec.to_builtins(pet)["photoUrls"] == ["a"]


def test_allof_single_ref_wrapper_resolves_to_ref() -> None:
    """`{description, allOf: [{$ref: X}]}` (3.0 idiom) must resolve to X, not an empty model."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Color": {"type": "string", "enum": ["red", "green"]},
                "Item": {
                    "type": "object",
                    "required": ["color"],
                    "properties": {
                        # description-on-$ref wrapper
                        "color": {
                            "description": "the color",
                            "allOf": [{"$ref": "#/components/schemas/Color"}],
                        },
                    },
                },
            }
        },
    }
    ir = _build(spec)
    from unihttp_openapi_generator.ir.models import IREnum

    color = next(d for d in ir.declarations if d.name == "Color")
    assert isinstance(color, IREnum)  # stays a real enum
    item = next(d for d in ir.declarations if d.name == "Item")
    assert isinstance(item, IRModel)
    field = next(f for f in item.fields if f.name == "color")
    assert field.type.annotation() == "Color"  # references the enum, not an empty model
    # no spurious extra declaration (e.g. ItemColor / Color2) was created
    names = [d.name for d in ir.declarations]
    assert names.count("Color") == 1
    assert not any(n.startswith("ItemColor") or n == "Color2" for n in names)


def test_discriminated_base_becomes_union_of_subtypes() -> None:
    """A base with a discriminator `mapping` (subtypes via allOf) -> union + Literal tags."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Animal": {
                    "type": "object",
                    "required": ["kind"],
                    "properties": {"kind": {"type": "string"}, "name": {"type": "string"}},
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {
                            "cat": "#/components/schemas/Cat",
                            "dog": {"$ref": "#/components/schemas/Dog"},
                            "snake": "#/components/schemas/Snake",  # marker subtype (no own props)
                        },
                    },
                },
                "Cat": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Animal"},
                        {"properties": {"lives": {"type": "integer"}}},
                    ]
                },
                "Dog": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Animal"},
                        {"properties": {"breed": {"type": "string"}}},
                    ]
                },
                "Snake": {"allOf": [{"$ref": "#/components/schemas/Animal"}]},  # marker only
            }
        },
    }
    ir = _build(spec)
    from unihttp_openapi_generator.ir.types import UnionType

    animal = next(d for d in ir.declarations if d.name == "Animal")
    assert isinstance(animal, IRAlias)
    assert isinstance(animal.target, UnionType)
    assert animal.target.annotation() == "Cat | Dog | Snake"  # base is the union, not itself

    # each subtype carries the base fields + a single-value Literal discriminator
    cat = next(d for d in ir.declarations if d.name == "Cat")
    assert isinstance(cat, IRModel)
    kind = next(f for f in cat.fields if f.name == "kind")
    assert kind.type.annotation() == "Literal['cat']"
    assert kind.default == "cat"
    assert {f.name for f in cat.fields} >= {"kind", "name", "lives"}

    # marker subtype is a real model (not an alias back to Animal -> no recursive union)
    snake = next(d for d in ir.declarations if d.name == "Snake")
    assert isinstance(snake, IRModel)
    snake_kind = next(f for f in snake.fields if f.name == "kind")
    assert snake_kind.type.annotation() == "Literal['snake']"


def test_class_names_avoid_markers_and_method_collisions() -> None:
    """Model/method class names must not shadow marker imports or collide with each other."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {
            "/thing": {
                "get": {
                    "operationId": "getThing",  # class GetThing would collide with the model
                    "tags": ["x"],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/GetThing"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "File": {"type": "object", "properties": {"id": {"type": "string"}}},  # marker name
                "Query": {"type": "object", "properties": {"q": {"type": "string"}}},  # marker name
                "GetThing": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            }
        },
    }
    ir = _build(spec)
    decl_names = {d.name for d in ir.declarations}
    method_names = {o.class_name for o in ir.operations}

    # reserved marker names are never reused by a generated class
    assert "File" not in decl_names and "Query" not in decl_names
    assert any(d.name == "File2" for d in ir.declarations)

    # method class names never collide with declaration names
    assert decl_names.isdisjoint(method_names)


def test_incompatible_default_makes_field_optional() -> None:
    """A default that can't be a literal of the field type -> optional, value dropped."""
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Obj": {"type": "object", "properties": {"x": {"type": "integer"}}},
                "X": {"type": "object", "properties": {"p": {"type": "integer"}}},
                "Y": {"type": "object", "properties": {"q": {"type": "integer"}}},
                "Holder": {
                    "type": "object",
                    "properties": {
                        # default: null on an object ref (via the allOf-describe idiom)
                        "a": {"allOf": [{"$ref": "#/components/schemas/Obj"}], "default": None},
                        # string default on a union of objects
                        "b": {
                            "anyOf": [
                                {"$ref": "#/components/schemas/X"},
                                {"$ref": "#/components/schemas/Y"},
                            ],
                            "default": "auto",
                        },
                        # a compatible scalar default is preserved
                        "c": {"type": "string", "default": "hi"},
                    },
                },
            }
        },
    }
    from unihttp_openapi_generator.ir.types import OptionalType

    holder = next(d for d in _build(spec).declarations if d.name == "Holder")
    assert isinstance(holder, IRModel)
    fields = {f.name: f for f in holder.fields}

    assert isinstance(fields["a"].type, OptionalType)  # Obj -> Obj | None
    assert fields["a"].default is None
    assert fields["a"].type.annotation() == "Obj | None"

    assert isinstance(fields["b"].type, OptionalType)  # union -> union | None
    assert fields["b"].default is None  # the un-typable "auto" was dropped

    assert fields["c"].type.annotation() == "str"  # compatible default kept
    assert fields["c"].default == "hi"


def test_colliding_field_names_are_deduped_with_aliases() -> None:
    """Distinct wire names that sanitize to the same identifier (e.g. +1/-1) get deduped."""
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Reactions": {
                    "type": "object",
                    "required": ["+1", "-1"],
                    "properties": {
                        "+1": {"type": "integer"},
                        "-1": {"type": "integer"},
                        "confused": {"type": "integer"},
                    },
                }
            }
        },
    }
    reactions = next(d for d in _build(spec).declarations if d.name == "Reactions")
    assert isinstance(reactions, IRModel)
    names = [f.name for f in reactions.fields]
    assert len(names) == len(set(names))  # no duplicate field names
    by_wire = {f.wire_name: f for f in reactions.fields}
    assert by_wire["+1"].name == "_1"
    assert by_wire["-1"].name == "_12"  # deduped
    # both keep their wire alias so serialization stays correct
    assert by_wire["+1"].needs_alias and by_wire["-1"].needs_alias
