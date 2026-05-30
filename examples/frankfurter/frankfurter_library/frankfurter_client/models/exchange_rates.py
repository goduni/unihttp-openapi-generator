"""Generated declaration ``ExchangeRates``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class ExchangeRates:
    """Reference rates for a base currency on a given date."""

    amount: float
    base: str
    date: date
    rates: dict[str, float]
