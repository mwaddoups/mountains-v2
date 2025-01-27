import argparse
import json
import uuid
from datetime import datetime

from cattrs import structure
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
from mountains.models.users import CommitteeRole, User, users_repo
from mountains.utils import readable_id

parser = argparse.ArgumentParser()
parser.add_argument("input_datadump")
parser.add_argument("output_db")
parser.add_argument("--scramble-pw", action="store_true")
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

with open(args.input_datadump) as f:
    input_data = json.load(f)
    # List of json objects which each have 'model', 'fields'
    # Models are
    # {'photos.album', 'drfpasswordless.callbacktoken', 'events.event', 'members.experience',
    # 'payments.membershipprice', 'sessions.session', 'members.user', 'kit.kit', 'kit.kitborrow', 'events.attendinguser',
    # 'activity.activity', 'authtoken.token', 'photos.photo', 'admin.logentry'}

with connection(args.output_db) as out_conn:
    user_repo = users_repo(out_conn)
    tokens_db = tokens_repo(out_conn)
    # recreate tokens
    tokens_db.drop_table()
    tokens_db.create_table()

    # Do the user import
    user_repo.drop_table()
    user_repo.create_table()
    old_users = [
        {"id": d["pk"], **d["fields"]}
        for d in input_data
        if d["model"] == "members.user"
    ]
    inserted = 0
    skipped = 0
    for u in old_users:
        # In the datadump, IDs start at 1
        id = u["id"]
        if not u["first_name"] or not u["last_name"] or not bool(u["is_approved"]):
            skipped += 1
            continue
        u_slug = readable_id([u["first_name"], u["last_name"], str(id)])

        # Take uploads/ off the start
        profile_url = u["profile_picture"][8:]

        if u["committee_role"] == "Chair":
            committee_role = CommitteeRole.CHAIR
        elif u["committee_role"] == "Vice-Chair":
            committee_role = CommitteeRole.VICE_CHAIR
        elif u["committee_role"] == "Treasurer":
            committee_role = CommitteeRole.TREASURER
        elif u["committee_role"] == "Secretary":
            committee_role = CommitteeRole.SECRETARY
        elif u["committee_role"] == "General":
            committee_role = CommitteeRole.GENERAL
        elif u["committee_role"] == "":
            committee_role = None
        else:
            raise Exception(f"Unknown role {u['committee_role']:!r} !")

        new_user = structure(
            dict(
                id=id,
                slug=u_slug,
                email=u["email"],
                password_hash=str(uuid.uuid4()) if args.scramble_pw else pw_hash,
                first_name=u["first_name"],
                last_name=u["last_name"],
                about=u["about"],
                mobile=u["mobile_number"],
                in_case_emergency=u["in_case_emergency"],
                discord_id=u["discord_id"],
                profile_picture_url=u["profile_picture"][8:]
                if u["profile_picture"]
                else None,
                is_admin=True if u["email"] == "mwaddoups@gmail.com" else False,
                is_committee=bool(u["is_committee"]),
                is_coordinator=bool(u["is_walk_coordinator"]),
                is_dormant=bool(u["is_dormant"]),
                membership_expiry=u["membership_expiry"],
                created_on_utc=u["date_joined"],
                last_login_utc=u["last_login"],
                committee_role=committee_role,
                committee_bio=u["committee_bio"]
                if u["committee_bio"] is not None
                else "",
            ),
            User,
        )

        user_repo.insert(new_user)
        inserted += 1
    if args.scramble_pw:
        print(f"Inserted {inserted} users (password: <scrambled>)")
    else:
        print(f"Inserted {inserted} users (password: password)")
    print(f"Skipped {skipped} users (blank names, or not approved)")

    # Do the events import
    events_db = events_repo(out_conn)
    events_db.drop_table()
    events_db.create_table()

    old_events = [
        {"id": d["pk"], **d["fields"]}
        for d in input_data
        if d["model"] == "events.event"
    ]
    inserted = 0
    skipped = 0
    for ev in old_events:
        id = ev["id"]
        ev_slug = readable_id([
            datetime.fromisoformat(ev["event_date"]).strftime("%Y-%m-%d"),
            ev["title"],
            str(id),
        ])

        new_event = structure(
            dict(
                id=id,
                slug=ev_slug,
                title=ev["title"],
                description=ev["description"],
                event_dt=(ev["event_date"]),
                event_end_dt=(ev["event_end_date"]) if ev["event_end_date"] else None,
                created_on_utc=(ev["created_date"]),
                updated_on_utc=(ev["created_date"]),
                event_type=event_map[ev["event_type"]],
                max_attendees=int(ev["max_attendees"]),
                signup_open_dt=(ev["signup_open_date"])
                if ev["signup_open_date"]
                else None,
                show_participation_ice=bool(ev["show_popup"]),
                is_members_only=bool(ev["members_only"]),
                is_locked=not bool(ev["signup_open"]),
                price_id=ev["price_id"],
                is_draft=False,
                is_deleted=bool(ev["is_deleted"]),
            ),
            Event,
        )

        events_db.insert(new_event)
        inserted += 1
    print(f"Inserted {inserted} events.")

    # Do the attendees import
    attendees_db = attendees_repo(out_conn)
    attendees_db.drop_table()
    attendees_db.create_table()

    old_attendees = [
        d["fields"] for d in input_data if d["model"] == "events.attendinguser"
    ]

    inserted = 0
    skipped = 0
    for au in old_attendees:
        new_au = structure(
            dict(
                user_id=au["user"],
                event_id=au["event"],
                is_waiting_list=au["is_waiting_list"],
                is_trip_paid=au["is_trip_paid"],
                joined_at_utc=(au["list_join_date"]),
            ),
            Attendee,
        )

        attendees_db.insert(new_au)
        inserted += 1
    print(f"Inserted {inserted} attendees.")

    # Do the albums import
    albums_db = albums_repo(out_conn)
    albums_db.drop_table()
    albums_db.create_table()

    old_albums = [
        {"id": d["pk"], **d["fields"]}
        for d in input_data
        if d["model"] == "photos.album"
    ]
    inserted = 0
    skipped = 0
    for al in old_albums:
        id = al["id"]
        new_al = structure(
            dict(
                id=id,
                name=al["name"],
                event_date=(al["event_date"]),
                created_at_utc=(al["created"]),
            ),
            Album,
        )

        albums_db.insert(new_al)
        inserted += 1
    print(f"Inserted {inserted} albums.")

    # Do the photos import
    photos_db = photos_repo(out_conn)
    photos_db.drop_table()
    photos_db.create_table()

    old_photos = [
        {"id": d["pk"], **d["fields"]}
        for d in input_data
        if d["model"] == "photos.photo"
    ]
    inserted = 0
    skipped = 0
    for p in old_photos:
        id = p["id"]
        if p["album"] and p["uploader"]:
            new_p = structure(
                dict(
                    id=id,
                    starred=p["starred"],
                    uploader_id=p["uploader"],
                    photo_path=p["photo"],
                    album_id=p["album"],
                    created_at_utc=(p["uploaded"]),
                ),
                Photo,
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

    old_activity = [
        d["fields"] for d in input_data if d["model"] == "activity.activity"
    ]
    inserted = 0
    skipped = 0
    for a in old_activity:
        new_a = structure(
            dict(
                user_id=a["user"],
                event_id=a["event"],
                dt=(a["timestamp"]),
                action=a["action"],
            ),
            Activity,
        )

        activity_db.insert(new_a)
        inserted += 1
    print(f"Inserted {inserted} activities")
