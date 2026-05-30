"""Unit coverage for renderer helpers: docstrings, empty/described declarations,
query delimiters, discriminated-union guards, module stems and method fields."""

from __future__ import annotations

from typing import Any

from unihttp_openapi_generator.ir.document import IRDocument
from unihttp_openapi_generator.ir.models import (
    Discriminator,
    IRAlias,
    IREnum,
    IRField,
    IRModel,
)
from unihttp_openapi_generator.ir.operations import (
    BodyKind,
    IRBody,
    IROperation,
    IRParameter,
    ParamLocation,
)
from unihttp_openapi_generator.ir.types import (
    STR,
    ListType,
    LiteralType,
    RefType,
    UnionType,
)
from unihttp_openapi_generator.render.file_layout import (
    _module_stem,
    build_layout_plan,
    render_forward_refs_module,
)
from unihttp_openapi_generator.render.methods import operation_fields, render_method_class
from unihttp_openapi_generator.render.serializers.adaptix import AdaptixStrategy
from unihttp_openapi_generator.render.serializers.base import docstring
from unihttp_openapi_generator.render.serializers.msgspec import MsgspecStrategy
from unihttp_openapi_generator.render.serializers.pydantic import PydanticStrategy

# -- docstring edge paths -----------------------------------------------------


def test_docstring_whitespace_only_returns_empty() -> None:
    assert docstring("   ", "    ") == ""


def test_docstring_single_paragraph_trailing_quote_is_padded() -> None:
    assert docstring('say "hi"', "    ") == '    """say "hi" """\n'


# -- enum / model renderers with descriptions and empty bodies ----------------


def test_render_enum_with_description_and_no_members() -> None:
    out = AdaptixStrategy().render_enum(
        IREnum(name="E", base="str", members=[], description="An enum.")
    )
    assert '"""An enum."""' in out
    assert "pass" in out


def test_adaptix_model_description_and_empty() -> None:
    described = AdaptixStrategy().render_model(IRModel(name="M", description="A model."))
    assert '"""A model."""' in described
    empty = AdaptixStrategy().render_model(IRModel(name="Empty"))
    assert "pass" in empty


def test_msgspec_model_description_and_empty() -> None:
    described = MsgspecStrategy().render_model(IRModel(name="M", description="A model."))
    assert '"""A model."""' in described
    empty = MsgspecStrategy().render_model(IRModel(name="Empty"))
    assert "pass" in empty


def test_pydantic_model_description() -> None:
    described = PydanticStrategy().render_model(IRModel(name="M", description="A model."))
    assert '"""A model."""' in described


# -- adaptix query delimiter --------------------------------------------------


def _query_param(style: str | None, explode: bool | None = None) -> IRParameter:
    return IRParameter(
        name="x",
        wire_name="x",
        location=ParamLocation.QUERY,
        type=ListType(STR),
        required=False,
        style=style,
        explode=explode,
    )


def test_adaptix_query_delimiter_styles() -> None:
    assert AdaptixStrategy._query_delimiter(_query_param("spaceDelimited")) == " "
    assert AdaptixStrategy._query_delimiter(_query_param("pipeDelimited")) == "|"
    # form + explode (the default) -> no delimiter joining
    assert AdaptixStrategy._query_delimiter(_query_param("form", explode=True)) is None


# -- pydantic discriminated-union guards --------------------------------------


def test_pydantic_discriminated_union_guards() -> None:
    strategy = PydanticStrategy()
    disc = Discriminator(property_name="kind")

    # member is not a RefType
    not_ref = IRAlias(name="U1", target=UnionType((STR,)), discriminator=disc)
    assert strategy._discriminated_union(not_ref) is None

    # member references an unknown model
    unknown = IRAlias(name="U2", target=UnionType((RefType("Missing"),)), discriminator=disc)
    assert strategy._discriminated_union(unknown) is None

    # tag field is a multi-value Literal -> not a clean single-tag discriminator
    strategy.models_by_name = {
        "Foo": IRModel(
            name="Foo",
            fields=[
                IRField(
                    name="kind",
                    wire_name="kind",
                    type=LiteralType(("a", "b")),
                    required=True,
                )
            ],
        )
    }
    multi = IRAlias(name="U3", target=UnionType((RefType("Foo"),)), discriminator=disc)
    assert strategy._discriminated_union(multi) is None


# -- file-layout module stems / empty forward-refs ----------------------------


def test_module_stem_non_identifier_is_prefixed() -> None:
    assert _module_stem("123") == "_123"


def test_render_forward_refs_for_empty_document() -> None:
    doc = IRDocument(title="T", version="1.0.0", base_url=None)
    plan = build_layout_plan(doc)
    out = render_forward_refs_module(doc, AdaptixStrategy(), "pkg", plan)
    assert "No generated declarations or methods need forward-ref resolution." in out


# -- method rendering: list defaults (field factory) / deprecated / array body -


def _op(**kwargs: Any) -> IROperation:
    base: dict[str, Any] = {
        "operation_id": "x",
        "class_name": "X",
        "method_name": "x",
        "http_method": "GET",
        "path": "/x",
        "tag": "t",
    }
    base.update(kwargs)
    return IROperation(**base)


def test_method_with_list_default_uses_field_factory() -> None:
    op = _op(
        parameters=[
            IRParameter(
                name="tags",
                wire_name="tags",
                location=ParamLocation.QUERY,
                type=ListType(STR),
                required=False,
                default=["a"],
                has_default=True,
            )
        ],
    )
    code, imports = render_method_class(op)
    assert "field(default_factory=lambda: ['a'])" in code
    assert any(imp.module == "dataclasses" and imp.name == "field" for imp in imports)


def test_method_deprecated_note_in_docstring() -> None:
    op = _op(summary="Does a thing.", deprecated=True)
    code, _ = render_method_class(op)
    assert "Deprecated." in code


def test_non_object_json_body_becomes_single_body_field() -> None:
    op = _op(
        http_method="POST",
        body=IRBody(
            kind=BodyKind.JSON,
            required=True,
            content_type="application/json",
            json_type=ListType(STR),
        ),
    )
    fields = operation_fields(op)
    assert [f.py_name for f in fields] == ["body"]
    assert fields[0].marker == "Body"
    assert fields[0].inner == "list[str]"
