"""Generated request method ``GetCurrencies``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.method import BaseMethod

from frankfurter_client.models.currency_map import CurrencyMap


@dataclass
class GetCurrencies(BaseMethod[CurrencyMap]):
    """Supported currencies

    A map of supported currency codes to their display names.
    """

    __url__ = "/v1/currencies"
    __method__ = "GET"
