"""Serializer strategies (adaptix, pydantic, msgspec)."""

from __future__ import annotations

from unihttp_openapi_generator.config import Serializer
from unihttp_openapi_generator.render.serializers.adaptix import AdaptixStrategy
from unihttp_openapi_generator.render.serializers.base import SerializerStrategy
from unihttp_openapi_generator.render.serializers.msgspec import MsgspecStrategy
from unihttp_openapi_generator.render.serializers.pydantic import PydanticStrategy

_STRATEGIES: dict[Serializer, type[SerializerStrategy]] = {
    Serializer.ADAPTIX: AdaptixStrategy,
    Serializer.PYDANTIC: PydanticStrategy,
    Serializer.MSGSPEC: MsgspecStrategy,
}


def get_strategy(serializer: Serializer) -> SerializerStrategy:
    return _STRATEGIES[serializer]()


__all__ = ["SerializerStrategy", "get_strategy"]
