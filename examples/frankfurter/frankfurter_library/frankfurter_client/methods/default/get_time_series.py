"""Generated request method ``GetTimeSeries``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path, Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from frankfurter_client.models.time_series_rates import TimeSeriesRates


@dataclass
class GetTimeSeries(BaseMethod[TimeSeriesRates]):
    """Time series of rates over a date range

    Reference rates for every working day in [start_date, end_date]. The API snaps the
    bounds to the nearest published working days.
    """

    __url__ = "/v1/{start_date}..{end_date}"
    __method__ = "GET"

    start_date: Path[str]
    """ISO start date, e.g. 2020-01-01."""
    end_date: Path[str]
    """ISO end date, e.g. 2020-01-31."""
    base: Query[Omittable[str]] = Omitted()
    """Base currency to quote against (default EUR)."""
    symbols: Query[Omittable[list[str]]] = Omitted()
    """Limit the response to these target currencies."""
    amount: Query[Omittable[float]] = Omitted()
    """Amount to convert (default 1)."""
