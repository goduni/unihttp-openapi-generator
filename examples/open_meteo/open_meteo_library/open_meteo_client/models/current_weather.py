"""Generated declaration ``CurrentWeather``. Do not edit by hand."""

from __future__ import annotations

from msgspec import Struct


class CurrentWeather(Struct):
    """Current conditions (present when `current=` is requested)."""

    time: str
    interval: int
    temperature_2m: float
    wind_speed_10m: float
    weather_code: int
