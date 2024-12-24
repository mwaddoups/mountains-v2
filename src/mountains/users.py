from __future__ import annotations

import datetime
import uuid
from typing import Self

from attrs import Factory, define, field
from werkzeug.security import generate_password_hash

from mountains.db import Repository
from mountains.utils import readable_id


@define(kw_only=True)
class User:
    id: str
    email: str
    password_hash: str = field(repr=False)
    first_name: str
    last_name: str
    about: str | None
    mobile: str
    profile_picture_url: str | None
    is_committee: bool
    is_coordinator: bool
    # is_member: bool
    # is_on_discord: bool = False
    # is_winter_skills: bool
    # is_dormant: bool
    created_on_utc: datetime.datetime = Factory(
        lambda: datetime.datetime.now(tz=datetime.UTC)
    )
    last_login_utc: datetime.datetime | None = None

    @property
    def full_name(self) -> str:
        return self.first_name + " " + self.last_name

    @property
    def is_member(self) -> bool:
        # TODO: Implement this
        return False

    @property
    def missing_profile_color(self) -> str:
        # map a -> z to a number between 0 and 360
        h = (ord(self.id[0].lower()) - 96) * (360 // 26)
        return f"hsl({h}, 50%, 50%)"

    @classmethod
    def from_registration(
        cls,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        about: str | None,
        mobile: str,
    ) -> Self:
        # Generate a random id that's somewhat readable
        random_str = str(uuid.uuid4())[:6]
        id = readable_id([first_name, last_name, random_str])

        # Generate password
        password_hash = generate_password_hash(password)

        return cls(
            id=id,
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
            about=about,
            mobile=mobile,
            profile_picture_url=None,
            is_committee=False,
            is_coordinator=False,
        )


def users(db_name: str) -> Repository[User]:
    return Repository(
        db_name=db_name,
        table_name="users",
        schema=[
            "id TEXT PRIMARY KEY",
            "email TEXT UNIQUE NOT NULL",
            "password_hash TEXT NOT NULL",
            "first_name TEXT NOT NULL",
            "last_name TEXT NOT NULL",
            "about TEXT",
            "mobile TEXT",
            "profile_picture_url TEXT",
            "is_committee BOOLEAN DEFAULT false NOT NULL",
            "is_coordinator BOOLEAN DEFAULT false NOT NULL",
            "is_member BOOLEAN DEFAULT false NOT NULL",
            "created_on_utc DATETIME NOT NULL",
            "last_login_utc DATETIME",
        ],
        storage_cls=User,
    )
