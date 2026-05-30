"""Generated declaration ``User``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jsonplaceholder_client.models.address import Address
    from jsonplaceholder_client.models.company import Company


@dataclass
class User:
    id: int
    name: str
    username: str
    email: str
    address: Address
    phone: str
    website: str
    company: Company
