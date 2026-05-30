"""Resolve cross-module forward references for the per-object layout."""

from __future__ import annotations

import importlib


def resolve_forward_refs() -> None:
    """Inject referenced classes into every generated module's globals."""
    from jsonplaceholder_client import models as _models

    namespace = {name: getattr(_models, name) for name in _models.__all__}

    module_names = [
        "jsonplaceholder_client.models.address",
        "jsonplaceholder_client.models.comment",
        "jsonplaceholder_client.models.company",
        "jsonplaceholder_client.models.geo",
        "jsonplaceholder_client.models.post",
        "jsonplaceholder_client.models.todo",
        "jsonplaceholder_client.models.user",
        "jsonplaceholder_client.methods.posts.list_posts",
        "jsonplaceholder_client.methods.posts.create_post",
        "jsonplaceholder_client.methods.posts.get_post",
        "jsonplaceholder_client.methods.posts.update_post",
        "jsonplaceholder_client.methods.posts.delete_post",
        "jsonplaceholder_client.methods.posts.get_post_comments",
        "jsonplaceholder_client.methods.comments.list_comments",
        "jsonplaceholder_client.methods.users.list_users",
        "jsonplaceholder_client.methods.users.get_user",
        "jsonplaceholder_client.methods.todos.list_todos",
        "jsonplaceholder_client.methods.todos.get_todo",
    ]
    for module_name in module_names:
        module = importlib.import_module(module_name)
        vars(module).update(namespace)
