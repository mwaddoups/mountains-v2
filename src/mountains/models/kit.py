from __future__ import annotations

import datetime
import enum
import sqlite3
from typing import TYPE_CHECKING

from attrs import define

from mountains.db import Repository

if TYPE_CHECKING:
    from sqlite3 import Connection


class KitGroup(enum.Enum):
    GENERAL = 1
    MAPS = 2
    BOOKS = 3
    HELMETS = 4
    CLIMBING = 5
    WINTER = 6


sqlite3.register_adapter(KitGroup, lambda x: x.value)


@define
class KitItem:
    id: int
    club_id: str
    description: str
    brand: str
    color: str
    size: str
    kit_group: KitGroup
    kit_type: str
    purchased_on: datetime.date
    purchase_price: float


def kit_item_repo(conn: Connection) -> Repository[KitItem]:
    repo = Repository(
        conn=conn,
        table_name="kit_item",
        schema=[
            "id INTEGER PRIMARY KEY",
            "club_id TEXT NOT NULL",
            "description TEXT NOT NULL",
            "brand TEXT",
            "color TEXT",
            "size TEXT",
            "kit_group INTEGER NOT NULL",
            "kit_type TEXT",
            "purchased_on DATE NOT NULL",
            "purchase_price FLOAT NOT NULL",
        ],
        storage_cls=KitItem,
    )

    return repo
