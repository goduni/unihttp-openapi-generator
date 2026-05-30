"""Generated API client. Do not edit by hand."""

from __future__ import annotations

from typing import Any

from unihttp.bind_method import bind_method
from unihttp.clients.httpx import HTTPXAsyncClient
from unihttp.middlewares.error_mapper import AsyncErrorMapperMiddleware

from open_meteo_client._serialization import request_dumper, response_loader
from open_meteo_client.exceptions import ERROR_MAP
from open_meteo_client.methods.default import GetForecast

SERVERS: dict[str, str] = {"Production": "https://api.open-meteo.com"}


DEFAULT_BASE_URL = "https://api.open-meteo.com"


class AsyncOpenMeteoForecastAPIClient(HTTPXAsyncClient):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: Any = None,
        middleware: list[Any] | None = None,
    ) -> None:
        _mw: list[Any] = list(middleware or [])
        _mw.insert(0, AsyncErrorMapperMiddleware(ERROR_MAP))
        super().__init__(
            base_url=base_url,
            request_dumper=request_dumper,
            response_loader=response_loader,
            middleware=_mw,
            session=session,
        )

    get_forecast = bind_method(GetForecast)
