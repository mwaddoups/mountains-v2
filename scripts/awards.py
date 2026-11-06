import datetime
import sqlite3
from collections import defaultdict
from typing import Callable

from mountains.db import connection
from mountains.events import Event
from mountains.models.activity import activity_repo
from mountains.models.events import EventType, attendees_repo, events_repo
from mountains.models.users import User, users_repo

with connection("test.db") as conn:
    users = {u.id: u for u in users_repo(conn).list()}
    events = {e.id: e for e in events_repo(conn).list()}
    att_users = attendees_repo(conn).list()
    activity = activity_repo(conn).list()

    def _print_events(filter: Callable[[Event], bool]):
        counter = defaultdict(int)
        for au in att_users:
            event = events[au.event_id]
            user = users[au.user_id]
            if event.event_dt.date() > datetime.date(
                2021, 1, 1
            ) and event.event_dt.date() < datetime.date(2026, 11, 25):
                if not au.is_waiting_list:
                    if filter(event):
                        counter[user.full_name] += 1

        for i, (name, count) in enumerate(
            sorted(counter.items(), key=lambda x: x[1], reverse=True)[:5]
        ):
            print(f"{i + 1}. {name} ({count} events)")
        print()

    print("OVERALL # OF EVENTS")
    _print_events(lambda event: True)

    print("WALKING EVENTS")
    _print_events(
        lambda event: event.event_type
        in (EventType.SUMMER_DAY_WALK, EventType.WINTER_DAY_WALK)
    )

    print("HUT WEEKENDS")
    _print_events(
        lambda event: event.event_type
        in (EventType.SUMMER_WEEKEND, EventType.WINTER_WEEKEND)
    )

    print("TRAIL RUNNING (ex. wednesday events)")
    _print_events(
        lambda event: event.event_type == EventType.RUNNING
        and event.event_dt.weekday() != 2
    )

    print("CLIMBING (ex. events mentioning GCC, prop store, brushworks, newsroom)")
    _print_events(
        lambda event: event.event_type
        in (EventType.INDOOR_CLIMBING, EventType.OUTDOOR_CLIMBING)
        and not (
            ("gcc" in event.title.lower())
            or ("brushworks" in event.title.lower())
            or ("prop store" in event.title.lower())
            or ("newsroom" in event.title.lower())
        )
    )

    print("SOCIALS")
    _print_events(lambda event: event.event_type == EventType.SOCIAL)

    print("BIGGEST LEAVER!!")
    counter = defaultdict(int)
    for a in activity:
        if a.event_id is not None and a.user_id is not None:
            event = events[a.event_id]
            user = users[a.user_id]
            if event.event_dt.date() > datetime.date(
                2026, 1, 1
            ) and event.event_dt.date() < datetime.date(2026, 11, 25):
                if a.action == "left":
                    counter[user.full_name] += 1

    for i, (name, count) in enumerate(
        sorted(counter.items(), key=lambda x: x[1], reverse=True)[:5]
    ):
        print(f"{i + 1}. {name} ({count} events)")
    print()

    print()
