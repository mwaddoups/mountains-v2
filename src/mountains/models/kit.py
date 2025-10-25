from __future__ import annotations

import datetime
import enum
import sqlite3
from typing import TYPE_CHECKING, Self

from attrs import Factory, define
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


@define
class KitRequest:
    id: int
    user_id: int
    kit_id: int
    pickup_dt: datetime.datetime
    return_dt: datetime.datetime
    notes: str
    is_approved: bool = False
    is_picked_up: bool = False
    is_returned: bool = False
    request_created_dt: datetime.datetime = Factory(datetime.datetime.now)

    @classmethod
    def from_form(
        cls, id: int, user_id: int, kit_id: int, form: ImmutableMultiDict[str, str]
    ) -> Self:
        return cls(
            id=id,
            user_id=user_id,
            kit_id=kit_id,
            pickup_dt=datetime.datetime.fromisoformat(form["pickup_dt"]),
            return_dt=datetime.datetime.fromisoformat(form["return_dt"]),
            notes=form["notes"],
        )

    def is_active(self) -> bool:
        now = datetime.datetime.now()
        return self.pickup_dt <= now <= self.return_dt and not self.is_returned

    def is_in_future(self) -> bool:
        now = datetime.datetime.now()
        return self.pickup_dt >= now 


def kit_request_repo(conn: Connection) -> Repository[KitRequest]:
    repo = Repository(
        conn=conn,
        table_name="kit_requests",
        schema=[
            "id INTEGER PRIMARY KEY",
            "user_id INTEGER REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE",
            "kit_id INTEGER REFERENCES kit_item(id) ON DELETE CASCADE ON UPDATE CASCADE",
            "pickup_dt DATETIME NOT NULL",
            "return_dt DATETIME NOT NULL",
            "notes TEXT",
            "is_approved BOOLEAN NOT NULL DEFAULT false",
            "is_picked_up BOOLEAN NOT NULL DEFAULT false",
            "is_returned BOOLEAN NOT NULL DEFAULT false",
            "request_created_dt DATETIME DEFAULT current_timestamp",
        ],
        storage_cls=KitRequest,
    )

    return repo


@define
class KitDetail:
    id: int
    kit_id: int
    user_id: int
    added_dt: datetime.datetime = Factory(datetime.datetime.now)
    condition: str | None = None
    note: str | None = None
    photo_path: str | None = None

    def __attrs_post_init__(self):
        if all(attr is None for attr in [self.condition, self.note, self.photo_path]):
            raise Exception("Kit detail should have one of condition, note or photo.")

    @classmethod
    def from_form(
        cls,
        id: int,
        user_id: int,
        kit_id: int,
        form: ImmutableMultiDict[str, str],
        photo_path: str | None = None,
    ) -> Self:
        return cls(
            id=id,
            user_id=user_id,
            kit_id=kit_id,
            added_dt=datetime.datetime.now(),
            condition=form["condition"],
            note=form["note"],
            photo_path=photo_path,
        )


def kit_details_repo(conn: Connection) -> Repository[KitDetail]:
    repo = Repository(
        conn=conn,
        table_name="kit_details",
        schema=[
            "id INTEGER PRIMARY KEY",
            "kit_id INTEGER REFERENCES kit_item(id) ON DELETE CASCADE ON UPDATE CASCADE",
            "user_id INTEGER REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE",
            "added_dt DATETIME NOT NULL DEFAULT current_timestamp",
            "condition TEXT",
            "note TEXT",
            "photo_path TEXT",
        ],
        storage_cls=KitDetail,
    )

    return repo
