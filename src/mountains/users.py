from __future__ import annotations

import datetime
import uuid
from typing import Self

from attr import Factory
from attrs import define, field
from werkzeug.security import generate_password_hash

from mountains.db import Repository


@define(kw_only=True)
class User:
    id: str
    email: str
    password_hash: str = field(repr=False)
    first_name: str
    last_name: str
    about: str | None
    mobile: str
    profile_picture_url: str | None = None
    is_committee: bool = False
    is_coordinator: bool = False
    is_member: bool = False
    # is_on_discord: bool = False
    # is_winter_skills: bool
    # is_dormant: bool
    created_on_utc: datetime.datetime = Factory(
        lambda: datetime.datetime.now(tz=datetime.UTC)
    )
    last_login_utc: datetime.datetime | None = None

    @property
    def full_name(self):
        return self.first_name + " " + self.last_name

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
        id = first_name.lower() + "-" + last_name.lower() + "-" + random_str.lower()

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
            "is_committee BOOLEAN DEFAULT false NOT NULL",
            "is_coordinator BOOLEAN DEFAULT false NOT NULL",
            "is_member BOOLEAN DEFAULT false NOT NULL",
            "created_on_utc DATETIME NOT NULL",
            "last_login_utc DATETIME",
        ],
        storage_cls=User,
    )
