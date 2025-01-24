import argparse
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

from mountains.db import connection
from mountains.models.activity import Activity, activity_repo
from mountains.models.events import (
    Attendee,
    Event,
    EventType,
    attendees_repo,
    events_repo,
)
from mountains.models.photos import Album, Photo, albums_repo, photos_repo
from mountains.models.tokens import tokens_repo
from mountains.models.users import User, users_repo
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
    user_repo = users_repo(out_conn)
    tokens_db = tokens_repo(out_conn)
    # recreate tokens
    tokens_db.drop_table()
    tokens_db.create_table()

    # Do the user import
    user_repo.drop_table()
    user_repo.create_table()
    old_users_res = in_conn.execute("SELECT * FROM members_user")
    old_users = old_users_res.fetchall()
    inserted = 0
    skipped = 0
    for u in old_users:
        u = dict(u)
        if not u["first_name"] or not u["last_name"] or not bool(u["is_approved"]):
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
            in_case_emergency=u["in_case_emergency"],
            discord_id=u["discord_id"],
            profile_picture_url=u["profile_picture"][8:]
            if u["profile_picture"]
            else None,
            is_committee=bool(u["is_committee"]),
            is_coordinator=bool(u["is_walk_coordinator"]),
            is_dormant=bool(u["is_dormant"]),
            membership_expiry=datetime.fromisoformat(u["membership_expiry"]).date()
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
    print(f"Skipped {skipped} users (blank names, or not approved)")

    # Do the events import
    events_db = events_repo(out_conn)
    events_db.drop_table()
    events_db.create_table()

    old_events = in_conn.execute("SELECT * FROM events_event").fetchall()
    inserted = 0
    skipped = 0
    for ev in old_events:
        ev = dict(ev)
        ev_slug = readable_id([
            datetime.fromisoformat(ev["event_date"]).strftime("%Y-%m-%d"),
            ev["title"],
            str(ev["id"]),
        ])

        new_event = Event(
            id=ev["id"],
            slug=ev_slug,
            title=ev["title"],
            description=ev["description"],
            event_dt=datetime.fromisoformat(ev["event_date"]),
            event_end_dt=datetime.fromisoformat(ev["event_end_date"])
            if ev["event_end_date"]
            else None,
            created_on_utc=datetime.fromisoformat(ev["created_date"]),
            updated_on_utc=datetime.fromisoformat(ev["created_date"]),
            event_type=event_map[ev["event_type"]],
            max_attendees=int(ev["max_attendees"]),
            signup_open_dt=datetime.fromisoformat(ev["signup_open_date"])
            if ev["signup_open_date"]
            else None,
            show_participation_ice=bool(ev["show_popup"]),
            is_members_only=bool(ev["members_only"]),
            is_locked=not bool(ev["signup_open"]),
            price_id=ev["price_id"],
            is_draft=False,
            is_deleted=bool(ev["is_deleted"]),
        )

        events_db.insert(new_event)
        inserted += 1
    print(f"Inserted {inserted} events.")

    # Do the attendees import
    attendees_db = attendees_repo(out_conn)
    attendees_db.drop_table()
    attendees_db.create_table()

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

        attendees_db.insert(new_au)
        inserted += 1
    print(f"Inserted {inserted} attendees.")

    # Do the albums import
    albums_db = albums_repo(out_conn)
    albums_db.drop_table()
    albums_db.create_table()

    old_albums = in_conn.execute("SELECT * FROM photos_album").fetchall()
    inserted = 0
    skipped = 0
    for al in old_albums:
        al = dict(al)
        new_al = Album(
            id=al["id"],
            name=al["name"],
            event_date=datetime.fromisoformat(al["event_date"]).date()
            if al["event_date"]
            else None,
            created_at_utc=datetime.fromisoformat(al["created"]),
        )

        albums_db.insert(new_al)
        inserted += 1
    print(f"Inserted {inserted} albums.")

    # Do the photos import
    photos_db = photos_repo(out_conn)
    photos_db.drop_table()
    photos_db.create_table()

    old_photos = in_conn.execute("SELECT * FROM photos_photo").fetchall()
    inserted = 0
    skipped = 0
    for p in old_photos:
        p = dict(p)
        if p["album_id"] and p["uploader_id"]:
            new_p = Photo(
                id=p["id"],
                starred=p["starred"],
                uploader_id=p["uploader_id"],
                photo_path=p["photo"],
                album_id=p["album_id"],
                created_at_utc=datetime.fromisoformat(p["uploaded"]),
            )

            photos_db.insert(new_p)
            inserted += 1
        else:
            skipped += 1
    print(
        f"Inserted {inserted} photos (skipped {skipped} for missing album or uploader id)."
    )

    # Do the activity import
    activity_db = activity_repo(out_conn)
    activity_db.drop_table()
    activity_db.create_table()

    old_activity = in_conn.execute("SELECT * FROM activity_activity").fetchall()
    inserted = 0
    skipped = 0
    for a in old_activity:
        a = dict(a)
        new_a = Activity(
            user_id=a["user_id"],
            event_id=a["event_id"],
            dt=datetime.fromisoformat(a["timestamp"]),
            action=a["action"],
        )

        activity_db.insert(new_a)
        inserted += 1
    print(f"Inserted {inserted} activities")
