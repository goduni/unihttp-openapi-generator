"""Generated declaration ``Forecast``. Do not edit by hand."""

from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec
from msgspec import Struct

if TYPE_CHECKING:
    from open_meteo_client.models.current_weather import CurrentWeather
    from open_meteo_client.models.hourly_forecast import HourlyForecast


class Forecast(Struct):
    """Forecast response for one coordinate."""

    latitude: float
    longitude: float
    timezone: str | None = msgspec.field(default=None)
    utc_offset_seconds: int | None = msgspec.field(default=None)
    elevation: float | None = msgspec.field(default=None)
    current: CurrentWeather | None = msgspec.field(default=None)
    hourly: HourlyForecast | None = msgspec.field(default=None)
