"""Coverage for the loader's URL, parse-error, version-warning and dump paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from unihttp_openapi_generator.loader import (
    SpecLoadError,
    _warn_version,
    dump_json,
    load_spec,
)

_MINIMAL = {"openapi": "3.1.0", "info": {"title": "T", "version": "1.0.0"}, "paths": {}}


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_load_spec_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(json.dumps(_MINIMAL))

    monkeypatch.setattr(httpx, "get", fake_get)
    spec = load_spec("https://example.com/spec.json")
    assert spec["openapi"] == "3.1.0"


def test_load_spec_from_url_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(SpecLoadError, match="failed to fetch"):
        load_spec("https://example.com/spec.json")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("key: 'unterminated\n")
    with pytest.raises(SpecLoadError, match="YAML/JSON"):
        load_spec(str(p))


def test_unsupported_version_warns(caplog: pytest.LogCaptureFixture) -> None:
    # The OpenAPI validator can't even detect a 4.x version, so exercise the
    # version warning directly (it fires for anything outside 3.0.x / 3.1.x).
    _warn_version({"openapi": "4.0.0"})
    assert "only OpenAPI 3.0.x / 3.1.x are supported" in caplog.text


def test_dump_json_is_sorted() -> None:
    out = dump_json({"b": 1, "a": 2})
    assert out == '{\n  "a": 2,\n  "b": 1\n}'
