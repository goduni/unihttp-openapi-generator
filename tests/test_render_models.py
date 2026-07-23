"""Tests for model rendering across serializer strategies."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.ir.builder import build_ir
from unihttp_openapi_generator.postprocess import format_python
from unihttp_openapi_generator.refs import RefResolver
from unihttp_openapi_generator.render.models import render_models_module
from unihttp_openapi_generator.render.serializers import get_strategy


def _render(spec: dict[str, Any], serializer: Serializer) -> str:
    ir = build_ir(spec, RefResolver(spec))
    strategy = get_strategy(serializer)
    return format_python(render_models_module(ir, strategy), filename="models.py")


def _load(source: str, tmp_path: Path, name: str) -> ModuleType:
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize(
    "serializer", [Serializer.ADAPTIX, Serializer.PYDANTIC, Serializer.MSGSPEC]
)
def test_models_module_imports(
    sample_spec: dict[str, Any], serializer: Serializer, tmp_path: Path
) -> None:
    source = _render(sample_spec, serializer)
    module = _load(source, tmp_path, f"genmodels_{serializer.value}")
    assert hasattr(module, "Pet")
    assert hasattr(module, "NewPet")
    assert hasattr(module, "PetKind")
    assert hasattr(module, "Animal")


def test_adaptix_models_are_dataclasses(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    import dataclasses

    module = _load(_render(sample_spec, Serializer.ADAPTIX), tmp_path, "genmodels_ad")
    assert dataclasses.is_dataclass(module.Pet)
    pet_cls: Any = module.Pet
    pet = pet_cls(id=1, name="Rex")
    assert pet.created_at is None


def test_pydantic_models_use_aliases(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    module = _load(_render(sample_spec, Serializer.PYDANTIC), tmp_path, "genmodels_pyd")
    pet = module.Pet(id=1, name="Rex", createdAt="2020-01-01T00:00:00Z")
    assert pet.created_at is not None
    dumped = pet.model_dump(by_alias=True, exclude_none=True)
    assert "createdAt" in dumped


def test_msgspec_models_use_field_names(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    import msgspec

    module = _load(_render(sample_spec, Serializer.MSGSPEC), tmp_path, "genmodels_ms")
    pet = module.Pet(id=1, name="Rex", created_at=None)
    encoded = msgspec.to_builtins(pet)
    assert "createdAt" in encoded


# -- item 4: docstring paragraphs ---------------------------------------------


def test_docstring_single_short_paragraph_is_one_line() -> None:
    from unihttp_openapi_generator.render.serializers.base import docstring

    assert docstring("Hello world.", "    ") == '    """Hello world."""\n'


def test_docstring_multiple_paragraphs() -> None:
    from unihttp_openapi_generator.render.serializers.base import docstring

    out = docstring("Summary.\n\nLonger description text.", "    ")
    lines = out.splitlines()
    assert lines[0] == '    """Summary.'
    # blank line separating the two paragraphs
    assert "" in lines
    assert any("Longer description text." in line for line in lines)
    assert lines[-1] == '    """'


# -- item 7: msgspec constraints ----------------------------------------------


_CONSTRAINT_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "S", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "C": {
                "type": "object",
                "required": ["age", "code"],
                "properties": {
                    "age": {"type": "integer", "minimum": 0, "maximum": 120},
                    "code": {"type": "string", "minLength": 3, "maxLength": 4},
                },
            }
        }
    },
}


def test_msgspec_constraints_emit_meta(tmp_path: Path) -> None:
    import msgspec

    source = _render(_CONSTRAINT_SPEC, Serializer.MSGSPEC)
    assert "Annotated[" in source
    assert "Meta(" in source
    assert "ge=0" in source
    assert "le=120" in source
    assert "min_length=3" in source
    module = _load(source, tmp_path, "genmodels_msc")
    # valid value round-trips
    obj = module.C(age=30, code="abcd")
    assert msgspec.to_builtins(obj)["age"] == 30


def test_pydantic_constraints_still_emit_field(tmp_path: Path) -> None:
    source = _render(_CONSTRAINT_SPEC, Serializer.PYDANTIC)
    assert "Field(" in source
    assert "ge=0" in source
    assert "le=120" in source


def test_omitted_optional_mode(sample_spec: dict[str, Any], tmp_path: Path) -> None:
    from unihttp_openapi_generator.ir.builder import build_ir
    from unihttp_openapi_generator.refs import RefResolver

    ir = build_ir(sample_spec, RefResolver(sample_spec), omit_optionals=True)
    source = format_python(
        render_models_module(ir, get_strategy(Serializer.ADAPTIX)), filename="models.py"
    )
    assert "from unihttp.omitted import Omittable, Omitted" in source
    assert "created_at: Omittable[datetime] = Omitted()" in source
    # nullable + optional keeps the `| None` inside Omittable
    assert "tag: Omittable[str | None] = Omitted()" in source
    # required field stays required (no Omittable)
    assert "id: int\n" in source
    module = _load(source, tmp_path, "genmodels_omit")
    pet = module.Pet(id=1, name="x")
    from unihttp.omitted import Omitted

    assert isinstance(pet.created_at, Omitted)


# -- bug 1: a model field named ``field``/``Field`` must not shadow the helper -------


_FIELD_NAMED_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "S", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "Shadow": {
                "type": "object",
                "properties": {
                    # list defaults force a ``field(default_factory=...)`` call, which is
                    # where shadowing by a field named ``field`` actually bites.
                    "field": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["x"],
                    },
                    "Field": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["y"],
                    },
                    "other": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["z"],
                    },
                },
            }
        }
    },
}


@pytest.mark.parametrize(
    "serializer", [Serializer.ADAPTIX, Serializer.PYDANTIC, Serializer.MSGSPEC]
)
def test_field_named_field_does_not_shadow_helper(serializer: Serializer, tmp_path: Path) -> None:
    source = _render(_FIELD_NAMED_SPEC, serializer)
    # The in-body helper call must be module-qualified so the class attribute can't
    # shadow it (msgspec.field / dataclasses.field / pydantic.Field).
    module = _load(source, tmp_path, f"genmodels_shadow_{serializer.value}")
    assert hasattr(module, "Shadow")
    if serializer is Serializer.MSGSPEC:
        assert "msgspec.field(" in source
        assert "import msgspec\n" in source
    elif serializer is Serializer.ADAPTIX:
        assert "dataclasses.field(" in source
        assert "import dataclasses\n" in source
    else:
        assert "pydantic.Field(" in source
        assert "import pydantic\n" in source


# -- bug 2: pydantic forbids leading-underscore field names ---------------------------


_LEADING_UNDERSCORE_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "S", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "Reactions": {
                "type": "object",
                "properties": {
                    "+1": {"type": "integer"},
                    "-1": {"type": "integer"},
                },
            }
        }
    },
}


def test_pydantic_leading_underscore_field_renamed_and_aliased(tmp_path: Path) -> None:
    source = _render(_LEADING_UNDERSCORE_SPEC, Serializer.PYDANTIC)
    # No field declaration may start with an underscore (pydantic raises NameError).
    for line in source.splitlines():
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith(("#", '"', "model_config", "class")):
            assert not stripped.startswith("_"), stripped
    module = _load(source, tmp_path, "genmodels_underscore")
    obj = module.Reactions.model_validate({"+1": 3, "-1": 1})
    dumped = obj.model_dump(by_alias=True, exclude_none=True)
    assert dumped == {"+1": 3, "-1": 1}


# -- bug 3: pydantic field name collides with a BaseModel member ----------------------


_RESERVED_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "S", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "Webhook": {
                "type": "object",
                "properties": {
                    "validate": {"type": "boolean"},
                    "model_dump": {"type": "string"},
                },
            }
        }
    },
}


def test_pydantic_reserved_field_name_renamed_and_aliased(tmp_path: Path) -> None:
    source = _render(_RESERVED_SPEC, Serializer.PYDANTIC)
    assert "validate_:" in source
    assert "validate" in source  # alias preserved
    assert "field_model_dump:" in source
    module = _load(source, tmp_path, "genmodels_reserved")
    obj = module.Webhook.model_validate({"validate": True, "model_dump": "x"})
    assert obj.validate_ is True
    dumped = obj.model_dump(by_alias=True, exclude_none=True)
    assert dumped == {"validate": True, "model_dump": "x"}


# -- bug 5: pydantic discriminated union with duplicate tag values --------------------


_DUP_TAG_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "S", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "A": {
                "type": "object",
                "required": ["type"],
                "properties": {"type": {"const": "message"}, "a": {"type": "string"}},
            },
            "B": {
                "type": "object",
                "required": ["type"],
                "properties": {"type": {"const": "message"}, "b": {"type": "string"}},
            },
            "U": {
                "oneOf": [
                    {"$ref": "#/components/schemas/A"},
                    {"$ref": "#/components/schemas/B"},
                ],
                "discriminator": {"propertyName": "type"},
            },
        }
    },
}


def test_pydantic_duplicate_discriminator_falls_back_to_plain_union(tmp_path: Path) -> None:
    source = _render(_DUP_TAG_SPEC, Serializer.PYDANTIC)
    # Duplicate tag values -> plain union, not Annotated[..., Field(discriminator=...)].
    assert "type U = A | B" in source
    assert "discriminator=" not in source
    module = _load(source, tmp_path, "genmodels_duptag")
    assert hasattr(module, "U")


def test_docstring_with_backslash_is_raw_and_warning_free() -> None:
    import warnings

    from unihttp_openapi_generator.render.serializers.base import docstring

    out = docstring("send it via curl \\ -H 'X: 1'", "    ")
    assert out.startswith('    r"""')  # raw string preserves the backslash
    src = f"def f():\n{out}    pass\n"
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # SyntaxWarning -> error
        compile(src, "t.py", "exec")  # must not raise


# -- inheritance mode ---------------------------------------------------------------


_INHERITED_SPEC: dict[str, Any] = {
    "openapi": "3.0.0",
    "info": {"title": "I", "version": "1.0.0"},
    "paths": {},
    "components": {
        "schemas": {
            "Button": {
                "type": "object",
                "required": ["type", "text"],
                "properties": {"type": {"type": "string"}, "text": {"type": "string"}},
                "discriminator": {
                    "propertyName": "type",
                    "mapping": {"callback": "#/components/schemas/CallbackButton"},
                },
            },
            "CallbackButton": {
                "allOf": [
                    {"$ref": "#/components/schemas/Button"},
                    {"required": ["payload"], "properties": {"payload": {"type": "string"}}},
                ]
            },
        }
    },
}


@pytest.mark.parametrize(
    "serializer", [Serializer.ADAPTIX, Serializer.PYDANTIC, Serializer.MSGSPEC]
)
def test_inherited_models_subclass_their_base(serializer: Serializer, tmp_path: Path) -> None:
    ir = build_ir(_INHERITED_SPEC, RefResolver(_INHERITED_SPEC), inheritance=True)
    source = format_python(render_models_module(ir, get_strategy(serializer)), filename="models.py")
    assert "class CallbackButton(Button" in source
    module = _load(source, tmp_path, f"genmodels_inherit_{serializer.value}")
    assert issubclass(module.CallbackButton, module.Button)
    # A subclass pinning an inherited field to a default while adding a required one
    # of its own only works with keyword-only construction.
    button = module.CallbackButton(text="hi", payload="p")
    assert button.type == "callback"
    assert button.text == "hi"


def test_inherited_adaptix_models_are_kw_only() -> None:
    ir = build_ir(_INHERITED_SPEC, RefResolver(_INHERITED_SPEC), inheritance=True)
    source = render_models_module(ir, get_strategy(Serializer.ADAPTIX))
    assert "@dataclass(kw_only=True)\nclass Button:" in source
    assert "@dataclass(kw_only=True)\nclass CallbackButton(Button):" in source


def test_only_hierarchy_members_become_kw_only() -> None:
    """One ``allOf`` subtype must not silently break every other model's constructor.

    ``kw_only`` is what lets a subclass pin an inherited field to a default while
    adding required fields of its own -- a constraint that exists only inside a
    hierarchy. Models outside one keep positional construction.
    """
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "I", "version": "1.0.0"},
        "paths": {},
        "components": {
            "schemas": {
                **_INHERITED_SPEC["components"]["schemas"],
                "Unrelated": {
                    "type": "object",
                    "required": ["n"],
                    "properties": {"n": {"type": "string"}},
                },
            }
        },
    }
    ir = build_ir(spec, RefResolver(spec), inheritance=True)
    source = render_models_module(ir, get_strategy(Serializer.ADAPTIX))
    assert "@dataclass\nclass Unrelated:" in source
    assert "@dataclass(kw_only=True)\nclass Button:" in source


def test_models_without_inheritance_keep_positional_dataclasses() -> None:
    ir = build_ir(_INHERITED_SPEC, RefResolver(_INHERITED_SPEC))
    source = render_models_module(ir, get_strategy(Serializer.ADAPTIX))
    assert "@dataclass(kw_only=True)" not in source


def test_discriminated_base_class_keeps_its_mapping_visible() -> None:
    """A base kept as a class must not swallow the discriminator it declares.

    No serializer resolves a concrete subtype from a base-class annotation on its own,
    so the mapping is the one thing a reader needs to wire tagged decoding by hand.
    Dropping it would leave that information nowhere in the generated package.
    """
    ir = build_ir(_INHERITED_SPEC, RefResolver(_INHERITED_SPEC), inheritance=True)
    source = render_models_module(ir, get_strategy(Serializer.ADAPTIX))
    assert "# discriminator: type (callback=CallbackButton)" in source
