import argparse
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
    with sqlite3.connect(args.output_db) as out_conn:
        in_conn.row_factory = sqlite3.Row
        out_conn.row_factory = sqlite3.Row

        # Do the user import
        user_repo.drop_table()
        user_repo.create_table()
        old_users = in_conn.execute("SELECT * FROM members_user").fetchall()
        for u in old_users:
            u = dict(u)
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
                created_on_utc=datetime.fromisoformat(u["date_joined"]),
                last_login_utc=datetime.fromisoformat(u["last_login"])
                if u["last_login"] is not None
                else None,
            )
            print(new_user)

            user_repo.insert(new_user)
        print(f"Inserted {len(old_users)} users (password: password).")

        # Do the events import
        events_repo.drop_table()
        events_repo.create_table()
