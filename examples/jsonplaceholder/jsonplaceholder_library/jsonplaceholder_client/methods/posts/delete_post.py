"""Generated request method ``DeletePost``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unihttp.markers import Path
from unihttp.method import BaseMethod


@dataclass
class DeletePost(BaseMethod[dict[str, Any]]):
    """Delete a post"""

    __url__ = "/posts/{id}"
    __method__ = "DELETE"

    id: Path[int]
