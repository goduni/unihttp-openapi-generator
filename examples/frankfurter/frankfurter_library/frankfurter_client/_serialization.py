"""Serialization wiring (adaptix)."""

from adaptix import P, dumper
from unihttp.serializers.adaptix import DEFAULT_RETORT

from frankfurter_client._forward_refs import resolve_forward_refs
from frankfurter_client.methods import (
    GetLatestRates,
    GetRatesForDate,
    GetTimeSeries,
    GetTimeSeriesToNow,
)

resolve_forward_refs()

_RECIPE = [
    dumper(
        P[GetLatestRates].symbols,
        lambda v: ",".join(str(x) for x in v) if isinstance(v, list) else v,
    ),
    dumper(
        P[GetRatesForDate].symbols,
        lambda v: ",".join(str(x) for x in v) if isinstance(v, list) else v,
    ),
    dumper(
        P[GetTimeSeries].symbols,
        lambda v: ",".join(str(x) for x in v) if isinstance(v, list) else v,
    ),
    dumper(
        P[GetTimeSeriesToNow].symbols,
        lambda v: ",".join(str(x) for x in v) if isinstance(v, list) else v,
    ),
]
RETORT = DEFAULT_RETORT.extend(recipe=_RECIPE)

request_dumper = RETORT
response_loader = RETORT
