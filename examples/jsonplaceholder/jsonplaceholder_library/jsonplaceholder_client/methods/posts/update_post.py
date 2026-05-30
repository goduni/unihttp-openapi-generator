"""Generated request method ``UpdatePost``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Body, Path
from unihttp.method import BaseMethod

from jsonplaceholder_client.models.post import Post


@dataclass
class UpdatePost(BaseMethod[Post]):
    """Replace a post"""

    __url__ = "/posts/{id}"
    __method__ = "PUT"

    id: Path[int]
    user_id: Body[int]
    title: Body[str]
    body: Body[str]
