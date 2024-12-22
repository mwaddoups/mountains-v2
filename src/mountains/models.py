import uuid

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
