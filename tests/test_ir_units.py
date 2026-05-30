"""Unit coverage for small IR helpers (imports/refs over additional_properties,
JSON-body type collection, optional() over a None-bearing union, name registry)."""

from __future__ import annotations

from unihttp_openapi_generator.ir.models import IRModel
from unihttp_openapi_generator.ir.naming import NameRegistry
from unihttp_openapi_generator.ir.operations import (
    BodyKind,
    IRBody,
    IROperation,
)
from unihttp_openapi_generator.ir.types import (
    DATETIME,
    NONE,
    STR,
    Import,
    RefType,
    UnionType,
    optional,
)


def test_model_additional_properties_imports_and_refs() -> None:
    m = IRModel(name="M", additional_properties=DATETIME)
    assert Import("datetime", "datetime") in m.imports()

    m2 = IRModel(name="M2", additional_properties=RefType("Other"))
    assert m2.referenced_models() == {"Other"}


def test_operation_json_body_imports_and_refs() -> None:
    body = IRBody(
        kind=BodyKind.JSON,
        required=True,
        content_type="application/json",
        json_type=DATETIME,
    )
    op = IROperation(
        operation_id="x",
        class_name="X",
        method_name="x",
        http_method="POST",
        path="/x",
        tag="t",
        body=body,
    )
    assert Import("datetime", "datetime") in op.imports()

    body2 = IRBody(
        kind=BodyKind.JSON,
        required=True,
        content_type="application/json",
        json_type=RefType("Pet"),
    )
    op2 = IROperation(
        operation_id="y",
        class_name="Y",
        method_name="y",
        http_method="POST",
        path="/y",
        tag="t",
        body=body2,
    )
    assert op2.referenced_models() == {"Pet"}


def test_optional_over_union_with_none_is_unchanged() -> None:
    union = UnionType((STR, NONE))
    assert optional(union) is union


def test_name_registry_contains() -> None:
    reg = NameRegistry()
    reg.reserve("Foo")
    assert "Foo" in reg
    assert "Bar" not in reg
