"""Generated declaration ``HourlyForecast``. Do not edit by hand."""

from __future__ import annotations

from msgspec import Struct


class HourlyForecast(Struct):
    """Parallel arrays of hourly values (present when `hourly=` is requested)."""

    time: list[str]
    temperature_2m: list[float]
