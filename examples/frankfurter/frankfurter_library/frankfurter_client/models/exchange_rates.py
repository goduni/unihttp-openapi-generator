"""Generated declaration ``ExchangeRates``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class ExchangeRates:
    """Reference rates for a base currency on a given date."""

    amount: float
    """The amount that was converted."""
    base: str
    """The base currency the rates are quoted against."""
    date: date
    """The date the rates apply to."""
    rates: dict[str, float]
    """Target currency code -> rate."""
