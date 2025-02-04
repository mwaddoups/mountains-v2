from __future__ import annotations

import datetime
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from attrs import Factory, define
from flask import current_app
from PIL import Image, ImageOps

from mountains.db import Repository
from mountains.utils import now_utc

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage

logger = logging.getLogger(__name__)


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

    def orig_path(self) -> Path | None:
        static_dir = Path(current_app.config["STATIC_FOLDER"])
        path = self.photo_path.with_stem(self.photo_path.stem + ".orig")
        if (static_dir / path).exists():
            return path
        else:
            return None

    def thumb_path(self, width=128) -> Path:
        static_dir = Path(current_app.config["STATIC_FOLDER"])
        path = self.photo_path.with_stem(self.photo_path.stem + f".th.{width}")
        file_path = static_dir / path

        static_photo_path = static_dir / self.photo_path
        if not file_path.exists() and static_photo_path.exists():
            # Create thumbnail for first time
            with Image.open(static_photo_path) as im:
                logger.info("Creating thumbnail for photo %s", self.id)
                if im.width > width:
                    new_height = int(im.height * (width / im.width))
                    resized = im.resize((width, new_height))
                    ImageOps.exif_transpose(resized, in_place=True)
                    resized.save(file_path)
        return path


def upload_photo(file: FileStorage, static_dir: Path, new_width: int = 1920) -> Path:
    assert file.filename is not None, (
        "upload_photo should always have a file.filename attribute"
    )
    random_str = str(uuid.uuid4())
    file_type = Path(file.filename).suffix
    filename = Path(random_str).with_suffix(file_type)
    upload_path = static_dir / "uploads" / "photos" / filename
    file.save(upload_path)

    # Now resize the image using PIL
    with Image.open(upload_path) as im:
        # Save the original too
        im.save(upload_path.with_stem(upload_path.stem + ".orig"))
        if im.width > new_width:
            new_height = int(im.height * (new_width / im.width))
            resized = im.resize((new_width, new_height))
            ImageOps.exif_transpose(resized, in_place=True)
            resized.save(upload_path)

    return Path("uploads") / "photos" / filename


def albums_repo(conn: sqlite3.Connection) -> Repository[Album]:
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


def photos_repo(conn: sqlite3.Connection) -> Repository[Photo]:
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
