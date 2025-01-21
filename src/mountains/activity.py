from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from attrs import Factory, define

from mountains.db import Repository
from mountains.utils import now_utc

if TYPE_CHECKING:
    from sqlite3 import Connection


@define
class Activity:
    user_id: int | None
    event_id: int | None
    action: str
    dt: datetime.datetime = Factory(now_utc)


def activity_repo(conn: Connection) -> Repository[Activity]:
    repo = Repository(
        conn=conn,
        table_name="activity",
        schema=[
            "user_id INTEGER REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE",
            "event_id INTEGER REFERENCES events(id) ON DELETE SET NULL ON UPDATE CASCADE",
            "dt DATETIME NOT NULL",
            "action TEXT NOT NULL",
        ],
        storage_cls=Activity,
    )

    repo.create_table()

    return repo
