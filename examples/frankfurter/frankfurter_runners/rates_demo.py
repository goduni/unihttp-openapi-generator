"""Live demo + assertions for the generated Frankfurter client.

Runs against the real Frankfurter API (https://frankfurter.dev) — no auth.
It both *prints* a human-readable walk-through and *asserts* invariants, so the
same file works as a usage example and as a functional test.

Run it:

    uv run python rates_demo.py

Exit codes:
    0  every endpoint worked and all assertions passed
    1  an assertion failed (a real client/serialization bug)
    2  the API was unreachable / returned a server error (skipped, not a bug)

This runner covers every endpoint of the generated client:
    - get_latest_rates        GET /v1/latest
    - get_rates_for_date      GET /v1/{date}
    - get_time_series         GET /v1/{start}..{end}
    - get_time_series_to_now  GET /v1/{start}..
    - get_currencies          GET /v1/currencies
"""

from __future__ import annotations

import sys

from frankfurter_client import DEFAULT_BASE_URL, FrankfurterAPIClient
from unihttp.exceptions import NetworkError, RequestTimeoutError, ServerError


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def run() -> None:
    print(f"Frankfurter client -> {DEFAULT_BASE_URL}")

    with FrankfurterAPIClient() as client:
        # --- 1. Latest rates -------------------------------------------------
        banner("Latest EUR rates")
        latest = client.get_latest_rates()
        sample = dict(list(latest.rates.items())[:5])
        print(f"base={latest.base}  date={latest.date}  amount={latest.amount}")
        print(f"sample rates: {sample}")
        assert latest.base == "EUR", f"default base should be EUR, got {latest.base}"
        assert latest.amount == 1.0
        assert latest.rates, "expected a non-empty rates map"
        assert all(isinstance(v, float) for v in latest.rates.values())

        # --- 2. Historical rates (deterministic) -----------------------------
        # Past reference rates never change, so these are exact assertions —
        # the strongest possible proof the client really round-trips the API.
        banner("Historical rates for 2020-01-02 (base USD)")
        hist = client.get_rates_for_date(date="2020-01-02", base="USD", symbols=["GBP", "EUR"])
        print(f"base={hist.base}  date={hist.date}  rates={hist.rates}")
        assert str(hist.date) == "2020-01-02", hist.date
        assert hist.base == "USD"
        assert hist.rates == {"GBP": 0.75787, "EUR": 0.89342}, hist.rates
        # `symbols` is a list[str] serialized as a single CSV query param; if that
        # were broken we'd get every currency back instead of just these two.
        assert set(hist.rates) == {"GBP", "EUR"}, "symbols filter did not apply"

        # --- 3. Amount scaling -----------------------------------------------
        banner("Convert 100 USD on 2020-01-02")
        scaled = client.get_rates_for_date(
            date="2020-01-02", base="USD", symbols=["GBP"], amount=100
        )
        print(f"100 USD -> {scaled.rates['GBP']} GBP")
        assert scaled.amount == 100.0
        # The API scales from its full-precision rate then rounds, so 100x the
        # rounded unit rate (75.787) only has to match within rounding error.
        assert abs(scaled.rates["GBP"] - 0.75787 * 100) < 0.01, scaled.rates

        # --- 4. Time series over a range (nested date -> code -> rate map) ----
        banner("Time series 2020-01-01..2020-01-05 (base USD)")
        series = client.get_time_series(
            start_date="2020-01-01", end_date="2020-01-05", base="USD", symbols=["GBP"]
        )
        print(
            f"base={series.base}  {series.start_date}..{series.end_date}  days={len(series.rates)}"
        )
        assert series.base == "USD"
        assert series.rates and all(isinstance(day, dict) for day in series.rates.values())
        # rates is {date: {code: rate}}; the 2020-01-02 working day is deterministic.
        assert series.rates["2020-01-02"]["GBP"] == 0.75787, series.rates.get("2020-01-02")

        # --- 5. Open-ended time series (start_date to today) -----------------
        banner("Time series 2024-01-01.. (base USD -> EUR)")
        to_now = client.get_time_series_to_now(start_date="2024-01-01", base="USD", symbols=["EUR"])
        print(f"{to_now.start_date}..{to_now.end_date}  days={len(to_now.rates)}")
        assert to_now.rates, "expected a non-empty time series"
        assert "2024-01-02" in to_now.rates, "expected the first working day to be present"
        assert isinstance(to_now.rates["2024-01-02"]["EUR"], float)

        # --- 6. Supported currencies -----------------------------------------
        banner("Supported currencies")
        currencies = client.get_currencies()
        print(f"{len(currencies)} currencies; e.g. USD={currencies.get('USD')!r}")
        assert currencies["USD"] == "United States Dollar"
        assert len(currencies) >= 20, f"expected many currencies, got {len(currencies)}"
        # every value the client returned for `latest` must be a known currency code
        unknown = set(latest.rates) - set(currencies)
        assert not unknown, f"rates referenced unknown currencies: {unknown}"

    print("\nOK — 5/5 endpoints exercised, all assertions passed.")


def main() -> int:
    try:
        run()
    except (NetworkError, RequestTimeoutError, ServerError) as exc:
        print(
            f"SKIP — Frankfurter API unreachable ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
