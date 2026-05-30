"""Tests for identifier naming utilities."""

from __future__ import annotations

import pytest

from unihttp_openapi_generator.ir.naming import (
    NameRegistry,
    class_name,
    field_name,
    method_name,
    to_pascal_case,
    to_snake_case,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("userName", "user_name"),
        ("HTTPResponse", "http_response"),
        ("user-id", "user_id"),
        ("X-Request-ID", "x_request_id"),
        ("already_snake", "already_snake"),
        ("user.name", "user_name"),
        ("getUserByID", "get_user_by_id"),
    ],
)
def test_to_snake_case(raw: str, expected: str) -> None:
    assert to_snake_case(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("user_name", "UserName"),
        ("pet-store", "PetStore"),
        ("getUser", "GetUser"),
    ],
)
def test_to_pascal_case(raw: str, expected: str) -> None:
    assert to_pascal_case(raw) == expected


def test_field_name_handles_keyword() -> None:
    assert field_name("class") == "class_"
    assert field_name("for") == "for_"


def test_field_name_handles_leading_digit() -> None:
    assert field_name("2fa") == "_2fa"


def test_class_name_from_ref() -> None:
    assert class_name("PetStore") == "PetStore"
    assert class_name("pet_store") == "PetStore"


def test_method_name() -> None:
    assert method_name("getUserById") == "get_user_by_id"


def test_name_registry_dedup() -> None:
    reg = NameRegistry()
    assert reg.reserve("User") == "User"
    assert reg.reserve("User") == "User2"
    assert reg.reserve("User") == "User3"
