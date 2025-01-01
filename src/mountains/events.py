from __future__ import annotations

import datetime
import enum
import sqlite3

from attrs import Factory, define

from mountains.db import Repository
from mountains.utils import now_utc, readable_id


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
    is_members_only: bool = False
    is_draft: bool = False
    is_deleted: bool = False
    price_id: str | None = None

    def is_full(self, attendees: list[Attendee]) -> bool:
        if self.max_attendees is None or self.max_attendees == 0:
            return False

        if any(a.is_waiting_list for a in attendees):
            return True

        return len(attendees) >= self.max_attendees

    @classmethod
    def from_new_event(
        cls,
        *,
        id: int,
        title: str,
        description: str,
        event_dt_str: str,
        event_end_dt_str: str,
        event_type_str: str,
        max_attendees_str: str,
        is_members_only: bool,
    ):
        # Convert from the form data
        event_dt = datetime.datetime.fromisoformat(event_dt_str)
        if event_end_dt_str:
            event_end_dt = datetime.datetime.fromisoformat(event_end_dt_str)
        else:
            event_end_dt = None
        event_type = EventType(value=int(event_type_str))
        max_attendees = int(max_attendees_str)

        slug = readable_id([event_dt.strftime("%Y-%m-%d"), title, str(id)])

        # Timestamp as now
        now = now_utc()

        return cls(
            id=id,
            slug=slug,
            title=title,
            description=description,
            event_dt=event_dt,
            event_end_dt=event_end_dt,
            event_type=event_type,
            max_attendees=max_attendees,
            is_members_only=is_members_only,
            created_on_utc=now,
            updated_on_utc=now,
        )


@define(kw_only=True)
class Attendee:
    user_id: int
    event_id: int
    joined_at_utc: datetime.datetime = Factory(now_utc)
    is_waiting_list: bool = False
    is_trip_paid: bool = False


def events(conn: sqlite3.Connection) -> Repository[Event]:
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
            "max_attendees INTEGER",
            "is_members_only BOOLEAN NOT NULL DEFAULT false",
            "is_draft BOOLEAN NOT NULL DEFAULT false",
            "is_deleted BOOLEAN NOT NULL DEFAULT false",
            "price_id TEXT",
        ],
        storage_cls=Event,
    )


def attendees(conn: sqlite3.Connection) -> Repository[Attendee]:
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
