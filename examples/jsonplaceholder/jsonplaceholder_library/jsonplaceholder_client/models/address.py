"""Generated declaration ``Address``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jsonplaceholder_client.models.geo import Geo


@dataclass
class Address:
    street: str
    suite: str
    city: str
    zipcode: str
    geo: Geo
