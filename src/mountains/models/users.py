from __future__ import annotations

import datetime
import enum
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from attrs import Factory, define, field
from flask import abort
from PIL import Image, ImageOps

from mountains.db import Repository
from mountains.errors import ValidationError
from mountains.utils import now_utc, readable_id

if TYPE_CHECKING:
    from typing import Self

    from werkzeug.datastructures import FileStorage


class CommitteeRole(enum.Enum):
    # Numbers should be less than 100 here otherwise member sorting might not work
    CHAIR = 1
    VICE_CHAIR = 2
    TREASURER = 3
    SECRETARY = 4
    GENERAL = 10


@define(kw_only=True)
class User:
    id: int
    slug: str
    email: str
    password_hash: str = field(repr=False)
    first_name: str
    last_name: str
    about: str | None
    mobile: str = ""
    in_case_emergency: str = ""
    profile_picture_url: str | None = None
    is_admin: bool = False
    is_committee: bool = False
    is_coordinator: bool = False
    is_winter_skills: bool = False
    discord_id: str | None = None
    membership_expiry: datetime.date | None = None
    is_dormant: bool = False
    created_on_utc: datetime.datetime = Factory(now_utc)
    last_login_utc: datetime.datetime | None = None
    committee_role: CommitteeRole | None = None
    committee_bio: str = ""

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    @property
    def full_name(self) -> str:
        return self.first_name + " " + self.last_name

    @property
    def profile_picture_thumb(self) -> Path | None:
        if self.profile_picture_url is None:
            return None
        return _thumb_path(Path(self.profile_picture_url))

    @property
    def is_member(self) -> bool:
        if self.membership_expiry is None:
            return False
        else:
            return (
                self.membership_expiry
                > datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None).date()
            )

    @property
    def is_site_admin(self) -> bool:
        return self.is_coordinator or self.is_committee or self.is_admin

    @property
    def missing_profile_color(self) -> str:
        # map a -> z to a number between 0 and 360
        h = (ord(self.first_name[0].lower()) - 96) * (360 // 26)
        return f"hsl({h}, 50%, 50%)"

    def is_authorised(self, user_id: int | None = None) -> bool:
        return self.is_site_admin or self.id == user_id

    def check_authorised(self, user_id: int | None = None) -> None:
        if not self.is_authorised(user_id):
            abort(403)

    def is_inactive_on(self, dt_utc: datetime.datetime, threshold_days: int) -> bool:
        if self.is_member:
            return False

        if self.membership_expiry is None:
            if self.created_on_utc + datetime.timedelta(days=threshold_days) < dt_utc:
                return True
            else:
                return False
        else:
            expiry_dt = datetime.datetime.combine(
                self.membership_expiry, datetime.time(0)
            )
            if expiry_dt + datetime.timedelta(days=threshold_days) < dt_utc:
                return True
            else:
                return False

    @classmethod
    def from_registration(
        cls,
        *,
        id: int,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        about: str | None,
    ) -> Self:
        slug = readable_id([first_name, last_name, str(id)])

        if len(first_name) == 0:
            raise ValidationError("First name cannot be blank!")

        if len(last_name) == 0:
            raise ValidationError("First name cannot be blank!")

        if about is not None and len(about) == 0:
            about = None

        return cls(
            id=id,
            slug=slug,
            email=email.lower(),
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            about=about,
        )


def users_repo(conn: sqlite3.Connection) -> Repository[User]:
    return Repository(
        conn=conn,
        table_name="users",
        schema=[
            "id INTEGER PRIMARY KEY",
            "slug TEXT UNIQUE NOT NULL",
            "email TEXT UNIQUE NOT NULL",
            "password_hash TEXT NOT NULL",
            "first_name TEXT NOT NULL",
            "last_name TEXT NOT NULL",
            "about TEXT",
            "mobile TEXT NOT NULL",
            "in_case_emergency TEXT NOT NULL",
            "profile_picture_url TEXT",
            "is_admin BOOLEAN NOT NULL",
            "is_committee BOOLEAN NOT NULL",
            "is_coordinator BOOLEAN NOT NULL",
            "is_winter_skills BOOLEAN NOT NULL",
            "discord_id TEXT",
            "membership_expiry DATE",
            "is_dormant BOOLEAN NOT NULL",
            "committee_role INTEGER",
            "committee_bio INTEGER NOT NULL",
            "created_on_utc DATETIME NOT NULL",
            "last_login_utc DATETIME",
        ],
        storage_cls=User,
    )


def upload_profile(
    file: FileStorage,
    static_dir: Path,
    user: User,
    size: int = 512,
    th_size: int = 32,
) -> str:
    assert file.filename is not None, (
        "upload_profile should always have a file.filename attribute"
    )
    filename = Path(user.slug).with_suffix(Path(file.filename).suffix)
    upload_path = static_dir / "profile" / filename
    file.save(upload_path)

    # Now resize the image using PIL
    with Image.open(upload_path) as im:
        # fit will center and crop
        resized = ImageOps.fit(im, (size, size))
        thumb = ImageOps.fit(im, (th_size, th_size))
        ImageOps.exif_transpose(resized, in_place=True)
        ImageOps.exif_transpose(thumb, in_place=True)

        resized.save(upload_path)
        thumb.save(_thumb_path(upload_path))

    return str(Path("profile") / filename)


def _thumb_path(profile_path: Path) -> Path:
    return profile_path.with_stem(profile_path.stem + ".th")
