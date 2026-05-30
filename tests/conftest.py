"""Shared fixtures."""

from __future__ import annotations

from typing import Any

import pytest


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
