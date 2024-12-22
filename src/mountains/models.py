from __future__ import annotations

import uuid
from typing import Self

from attrs import define


@define(kw_only=True)
class User:
    id: str
    email: str
    # password_hash: str
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

    @classmethod
    def from_registration(
        cls,
        *,
        email: str,
        first_name: str,
        last_name: str,
        about: str | None,
    ) -> Self:
        random_str = str(uuid.uuid4())[:6]
        id = first_name + "-" + last_name + "-" + random_str

        return cls(
            id=id, email=email, first_name=first_name, last_name=last_name, about=about
        )
