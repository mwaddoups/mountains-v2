from __future__ import annotations

import datetime
import enum
import sqlite3
import zoneinfo
from typing import TYPE_CHECKING

from attrs import Factory, define

from mountains.db import Repository
from mountains.errors import MountainException
from mountains.models.users import User
from mountains.utils import now_utc, readable_id

if TYPE_CHECKING:
    from typing import Self

    from werkzeug.datastructures import ImmutableMultiDict


class EventType(enum.Enum):
    SUMMER_DAY_WALK = 1
    SUMMER_WEEKEND = 2
    WINTER_DAY_WALK = 3
    WINTER_WEEKEND = 4
    INDOOR_CLIMBING = 5
    OUTDOOR_CLIMBING = 6
    RUNNING = 7
    SOCIAL = 8
    COMMITTEE = 9
    OTHER = 10


sqlite3.register_adapter(EventType, lambda x: x.value)


@define(kw_only=True)
class Event:
    id: int
    slug: str
    title: str
    description: str
    event_dt: datetime.datetime
    event_end_dt: datetime.datetime | None
    event_type: EventType
    created_on_utc: datetime.datetime
    updated_on_utc: datetime.datetime
    max_attendees: int | None
    show_participation_ice: bool
    signup_open_dt: datetime.datetime | None
    is_members_only: bool
    is_draft: bool
    is_deleted: bool
    is_locked: bool
    price_id: str | None

    def is_full(self, attendees: list[Attendee]) -> bool:
        if any(a.is_waiting_list for a in attendees):
            return True

        if self.max_attendees is None or self.max_attendees == 0:
            return False
        else:
            return len(attendees) >= self.max_attendees

    def is_upcoming_on(self, dt: datetime.date) -> bool:
        return self.event_dt.date() >= dt or (
            self.event_end_dt is not None and self.event_end_dt.date() >= dt
        )

    def is_upcoming(self) -> bool:
        return self.is_upcoming_on(now_utc().date())

    def is_happening_on(self, dt: datetime.date) -> bool:
        if self.event_end_dt is None:
            return self.event_dt.date() == dt
        else:
            return self.event_dt.date() <= dt and self.event_end_dt.date() >= dt

    def is_open(self) -> bool:
        if self.signup_open_dt is None:
            return True
        else:
            # This is in GMT time
            return self.signup_open_dt < datetime.datetime.now(
                tz=zoneinfo.ZoneInfo("Europe/London")
            ).replace(tzinfo=None)

    def popups_for(self, user: User) -> list[str]:
        popups = []
        if user.discord_id is None:
            popups.append("discord")

        if not user.is_member and self.is_members_only:
            popups.append("members_only")

        if self.show_participation_ice or len(user.in_case_emergency) == 0:
            popups.append("ice")

        if self.show_participation_ice:
            popups.append("statement")

        return popups

    def needs_payment_from(self, attendee: Attendee) -> bool:
        if not self.price_id:
            return False
        else:
            if attendee.is_waiting_list:
                return False
            else:
                return not attendee.is_trip_paid

    def is_part_of_trial(self) -> bool:
        return self.event_type in [
            EventType.SUMMER_DAY_WALK,
            EventType.SUMMER_WEEKEND,
            EventType.WINTER_DAY_WALK,
            EventType.WINTER_WEEKEND,
            EventType.OUTDOOR_CLIMBING,
            EventType.RUNNING,
        ]

    @classmethod
    def from_form(
        cls,
        *,
        id: int,
        form: ImmutableMultiDict[str, str],
        created_on_utc: datetime.datetime | None = None,
        updated_on_utc: datetime.datetime | None = None,
        is_deleted: bool = False,
    ) -> Self:
        if len(title := form["title"]) == 0:
            raise MountainException("Title must not be blank!")

        # Convert from the form data
        event_dt = datetime.datetime.fromisoformat(form["event_dt"])
        event_end_dt = form.get(
            "event_end_dt", type=datetime.datetime.fromisoformat, default=None
        )
        if event_end_dt is not None and event_end_dt < event_dt:
            raise MountainException(
                "Provided end date must be later than the start date!"
            )
        event_type = EventType(value=form.get("event_type", type=int))
        signup_open_dt = form.get(
            "signup_open_dt", type=datetime.datetime.fromisoformat, default=None
        )

        slug = readable_id([event_dt.strftime("%Y-%m-%d"), title, str(id)])

        # Timestamp as now
        now = now_utc()
        if created_on_utc is None:
            created_on_utc = now
        if updated_on_utc is None:
            updated_on_utc = now

        return cls(
            id=id,
            slug=slug,
            title=title,
            description=form["description"],
            event_dt=event_dt,
            event_end_dt=event_end_dt,
            event_type=event_type,
            max_attendees=form.get("max_attendees", type=int),
            show_participation_ice="show_participation_ice" in form,
            is_members_only="is_members_only" in form,
            signup_open_dt=signup_open_dt,
            is_locked="is_locked" in form,
            price_id=form.get("price_id"),
            is_draft="is_draft" in form,
            is_deleted=False,
            created_on_utc=now,
            updated_on_utc=now,
        )

    def to_form(self) -> dict[str, str]:
        as_form = {
            "title": self.title,
            "description": self.description,
            "event_dt": self.event_dt.isoformat(),
            "event_end_dt": self.event_end_dt.isoformat() if self.event_end_dt else "",
            "event_type": str(self.event_type.value),
            "max_attendees": str(self.max_attendees),
            "signup_open_dt": self.signup_open_dt.isoformat()
            if self.signup_open_dt
            else "",
            "price_id": self.price_id if self.price_id else "",
        }
        # Booleans are only there if true
        if self.is_members_only:
            as_form["is_members_only"] = "1"
        if self.show_participation_ice:
            as_form["show_participation_ice"] = "1"
        if self.is_locked:
            as_form["is_locked"] = "1"
        if self.is_draft:
            as_form["is_draft"] = "1"
        return as_form


@define(kw_only=True)
class Attendee:
    user_id: int
    event_id: int
    joined_at_utc: datetime.datetime = Factory(now_utc)
    is_waiting_list: bool = False
    is_trip_paid: bool = False


def events_repo(conn: sqlite3.Connection) -> Repository[Event]:
    return Repository(
        conn=conn,
        table_name="events",
        schema=[
            "id INTEGER PRIMARY KEY",
            "slug TEXT UNIQUE",
            "title TEXT NOT NULL",
            "description TEXT NOT NULL",
            "event_dt DATETIME NOT NULL",
            "event_end_dt DATETIME",
            "event_type INTEGER NOT NULL",
            "created_on_utc DATETIME NOT NULL",
            "updated_on_utc DATETIME NOT NULL",
            "signup_open_dt DATETIME",
            "max_attendees INTEGER",
            "show_participation_ice BOOLEAN NOT NULL",
            "is_members_only BOOLEAN NOT NULL DEFAULT false",
            "is_draft BOOLEAN NOT NULL DEFAULT false",
            "is_deleted BOOLEAN NOT NULL DEFAULT false",
            "is_locked BOOLEAN NOT NULL DEFAULT false",
            "price_id TEXT",
        ],
        storage_cls=Event,
    )


def attendees_repo(conn: sqlite3.Connection) -> Repository[Attendee]:
    return Repository(
        conn=conn,
        table_name="attendees",
        schema=[
            "user_id INTEGER NOT NULL",
            "event_id INTEGER NOT NULL",
            "joined_at_utc DATETIME NOT NULL",
            "is_waiting_list BOOLEAN NOT NULL DEFAULT false",
            "is_trip_paid BOOLEAN NOT NULL DEFAULT false",
            "PRIMARY KEY(user_id, event_id)",
            "FOREIGN KEY(user_id) REFERENCES users(id)",
            "FOREIGN KEY(event_id) REFERENCES events(id)",
        ],
        storage_cls=Attendee,
    )
