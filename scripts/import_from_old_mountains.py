import argparse
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

from mountains.db import connection
from mountains.events import Attendee, Event, EventType, attendees, events
from mountains.tokens import tokens
from mountains.users import User, users
from mountains.utils import readable_id

parser = argparse.ArgumentParser()
parser.add_argument("input_db")
parser.add_argument("output_db")
args = parser.parse_args()


event_map = {
    "SD": EventType.SUMMER_DAY_WALK,
    "SW": EventType.SUMMER_WEEKEND,
    "WD": EventType.WINTER_DAY_WALK,
    "WW": EventType.WINTER_WEEKEND,
    "CL": EventType.INDOOR_CLIMBING,
    "OC": EventType.OUTDOOR_CLIMBING,
    "RN": EventType.RUNNING,
    "SO": EventType.SOCIAL,
    "CM": EventType.COMMITTEE,
    "XX": EventType.OTHER,
}

pw_hash = generate_password_hash("password")
with (
    sqlite3.connect(args.input_db) as in_conn,
    connection(args.output_db) as out_conn,
):
    in_conn.row_factory = sqlite3.Row
    user_repo = users(out_conn)
    token_repo = tokens(out_conn)
    # recreate tokens
    token_repo.drop_table()
    token_repo.create_table()

    # Do the user import
    user_repo.drop_table()
    user_repo.create_table()
    old_users_res = in_conn.execute("SELECT * FROM members_user")
    old_users = old_users_res.fetchall()
    inserted = 0
    skipped = 0
    for u in old_users:
        u = dict(u)
        if not u["first_name"] or not u["last_name"]:
            skipped += 1
            continue
        u_slug = readable_id([u["first_name"], u["last_name"], str(u["id"])])

        # Take uploads/ off the start
        profile_url = u["profile_picture"][8:]

        # TODO: still not importing all fields
        new_user = User(
            id=u["id"],
            slug=u_slug,
            email=u["email"],
            password_hash=pw_hash,
            first_name=u["first_name"],
            last_name=u["last_name"],
            about=u["about"],
            mobile=u["mobile_number"],
            profile_picture_url=u["profile_picture"][8:]
            if u["profile_picture"]
            else None,
            is_committee=bool(u["is_committee"]),
            is_coordinator=bool(u["is_walk_coordinator"]),
            is_dormant=bool(u["is_dormant"]),
            membership_expiry_utc=datetime.fromisoformat(u["membership_expiry"])
            if u["membership_expiry"] is not None
            else None,
            created_on_utc=datetime.fromisoformat(u["date_joined"]),
            last_login_utc=datetime.fromisoformat(u["last_login"])
            if u["last_login"] is not None
            else None,
        )

        user_repo.insert(new_user)
        inserted += 1
    print(f"Inserted {inserted} users (password: password)")
    print(f"Skipped {skipped} users (blank names)")

    # Do the events import
    events_repo = events(out_conn)
    events_repo.drop_table()
    events_repo.create_table()

    old_events = in_conn.execute("SELECT * FROM events_event").fetchall()
    inserted = 0
    skipped = 0
    for ev in old_events:
        ev = dict(ev)

        new_event = Event.from_new_event(
            id=ev["id"],
            title=ev["title"],
            description=ev["description"],
            event_dt_str=ev["event_date"],
            event_end_dt_str=ev["event_end_date"],
            event_type_str=str(event_map[ev["event_type"]].value),
            max_attendees_str=ev["max_attendees"],
            is_members_only=bool(ev["members_only"]),
        )

        events_repo.insert(new_event)
        inserted += 1
    print(f"Inserted {inserted} events.")

    # Do the events import
    attendees_repo = attendees(out_conn)
    attendees_repo.drop_table()
    attendees_repo.create_table()

    old_attendees = in_conn.execute("SELECT * FROM events_attendinguser").fetchall()
    inserted = 0
    skipped = 0
    for au in old_attendees:
        au = dict(au)
        new_au = Attendee(
            user_id=au["user_id"],
            event_id=au["event_id"],
            is_waiting_list=au["is_waiting_list"],
            is_trip_paid=au["is_trip_paid"],
            joined_at_utc=datetime.fromisoformat(au["list_join_date"]),
        )

        attendees_repo.insert(new_au)
        inserted += 1
    print(f"Inserted {inserted} attendees.")
