"""Generated API client. Do not edit by hand."""

from __future__ import annotations

from typing import Any, cast

from unihttp.bind_method import bind_method
from unihttp.clients.requests import RequestsSyncClient
from unihttp.method import BaseMethod, ResponseType
from unihttp.middlewares.error_mapper import SyncErrorMapperMiddleware

from jsonplaceholder_client._serialization import request_dumper, response_loader
from jsonplaceholder_client.exceptions import ERROR_MAP
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

SERVERS: dict[str, str] = {"Production": "https://jsonplaceholder.typicode.com"}


DEFAULT_BASE_URL = "https://jsonplaceholder.typicode.com"


class PostsClient:
    def __init__(self, root: Any) -> None:
        self._root = root

    def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType:
        return cast(ResponseType, self._root.call_method(method))

    list_posts = bind_method(ListPosts)
    create_post = bind_method(CreatePost)
    get_post = bind_method(GetPost)
    update_post = bind_method(UpdatePost)
    delete_post = bind_method(DeletePost)
    get_post_comments = bind_method(GetPostComments)


class CommentsClient:
    def __init__(self, root: Any) -> None:
        self._root = root

    def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType:
        return cast(ResponseType, self._root.call_method(method))

    list_comments = bind_method(ListComments)


class UsersClient:
    def __init__(self, root: Any) -> None:
        self._root = root

    def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType:
        return cast(ResponseType, self._root.call_method(method))

    list_users = bind_method(ListUsers)
    get_user = bind_method(GetUser)


class TodosClient:
    def __init__(self, root: Any) -> None:
        self._root = root

    def call_method(self, method: BaseMethod[ResponseType]) -> ResponseType:
        return cast(ResponseType, self._root.call_method(method))

    list_todos = bind_method(ListTodos)
    get_todo = bind_method(GetTodo)


class JSONPlaceholderClient(RequestsSyncClient):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: Any = None,
        middleware: list[Any] | None = None,
    ) -> None:
        _mw: list[Any] = list(middleware or [])
        _mw.insert(0, SyncErrorMapperMiddleware(ERROR_MAP))
        super().__init__(
            base_url=base_url,
            request_dumper=request_dumper,
            response_loader=response_loader,
            middleware=_mw,
            session=session,
        )
        self.posts = PostsClient(self)
        self.comments = CommentsClient(self)
        self.users = UsersClient(self)
        self.todos = TodosClient(self)
