"""Generated request method ``GetTimeSeriesToNow``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path, Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from frankfurter_client.models.time_series_rates import TimeSeriesRates


@dataclass
class GetTimeSeriesToNow(BaseMethod[TimeSeriesRates]):
    """Time series of rates from a date to today

    Like the bounded range, but ends at the latest available day.
    """

    __url__ = "/v1/{start_date}.."
    __method__ = "GET"

    start_date: Path[str]
    base: Query[Omittable[str]] = Omitted()
    symbols: Query[Omittable[list[str]]] = Omitted()
    amount: Query[Omittable[float]] = Omitted()
