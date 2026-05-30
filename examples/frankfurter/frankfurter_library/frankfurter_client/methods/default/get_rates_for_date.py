"""Generated request method ``GetRatesForDate``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path, Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from frankfurter_client.models.exchange_rates import ExchangeRates


@dataclass
class GetRatesForDate(BaseMethod[ExchangeRates]):
    """Historical exchange rates for a date

    Reference rates for a specific day (YYYY-MM-DD). Rates are published on working days
    around 16:00 CET; for weekends/holidays the API returns the most recent prior
    working day.
    """

    __url__ = "/v1/{date}"
    __method__ = "GET"

    date: Path[str]
    base: Query[Omittable[str]] = Omitted()
    symbols: Query[Omittable[list[str]]] = Omitted()
    amount: Query[Omittable[float]] = Omitted()
