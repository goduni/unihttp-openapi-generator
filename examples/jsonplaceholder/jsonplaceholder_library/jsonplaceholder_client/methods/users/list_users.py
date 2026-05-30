"""Generated request method ``ListUsers``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.method import BaseMethod

from jsonplaceholder_client.models.user import User


@dataclass
class ListUsers(BaseMethod[list[User]]):
    """List users"""

    __url__ = "/users"
    __method__ = "GET"
