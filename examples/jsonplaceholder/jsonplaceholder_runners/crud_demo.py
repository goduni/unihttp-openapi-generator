"""Live demo + assertions for the generated JSONPlaceholder client.

Runs against the real JSONPlaceholder API (https://jsonplaceholder.typicode.com)
— no auth. It walks every endpoint of the grouped client across all four tags
(posts / comments / users / todos), including a create -> update -> delete write
lifecycle (the service fakes writes: it echoes the body back with an assigned
id). The fixtures are fixed, so most assertions are exact.

Run it:

    uv run python crud_demo.py

Exit codes:
    0  every call worked and all assertions passed
    1  an assertion failed (a real client/serialization bug)
    2  the API was unreachable / returned a server error (skipped, not a bug)
"""

from __future__ import annotations

import sys

from jsonplaceholder_client import DEFAULT_BASE_URL, JSONPlaceholderClient
from unihttp.exceptions import NetworkError, RequestTimeoutError, ServerError

POST_1_TITLE = "sunt aut facere repellat provident occaecati excepturi optio reprehenderit"


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def run() -> None:
    print(f"JSONPlaceholder client -> {DEFAULT_BASE_URL}")

    with JSONPlaceholderClient() as client:
        # --- posts: read --------------------------------------------------
        banner("posts")
        post = client.posts.get_post(id=1)
        print(f"post 1: user_id={post.user_id} title={post.title[:40]!r}...")
        assert post.id == 1 and post.user_id == 1
        assert post.title == POST_1_TITLE

        all_posts = client.posts.list_posts()
        by_user = client.posts.list_posts(user_id=1)
        print(f"{len(all_posts)} posts total, {len(by_user)} by user 1")
        assert len(all_posts) == 100
        # the camelCase `userId` query filter must actually apply (adaptix aliases it)
        assert len(by_user) == 10 and all(p.user_id == 1 for p in by_user)

        # --- posts: write lifecycle (faked by the service) ----------------
        banner("posts: create / update / delete")
        # the request body is spread into Body fields (user_id -> userId), so the
        # client POSTs {"userId": 7, ...}; if it were wrong the echoed user_id
        # below would not survive.
        created = client.posts.create_post(user_id=7, title="hello", body="world")
        print(f"created -> id={created.id} user_id={created.user_id} title={created.title!r}")
        assert created.id == 101  # new posts always echo back as id 101
        assert created.user_id == 7 and created.title == "hello"

        updated = client.posts.update_post(id=1, user_id=1, title="edited", body="updated")
        print(f"updated -> id={updated.id} title={updated.title!r}")
        assert updated.id == 1 and updated.title == "edited"

        deleted = client.posts.delete_post(id=1)
        print(f"deleted -> {deleted}")
        assert isinstance(deleted, dict)

        comments = client.posts.get_post_comments(id=1)
        print(f"post 1 has {len(comments)} comments; first by {comments[0].email}")
        assert len(comments) == 5 and all(c.post_id == 1 for c in comments)

        # --- comments -----------------------------------------------------
        banner("comments")
        post_comments = client.comments.list_comments(post_id=1)
        print(f"{len(post_comments)} comments on post 1 (via /comments?postId=1)")
        assert len(post_comments) == 5 and all(c.post_id == 1 for c in post_comments)

        # --- users: nested models -----------------------------------------
        banner("users")
        user = client.users.get_user(id=1)
        print(f"user 1: {user.name} <{user.email}> in {user.address.city} @ {user.company.name}")
        assert user.name == "Leanne Graham" and user.username == "Bret"
        assert user.address.city == "Gwenborough"
        assert user.address.geo.lat == "-37.3159"  # geo coords are strings here
        assert user.company.name == "Romaguera-Crona"
        assert len(client.users.list_users()) == 10

        # --- todos --------------------------------------------------------
        banner("todos")
        todo = client.todos.get_todo(id=1)
        print(f"todo 1: {todo.title!r} completed={todo.completed}")
        assert todo.id == 1 and todo.user_id == 1
        assert todo.title == "delectus aut autem" and todo.completed is False
        user_todos = client.todos.list_todos(user_id=1)
        print(f"user 1 has {len(user_todos)} todos")
        assert user_todos and all(t.user_id == 1 for t in user_todos)

    print("\nOK — 11 endpoints across 4 tags exercised (incl. CRUD), all assertions passed.")


def main() -> int:
    try:
        run()
    except (NetworkError, RequestTimeoutError, ServerError) as exc:
        print(f"SKIP — JSONPlaceholder unreachable ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
