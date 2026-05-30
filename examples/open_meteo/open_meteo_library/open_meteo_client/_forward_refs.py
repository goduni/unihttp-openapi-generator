"""Resolve cross-module forward references for the per-object layout."""

from __future__ import annotations

import importlib


def resolve_forward_refs() -> None:
    """Inject referenced classes into every generated module's globals."""
    from open_meteo_client import models as _models

    namespace = {name: getattr(_models, name) for name in _models.__all__}

    module_names = [
        "open_meteo_client.models.current_weather",
        "open_meteo_client.models.forecast",
        "open_meteo_client.models.hourly_forecast",
        "open_meteo_client.methods.default.get_forecast",
    ]
    for module_name in module_names:
        module = importlib.import_module(module_name)
        vars(module).update(namespace)
