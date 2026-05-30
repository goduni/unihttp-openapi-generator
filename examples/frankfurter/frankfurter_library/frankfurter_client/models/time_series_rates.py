"""Generated declaration ``TimeSeriesRates``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class TimeSeriesRates:
    """Reference rates for each working day in a date range."""

    amount: float
    base: str
    start_date: date
    end_date: date
    rates: dict[str, dict[str, float]]
