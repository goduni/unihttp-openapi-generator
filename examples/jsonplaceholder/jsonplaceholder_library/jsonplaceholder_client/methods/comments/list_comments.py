"""Generated request method ``ListComments``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Query
from unihttp.method import BaseMethod
from unihttp.omitted import Omittable, Omitted

from jsonplaceholder_client.models.comment import Comment


@dataclass
class ListComments(BaseMethod[list[Comment]]):
    """List comments"""

    __url__ = "/comments"
    __method__ = "GET"

    post_id: Query[Omittable[int]] = Omitted()
