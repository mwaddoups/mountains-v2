import argparse
import asyncio
import sqlite3
import uuid
from datetime import datetime

from werkzeug.security import generate_password_hash

from mountains.events import Event, events
from mountains.users import User, users
from mountains.utils import readable_id

parser = argparse.ArgumentParser()
parser.add_argument("input_db")
parser.add_argument("output_db")
args = parser.parse_args()

user_repo = users(args.output_db)
events_repo = events(args.output_db)

pw_hash = generate_password_hash("password")
with sqlite3.connect(args.input_db) as in_conn:
    in_conn.row_factory = sqlite3.Row

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
        random_str = str(uuid.uuid4())[:6]
        u_id = readable_id([u["first_name"], u["last_name"], random_str])

        # TODO: still not importing all fields
        new_user = User(
            id=u_id,
            email=u["email"],
            password_hash=pw_hash,
            first_name=u["first_name"],
            last_name=u["last_name"],
            about=u["about"],
            mobile=u["mobile_number"],
            profile_picture_url=None,
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
    events_repo.drop_table()
    events_repo.create_table()
