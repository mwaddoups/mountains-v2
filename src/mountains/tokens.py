import datetime
import sqlite3
import uuid

from attrs import define

from mountains.db import Repository
from mountains.utils import now_utc


@define
class AuthToken:
    id: str
    user_id: int
    expiry_utc: datetime.datetime

    @classmethod
    def from_id(cls, id: int, valid_days: int = 0, valid_mins: int = 0):
        return cls(
            id=str(uuid.uuid4()),
            user_id=id,
            expiry_utc=now_utc()
            + datetime.timedelta(days=valid_days, minutes=valid_mins),
        )

    def is_valid(self) -> bool:
        return self.expiry_utc > now_utc()


def tokens(conn: sqlite3.Connection) -> Repository[AuthToken]:
    return Repository(
        conn=conn,
        table_name="tokens",
        schema=[
            "id TEXT PRIMARY KEY",
            "user_id INTEGER",
            "expiry_utc DATETIME",
            "FOREIGN KEY(user_id) REFERENCES users(id)",
        ],
        storage_cls=AuthToken,
    )
