"""Generated request method ``GetForecast``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from open_meteo_client.models.forecast import Forecast


@dataclass
class GetForecast(BaseMethod[Forecast]):
    """Weather forecast for a coordinate

    Current conditions and/or an hourly forecast for a latitude/longitude.
    """

    __url__ = "/v1/forecast"
    __method__ = "GET"

    latitude: Query[float]
    """Latitude in decimal degrees."""
    longitude: Query[float]
    """Longitude in decimal degrees."""
    current: Query[Omittable[list[str]]] = Omitted()
    """Current-condition variables to return."""
    hourly: Query[Omittable[list[str]]] = Omitted()
    """Hourly variables to return."""
    timezone: Query[Omittable[str]] = Omitted()
    """Timezone name (e.g. UTC) or "auto"."""
    forecast_days: Query[Omittable[int]] = Omitted()
    """Number of forecast days (1-16)."""
