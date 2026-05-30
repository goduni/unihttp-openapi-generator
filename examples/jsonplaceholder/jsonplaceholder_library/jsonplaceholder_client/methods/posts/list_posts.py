"""Generated request method ``ListPosts``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from jsonplaceholder_client.models.post import Post


@dataclass
class ListPosts(BaseMethod[list[Post]]):
    """List posts"""

    __url__ = "/posts"
    __method__ = "GET"

    user_id: Query[Omittable[int]] = Omitted()
