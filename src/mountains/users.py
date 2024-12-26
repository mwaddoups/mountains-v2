from __future__ import annotations

import datetime
import sqlite3
import uuid
from typing import Self

from attrs import Factory, define, field
from werkzeug.security import generate_password_hash

from mountains.db import Repository
from mountains.utils import now_utc, readable_id


@define(kw_only=True)
class User:
    id: int
    slug: str
    email: str
    password_hash: str = field(repr=False)
    first_name: str
    last_name: str
    about: str | None
    mobile: str
    profile_picture_url: str | None
    is_committee: bool
    is_coordinator: bool
    # is_on_discord: bool = False
    # is_winter_skills: bool
    membership_expiry_utc: datetime.datetime | None
    is_dormant: bool
    created_on_utc: datetime.datetime
    last_login_utc: datetime.datetime | None = None

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    @property
    def full_name(self) -> str:
        return self.first_name + " " + self.last_name

    @property
    def is_member(self) -> bool:
        if self.membership_expiry_utc is None:
            return False
        else:
            return self.membership_expiry_utc > datetime.datetime.now(
                tz=datetime.UTC
            ).replace(tzinfo=None)

    @property
    def missing_profile_color(self) -> str:
        # map a -> z to a number between 0 and 360
        h = (ord(self.first_name[0].lower()) - 96) * (360 // 26)
        return f"hsl({h}, 50%, 50%)"

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
        mobile: str,
    ) -> Self:
        slug = readable_id([first_name, last_name, str(id)])

        return cls(
            id=id,
            slug=slug,
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            about=about,
            mobile=mobile,
            profile_picture_url=None,
            is_committee=False,
            is_coordinator=False,
            membership_expiry_utc=None,
            is_dormant=False,
            created_on_utc=now_utc(),
        )


def users(conn: sqlite3.Connection) -> Repository[User]:
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
            "mobile TEXT",
            "profile_picture_url TEXT",
            "is_committee BOOLEAN NOT NULL",
            "is_coordinator BOOLEAN NOT NULL",
            "membership_expiry_utc DATETIME",
            "is_dormant BOOLEAN NOT NULL",
            "created_on_utc DATETIME NOT NULL",
            "last_login_utc DATETIME",
        ],
        storage_cls=User,
    )
