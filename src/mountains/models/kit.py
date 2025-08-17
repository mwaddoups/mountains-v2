from __future__ import annotations

import datetime
import enum
import sqlite3
from typing import TYPE_CHECKING, Self

from attrs import define
from werkzeug.datastructures import ImmutableMultiDict

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

    @classmethod
    def from_form(cls, id: int, form: ImmutableMultiDict[str, str]) -> Self:
        return cls(
            id=id,
            club_id=form["club_id"],
            description=form["description"],
            brand=form["brand"],
            color=form["color"],
            size=form["size"],
            kit_type=form["kit_type"],
            kit_group=KitGroup(form.get("kit_group", type=int)),
            purchased_on=datetime.date.fromisoformat(form["purchased_on"]),
            purchase_price=float(form["purchase_price"]),
        )


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
