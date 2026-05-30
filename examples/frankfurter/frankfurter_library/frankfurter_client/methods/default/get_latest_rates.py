"""Generated request method ``GetLatestRates``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from frankfurter_client.models.exchange_rates import ExchangeRates


@dataclass
class GetLatestRates(BaseMethod[ExchangeRates]):
    """Latest exchange rates

    The most recent reference rates available.
    """

    __url__ = "/v1/latest"
    __method__ = "GET"

    base: Query[Omittable[str]] = Omitted()
    symbols: Query[Omittable[list[str]]] = Omitted()
    amount: Query[Omittable[float]] = Omitted()
