"""Generated request method ``GetPostComments``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path
from unihttp.method import BaseMethod

from jsonplaceholder_client.models.comment import Comment


@dataclass
class GetPostComments(BaseMethod[list[Comment]]):
    """Comments on a post"""

    __url__ = "/posts/{id}/comments"
    __method__ = "GET"

    id: Path[int]
