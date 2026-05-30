"""Render ``exceptions.py``: per-status API exceptions and the status->exception map."""

from __future__ import annotations

from unihttp_openapi_generator.ir.document import IRDocument

_STATUS_NAMES = {
    400: "BadRequest",
    401: "Unauthorized",
    402: "PaymentRequired",
    403: "Forbidden",
    404: "NotFound",
    405: "MethodNotAllowed",
    406: "NotAcceptable",
    408: "RequestTimeout",
    409: "Conflict",
    410: "Gone",
    411: "LengthRequired",
    412: "PreconditionFailed",
    413: "PayloadTooLarge",
    415: "UnsupportedMediaType",
    418: "ImATeapot",
    422: "UnprocessableEntity",
    423: "Locked",
    424: "FailedDependency",
    425: "TooEarly",
    426: "UpgradeRequired",
    428: "PreconditionRequired",
    429: "TooManyRequests",
    431: "RequestHeaderFieldsTooLarge",
    451: "UnavailableForLegalReasons",
    500: "InternalServerError",
    501: "NotImplemented",
    502: "BadGateway",
    503: "ServiceUnavailable",
    504: "GatewayTimeout",
    505: "HTTPVersionNotSupported",
}


def status_exception_name(status: int) -> str:
    return f"{_STATUS_NAMES.get(status, f'Status{status}')}Error"


def collect_error_statuses(doc: IRDocument) -> list[int]:
    statuses: set[int] = set()
    for op in doc.operations:
        for err in op.errors:
            if err.status.isdigit():
                statuses.add(int(err.status))
    return sorted(statuses)


def render_exceptions_module(doc: IRDocument) -> str:
    statuses = collect_error_statuses(doc)
    lines = [
        '"""Generated API exceptions. Do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "from unihttp.exceptions import ClientError, HTTPStatusError, ServerError",
        "from unihttp.middlewares.error_mapper import ErrorFactory, StatusKey",
        "",
        "",
        "class ApiError(HTTPStatusError):",
        f'    """Base error raised by the {doc.title} client."""',
    ]
    for status in statuses:
        lines.append("")
        lines.append("")
        lines.append(f"class {status_exception_name(status)}(ApiError):")
        lines.append(f'    """Raised on HTTP {status} responses."""')

    lines.append("")
    lines.append("")
    lines.append("ERROR_MAP: dict[StatusKey, ErrorFactory] = {")
    for status in statuses:
        lines.append(f"    {status}: {status_exception_name(status)},")
    lines.append("    range(400, 500): ClientError,")
    lines.append("    range(500, 600): ServerError,")
    lines.append("}")
    return "\n".join(lines) + "\n"
