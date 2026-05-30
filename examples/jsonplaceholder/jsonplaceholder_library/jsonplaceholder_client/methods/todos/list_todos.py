"""Generated request method ``ListTodos``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from jsonplaceholder_client.models.todo import Todo


@dataclass
class ListTodos(BaseMethod[list[Todo]]):
    """List todos"""

    __url__ = "/todos"
    __method__ = "GET"

    user_id: Query[Omittable[int]] = Omitted()
