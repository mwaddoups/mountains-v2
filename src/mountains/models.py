from __future__ import annotations

import uuid
from typing import Self

from attrs import define, field
from werkzeug.security import generate_password_hash


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
    # created_on_utc: datetime.datetime
    # last_login_utc: datetime.datetime (utc)

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
