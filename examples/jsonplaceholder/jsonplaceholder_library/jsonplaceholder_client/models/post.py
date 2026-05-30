"""Generated declaration ``Post``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Post:
    user_id: int
    id: int
    title: str
    body: str
