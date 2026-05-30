"""Generated request method ``CreatePost``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Body
from unihttp.method import BaseMethod

from jsonplaceholder_client.models.post import Post


@dataclass
class CreatePost(BaseMethod[Post]):
    """Create a post"""

    __url__ = "/posts"
    __method__ = "POST"

    user_id: Body[int]
    title: Body[str]
    body: Body[str]
