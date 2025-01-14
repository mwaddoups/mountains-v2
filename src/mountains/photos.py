import datetime
import sqlite3
from pathlib import Path

from attrs import Factory, define

from mountains.db import Repository
from mountains.utils import now_utc


@define
class Album:
    id: int
    name: str
    event_date: datetime.datetime | None
    created_at_utc: datetime.datetime = Factory(now_utc)


@define
class Photo:
    id: int
    uploader_id: int
    album_id: int
    starred: bool
    photo_path: Path
    created_at_utc: datetime.datetime = Factory(now_utc)


def albums(conn: sqlite3.Connection) -> Repository[Album]:
    return Repository(
        conn=conn,
        table_name="albums",
        schema=[
            "id INTEGER PRIMARY KEY",
            "name TEXT NOT NULL",
            "event_date DATETIME",
            "created_at_utc DATETIME NOT NULL",
        ],
        storage_cls=Album,
    )


def photos(conn: sqlite3.Connection) -> Repository[Photo]:
    return Repository(
        conn=conn,
        table_name="photos",
        schema=[
            "id INTEGER PRIMARY KEY",
            "uploader_id INTEGER NOT NULL",
            "album_id INTEGER NOT NULL",
            "photo_path TEXT NOT NULL",
            "starred BOOLEAN NOT NULL",
            "created_at_utc DATETIME NOT NULL",
            "FOREIGN KEY(uploader_id) REFERENCES users(id)",
            "FOREIGN KEY(album_id) REFERENCES albums(id)",
        ],
        storage_cls=Photo,
    )
