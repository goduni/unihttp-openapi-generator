"""Generated request method ``GetPost``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass

from unihttp.markers import Path
from unihttp.method import BaseMethod

from jsonplaceholder_client.models.post import Post


@dataclass
class GetPost(BaseMethod[Post]):
    """Get a post by id"""

    __url__ = "/posts/{id}"
    __method__ = "GET"

    id: Path[int]
