"""Generated API exceptions. Do not edit by hand."""

from __future__ import annotations

from unihttp.exceptions import ClientError, HTTPStatusError, ServerError
from unihttp.middlewares.error_mapper import ErrorFactory, StatusKey


class ApiError(HTTPStatusError):
    """Base error raised by the Frankfurter API client."""


ERROR_MAP: dict[StatusKey, ErrorFactory] = {
    range(400, 500): ClientError,
    range(500, 600): ServerError,
}
