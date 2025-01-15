from __future__ import annotations

from typing import TYPE_CHECKING

from attrs import define

from mountains.db import Repository

if TYPE_CHECKING:
    from sqlite3 import Connection


@define
class Page:
    name: str
    description: str
    markdown: str
    version: int


def latest_page(name: str, repo: Repository[Page]) -> Page:
    pages = repo.list_where(name=name)
    return max(pages, key=lambda p: p.version)


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

    repo.create_table()

    return repo
