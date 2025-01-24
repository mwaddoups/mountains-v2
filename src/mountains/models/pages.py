from __future__ import annotations

from typing import TYPE_CHECKING

from attrs import define

from mountains.db import Repository
from mountains.errors import MountainException

if TYPE_CHECKING:
    from sqlite3 import Connection


@define
class Page:
    name: str
    description: str
    markdown: str
    version: int


def pages_repo(conn: Connection) -> Repository[Page]:
    repo = Repository(
        conn=conn,
        table_name="pages",
        schema=[
            "name TEXT NOT NULL",
            "description TEXT NOT NULL",
            "markdown TEXT NOT NULL",
            "version INTEGER NOT NULL",
            "PRIMARY KEY(name, version)",
        ],
        storage_cls=Page,
    )

    return repo


def latest_page(name: str, repo: Repository[Page]) -> Page:
    pages = repo.list_where(name=name)
    try:
        return max(pages, key=lambda p: p.version)
    except ValueError:
        raise MountainException(f"No page found with name {name}!")


def latest_content(conn: Connection, name: str) -> str:
    return latest_page(name, repo=pages_repo(conn)).markdown
