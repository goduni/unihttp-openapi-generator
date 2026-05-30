"""Generated API client. Do not edit by hand."""

from __future__ import annotations

from typing import Any

from unihttp.bind_method import bind_method
from unihttp.clients.httpx import HTTPXSyncClient
from unihttp.middlewares.error_mapper import SyncErrorMapperMiddleware

from frankfurter_client._serialization import request_dumper, response_loader
from frankfurter_client.exceptions import ERROR_MAP
from frankfurter_client.methods.default import (
    GetCurrencies,
    GetLatestRates,
    GetRatesForDate,
    GetTimeSeries,
    GetTimeSeriesToNow,
)

SERVERS: dict[str, str] = {"Production": "https://api.frankfurter.dev"}


DEFAULT_BASE_URL = "https://api.frankfurter.dev"


class FrankfurterAPIClient(HTTPXSyncClient):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: Any = None,
        middleware: list[Any] | None = None,
    ) -> None:
        _mw: list[Any] = list(middleware or [])
        _mw.insert(0, SyncErrorMapperMiddleware(ERROR_MAP))
        super().__init__(
            base_url=base_url,
            request_dumper=request_dumper,
            response_loader=response_loader,
            middleware=_mw,
            session=session,
        )

    get_latest_rates = bind_method(GetLatestRates)
    get_rates_for_date = bind_method(GetRatesForDate)
    get_time_series = bind_method(GetTimeSeries)
    get_time_series_to_now = bind_method(GetTimeSeriesToNow)
    get_currencies = bind_method(GetCurrencies)
