"""Live demo + assertions for the generated Open-Meteo client (async + msgspec).

Runs against the real Open-Meteo API (https://open-meteo.com) — no auth. It
fetches current weather for several cities **concurrently** with asyncio.gather,
then an hourly forecast, and asserts plausible ranges (live weather is not
deterministic, so the checks are structural + sane-range rather than exact).

Run it:

    uv run python weather_demo.py

Exit codes:
    0  every call worked and all assertions passed
    1  an assertion failed (a real client/serialization bug)
    2  the API was unreachable / returned a server error (skipped, not a bug)

The generated client has a single endpoint, exercised in both modes:
    - get_forecast(current=...)  GET /v1/forecast  (current conditions)
    - get_forecast(hourly=...)   GET /v1/forecast  (hourly parallel arrays)
"""

from __future__ import annotations

import asyncio
import sys

from open_meteo_client import DEFAULT_BASE_URL, AsyncOpenMeteoForecastAPIClient
from unihttp.exceptions import NetworkError, RequestTimeoutError, ServerError

CITIES: dict[str, tuple[float, float]] = {
    "Berlin": (52.52, 13.41),
    "London": (51.51, -0.13),
    "Tokyo": (35.68, 139.69),
    "New York": (40.71, -74.01),
    "Sydney": (-33.87, 151.21),
}
CURRENT_VARS = ["temperature_2m", "wind_speed_10m", "weather_code"]


async def run() -> None:
    print(f"Open-Meteo client -> {DEFAULT_BASE_URL}")

    async with AsyncOpenMeteoForecastAPIClient() as client:
        # --- Current weather for many cities, fetched concurrently -----------
        print(f"\n=== Current weather ({len(CITIES)} cities, fetched concurrently) ===")
        forecasts = await asyncio.gather(
            *(
                client.get_forecast(
                    latitude=lat, longitude=lon, current=CURRENT_VARS, timezone="UTC"
                )
                for lat, lon in CITIES.values()
            )
        )
        print(f"{'City':<10}{'Temp °C':>9}{'Wind km/h':>11}{'Code':>6}")
        for city, fc in zip(CITIES, forecasts, strict=True):
            cur = fc.current
            assert cur is not None, f"{city}: response had no `current` block"
            print(
                f"{city:<10}{cur.temperature_2m:>9.1f}{cur.wind_speed_10m:>11.1f}{cur.weather_code:>6}"
            )
            assert -60.0 <= cur.temperature_2m <= 60.0, (
                f"{city}: implausible temp {cur.temperature_2m}"
            )
            assert cur.wind_speed_10m >= 0.0, f"{city}: negative wind speed"
            assert isinstance(cur.weather_code, int) and cur.weather_code >= 0
        # the API echoes the (snapped) coordinate back
        for fc, (lat, _) in zip(forecasts, CITIES.values(), strict=True):
            assert abs(fc.latitude - lat) < 0.5, f"latitude drifted: {fc.latitude} vs {lat}"

        # --- Hourly forecast (parallel arrays) -------------------------------
        print("\n=== Hourly forecast for Berlin (next day) ===")
        lat, lon = CITIES["Berlin"]
        hourly_fc = await client.get_forecast(
            latitude=lat, longitude=lon, hourly=["temperature_2m"], forecast_days=1, timezone="UTC"
        )
        hourly = hourly_fc.hourly
        assert hourly is not None, "response had no `hourly` block"
        # the two arrays line up element-for-element
        assert len(hourly.time) == len(hourly.temperature_2m) > 0, (
            "time/temperature arrays misaligned"
        )
        print(
            f"{len(hourly.time)} points; "
            f"first {hourly.time[0]} = {hourly.temperature_2m[0]}°C, "
            f"last {hourly.time[-1]} = {hourly.temperature_2m[-1]}°C"
        )
        assert all(isinstance(t, float) for t in hourly.temperature_2m)
        assert all(-60.0 <= t <= 60.0 for t in hourly.temperature_2m)

    print("\nOK — forecast (current + hourly), 5 cities concurrent, all assertions passed.")


def main() -> int:
    try:
        asyncio.run(run())
    except (NetworkError, RequestTimeoutError, ServerError) as exc:
        print(f"SKIP — Open-Meteo unreachable ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
