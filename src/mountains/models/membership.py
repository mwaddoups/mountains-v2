from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from attrs import define

from mountains.db import Repository

if TYPE_CHECKING:
    from sqlite3 import Connection


@define
class MembershipProduct:
    """
    This is a product that can be bought by users, and entitles them to
    the expiry_date listed in the product.
    """

    id: int
    expiry_date: datetime.date
    price_id: str


def membership_repo(conn: Connection) -> Repository[MembershipProduct]:
    repo = Repository(
        conn=conn,
        table_name="membership_product",
        schema=[
            "id INTEGER PRIMARY KEY",
            "expiry_date DATE NOT NULL",
            "price_id TEXT NOT NULL",
        ],
        storage_cls=MembershipProduct,
    )

    repo.create_table()

    return repo
