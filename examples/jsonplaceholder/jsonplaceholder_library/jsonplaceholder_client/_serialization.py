"""Serialization wiring (adaptix)."""

from adaptix import name_mapping
from unihttp.serializers.adaptix import DEFAULT_RETORT

from jsonplaceholder_client._forward_refs import resolve_forward_refs
from jsonplaceholder_client.methods import (
    CreatePost,
    ListComments,
    ListPosts,
    ListTodos,
    UpdatePost,
)
from jsonplaceholder_client.models import Comment, Company, Post, Todo

resolve_forward_refs()

_RECIPE = [
    name_mapping(Company, map={"catch_phrase": "catchPhrase"}),
    name_mapping(Post, map={"user_id": "userId"}),
    name_mapping(Comment, map={"post_id": "postId"}),
    name_mapping(Todo, map={"user_id": "userId"}),
    name_mapping(ListPosts, map={"user_id": "userId"}),
    name_mapping(CreatePost, map={"user_id": "userId"}),
    name_mapping(UpdatePost, map={"user_id": "userId"}),
    name_mapping(ListComments, map={"post_id": "postId"}),
    name_mapping(ListTodos, map={"user_id": "userId"}),
]
RETORT = DEFAULT_RETORT.extend(recipe=_RECIPE)

request_dumper = RETORT
response_loader = RETORT
