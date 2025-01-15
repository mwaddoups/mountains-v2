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


def pages_repo(conn: Connection) -> Repository[Page]:
    repo = Repository(
        conn=conn,
        table_name="pages",
        schema=[
            "name TEXT PRIMARY KEY",
            "description TEXT NOT NULL",
            "markdown TEXT NOT NULL",
        ],
        storage_cls=Page,
    )

    repo.create_table()

    return repo
