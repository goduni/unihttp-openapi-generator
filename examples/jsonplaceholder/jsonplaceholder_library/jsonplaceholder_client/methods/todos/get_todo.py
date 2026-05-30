"""Generated request method ``GetTodo``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path
from unihttp.method import BaseMethod

from jsonplaceholder_client.models.todo import Todo


@dataclass
class GetTodo(BaseMethod[Todo]):
    """Get a todo by id"""

    __url__ = "/todos/{id}"
    __method__ = "GET"

    id: Path[int]
