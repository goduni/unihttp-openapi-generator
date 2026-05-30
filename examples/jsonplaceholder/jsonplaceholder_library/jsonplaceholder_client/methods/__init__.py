"""Generated request methods."""

from __future__ import annotations

from jsonplaceholder_client.methods.comments import ListComments
from jsonplaceholder_client.methods.posts import (
    CreatePost,
    DeletePost,
    GetPost,
    GetPostComments,
    ListPosts,
    UpdatePost,
)
from jsonplaceholder_client.methods.todos import GetTodo, ListTodos
from jsonplaceholder_client.methods.users import GetUser, ListUsers

__all__ = [
    "CreatePost",
    "DeletePost",
    "GetPost",
    "GetPostComments",
    "GetTodo",
    "GetUser",
    "ListComments",
    "ListPosts",
    "ListTodos",
    "ListUsers",
    "UpdatePost",
]
