"""Resolve cross-module forward references for the per-object layout."""

from __future__ import annotations

import importlib


def resolve_forward_refs() -> None:
    """Inject referenced classes into every generated module's globals."""
    from frankfurter_client import models as _models

    namespace = {name: getattr(_models, name) for name in _models.__all__}

    module_names = [
        "frankfurter_client.models.currency_map",
        "frankfurter_client.models.exchange_rates",
        "frankfurter_client.models.time_series_rates",
        "frankfurter_client.methods.default.get_latest_rates",
        "frankfurter_client.methods.default.get_rates_for_date",
        "frankfurter_client.methods.default.get_time_series",
        "frankfurter_client.methods.default.get_time_series_to_now",
        "frankfurter_client.methods.default.get_currencies",
    ]
    for module_name in module_names:
        module = importlib.import_module(module_name)
        vars(module).update(namespace)
