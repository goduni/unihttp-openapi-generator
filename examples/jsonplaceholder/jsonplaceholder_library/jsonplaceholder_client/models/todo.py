"""Generated declaration ``Todo``. Do not edit by hand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Todo:
    user_id: int
    id: int
    title: str
    completed: bool
