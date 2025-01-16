from __future__ import annotations

import datetime
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from attrs import Factory, define
from PIL import Image

from mountains.db import Repository
from mountains.utils import now_utc

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


@define
class Album:
    id: int
    name: str
    event_date: datetime.date | None
    created_at_utc: datetime.datetime = Factory(now_utc)


@define
class Photo:
    id: int
    uploader_id: int
    album_id: int
    starred: bool
    # Relative to static (e.g. uploads/photos/...)
    photo_path: Path
    created_at_utc: datetime.datetime = Factory(now_utc)


def upload_photo(file: FileStorage, upload_dir: Path, new_width: int = 1920) -> Path:
    assert file.filename is not None, (
        "upload_photo should always have a file.filename attribute"
    )
    filename = Path(str(uuid.uuid4())).with_suffix(Path(file.filename).suffix)
    upload_path = upload_dir / "photos" / filename
    file.save(upload_path)

    # Now resize the image using PIL
    with Image.open(upload_path) as im:
        if im.width > new_width:
            new_height = int(im.height * (new_width / im.width))
            resized = im.resize((new_width, new_height))
            resized.save(upload_path)

    # This relies on the uploads dir being at static/uploads
    return Path("uploads") / "photos" / filename


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
