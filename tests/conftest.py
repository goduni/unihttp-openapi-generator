"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from unihttp_openapi_generator.tooling import ruff_executable


@pytest.fixture(autouse=True)
def _reset_tool_lookup_cache() -> Iterator[None]:
    """Keep a monkeypatched ruff lookup in one test from leaking into the next."""
    ruff_executable.cache_clear()
    yield
    ruff_executable.cache_clear()


@pytest.fixture
def sample_spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Sample", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com/v1"}],
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"},
                        },
                        {
                            "name": "tags",
                            "in": "query",
                            "style": "form",
                            "explode": False,
                            "schema": {"type": "array", "items": {"type": "string"}},
                        },
                        {
                            "name": "X-Request-ID",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Pet"},
                                    }
                                }
                            },
                        },
                        "default": {
                            "description": "error",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                },
                "post": {
                    "operationId": "createPet",
                    "tags": ["pets"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/NewPet"}}
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "created",
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}
                            },
                        }
                    },
                },
            },
            "/pets/{petId}/photo": {
                "post": {
                    "operationId": "uploadPhoto",
                    "tags": ["pets"],
                    "parameters": [{"name": "petId", "in": "path", "schema": {"type": "integer"}}],
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["file"],
                                    "properties": {
                                        "file": {"type": "string", "format": "binary"},
                                        "caption": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"204": {"description": "no content"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
                "bearer": {"type": "http", "scheme": "bearer"},
            },
            "schemas": {
                "Pet": {
                    "type": "object",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "status": {"type": "string", "enum": ["available", "sold"]},
                        "createdAt": {"type": "string", "format": "date-time"},
                        "tag": {"type": ["string", "null"]},
                    },
                },
                "NewPet": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Pet"},
                        {
                            "type": "object",
                            "properties": {"ownerId": {"type": "integer"}},
                        },
                    ]
                },
                "PetKind": {"type": "string", "enum": ["cat", "dog"]},
                "Animal": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/Pet"},
                        {"$ref": "#/components/schemas/NewPet"},
                    ],
                    "discriminator": {
                        "propertyName": "kind",
                        "mapping": {
                            "pet": "#/components/schemas/Pet",
                            "new": "#/components/schemas/NewPet",
                        },
                    },
                },
                "Metadata": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "Error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"type": "integer"},
                        "message": {"type": "string"},
                    },
                },
            },
        },
    }


@pytest.fixture
def hierarchy_spec() -> dict[str, Any]:
    """A spec whose ``allOf`` shapes all land differently under ``--inheritance``.

    Every schema here stands for one rule the mode has to get right, and each was a
    real defect at some point: a discriminated base that keeps its own properties, a
    tag the base types as an enum (so the subtype's ``Literal`` is not assignable),
    restatements that only add prose / relax to nullable / change a default, wire names
    that snake-case onto an inherited identifier, a three-level chain, a base whose own
    body refers back to its subtype, and narrowings only the base chain or the numeric
    tower can justify.
    """
    return {
        "openapi": "3.1.0",
        "info": {"title": "Hierarchy", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/buttons": {
                "post": {
                    "operationId": "createButton",
                    "tags": ["buttons"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CallbackButton"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Button"}
                                }
                            },
                        }
                    },
                }
            },
            "/leaves": {
                "get": {
                    "operationId": "listLeaves",
                    "tags": ["leaves"],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Leaf"},
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/nodes": {
                "get": {
                    "operationId": "getNode",
                    "tags": ["nodes"],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/NodeLeaf"}
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "ButtonKind": {"type": "string", "enum": ["callback", "link"]},
                "Button": {
                    "type": "object",
                    "description": "A discriminated base with properties of its own.",
                    "required": ["type", "text"],
                    "properties": {
                        # the idiomatic tag: a $ref to an enum, which no Literal narrows
                        "type": {"$ref": "#/components/schemas/ButtonKind"},
                        "text": {"type": "string"},
                        "packSize": {"type": "integer"},
                        "note": {"type": "string", "default": "base"},
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
                            "type": "object",
                            "required": ["payload"],
                            "properties": {
                                "payload": {"type": "string"},
                                # snake-cases onto the inherited ``pack_size``
                                "pack_size": {"type": "string"},
                                # snake-cases onto the inherited ``type``
                                "Type": {"type": "string"},
                                # restated only to attach prose
                                "text": {"type": "string", "description": "Visible label."},
                            },
                        },
                    ]
                },
                "LinkButton": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Button"},
                        {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                # relaxed to nullable: unsound as an override
                                "text": {"type": "string", "nullable": True},
                                # changes only the default: a legal override
                                "note": {"type": "string", "default": "link"},
                            },
                        },
                    ]
                },
                "Base": {
                    "type": "object",
                    "required": ["shared"],
                    "properties": {"shared": {"type": "string"}, "wide": {}},
                },
                "Middle": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Base"},
                        {"properties": {"mid": {"type": "string"}}},
                    ]
                },
                "Leaf": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Middle"},
                        {
                            "properties": {
                                # re-declares the *grandparent*'s fields
                                "shared": {"type": "string"},
                                "wide": {"type": "integer"},
                            }
                        },
                    ]
                },
                "Node": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        # the base's own body refers back to its subtype
                        "child": {"$ref": "#/components/schemas/NodeLeaf"},
                    },
                },
                "NodeLeaf": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Node"},
                        {"properties": {"value": {"type": "string"}}},
                    ]
                },
                # A subtype narrowing a property to a schema that subclasses the base's:
                # nothing in either annotation says ``Pet`` is a ``Creature``, so the
                # override reads as incompatible unless the base chain is consulted.
                "Creature": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                },
                "Pet": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Creature"},
                        {"properties": {"tame": {"type": "boolean"}}},
                    ]
                },
                "Owner": {
                    "type": "object",
                    "required": ["companion", "score"],
                    "properties": {
                        "companion": {"$ref": "#/components/schemas/Creature"},
                        "score": {"type": "number"},
                    },
                },
                "PetOwner": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Owner"},
                        {
                            "type": "object",
                            "required": ["companion", "score"],
                            "properties": {
                                "companion": {"$ref": "#/components/schemas/Pet"},
                                # the numeric tower: ``integer`` narrows ``number``
                                "score": {"type": "integer"},
                            },
                        },
                    ]
                },
            }
        },
    }
