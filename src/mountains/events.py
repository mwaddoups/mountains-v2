import datetime
import enum
import sqlite3
import uuid

from attrs import define

from mountains.db import Repository


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
    id: str
    title: str
    event_dt: datetime.datetime
    event_end_dt: datetime.datetime | None
    event_type: EventType
    created_on_utc: datetime.datetime
    updated_on_utc: datetime.datetime
    max_attendees: int | None
    is_draft: bool = False
    is_deleted: bool = False
    price_id: str | None = None

    @staticmethod
    def event_types():
        return EventType

    @classmethod
    def from_new_event(
        cls,
        *,
        title: str,
        event_dt_str: str,
        event_end_dt_str: str,
        event_type_str: str,
        max_attendees_str: str,
    ):
        # Convert from the form data
        event_dt = datetime.datetime.fromisoformat(event_dt_str)
        if event_end_dt_str:
            event_end_dt = datetime.datetime.fromisoformat(event_end_dt_str)
        else:
            event_end_dt = None
        event_type = EventType(value=int(event_type_str))
        max_attendees = int(max_attendees_str)

        # Generate a random id that's somewhat readable
        random_str = str(uuid.uuid4())[:6]
        id = title.lower()[:15] + "-" + event_dt.strftime("%Y-%m-%d") + "-" + random_str

        # Timestamp as now
        now_utc = datetime.datetime.now(tz=datetime.UTC)

        return cls(
            id=id,
            title=title,
            event_dt=event_dt,
            event_end_dt=event_end_dt,
            event_type=event_type,
            max_attendees=max_attendees,
            created_on_utc=now_utc,
            updated_on_utc=now_utc,
        )


def events(db_name: str) -> Repository[Event]:
    return Repository(
        db_name=db_name,
        table_name="events",
        schema=[
            "id TEXT PRIMARY KEY",
            "title TEXT NOT NULL",
            "event_dt DATETIME NOT NULL",
            "event_end_dt DATETIME",
            "event_type INTEGER NOT NULL",
            "created_on_utc DATETIME NOT NULL",
            "updated_on_utc DATETIME NOT NULL",
            "max_attendees INTEGER",
            "is_draft BOOLEAN NOT NULL DEFAULT false",
            "is_deleted BOOLEAN NOT NULL DEFAULT false",
            "price_id TEXT",
        ],
        storage_cls=Event,
    )
