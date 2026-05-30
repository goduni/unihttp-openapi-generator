"""Generated declaration ``Comment``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Comment:
    post_id: int
    id: int
    name: str
    email: str
    body: str
