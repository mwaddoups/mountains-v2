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
    # mobile: str
    first_name: str
    last_name: str
    about: str | None
    # profile_picture_link: str | None
    # is_committee: bool
    # is_coordinator: bool
    # is_member: bool
    # is_on_discord: bool
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
            "created_on_utc DATETIME",
            "last_login_utc DATETIME",
        ],
        storage_cls=User,
    )
