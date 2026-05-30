"""Generated request method ``GetUser``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path
from unihttp.method import BaseMethod

from jsonplaceholder_client.models.user import User


@dataclass
class GetUser(BaseMethod[User]):
    """Get a user by id"""

    __url__ = "/users/{id}"
    __method__ = "GET"

    id: Path[int]
