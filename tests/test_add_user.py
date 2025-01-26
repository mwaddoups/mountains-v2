from concurrent.futures import ThreadPoolExecutor

from flask import Flask, g

from mountains.context import current_user, db_conn
from mountains.events import _add_user_to_event
from mountains.models.events import attendees_repo, events_repo
from mountains.models.users import users_repo

app = Flask(__name__)
app.config.from_prefixed_env("FLASK")


def test_add(event, user_id):
    app = Flask(__name__)
    app.config.from_prefixed_env("FLASK")
    with app.app_context():
        with db_conn() as conn:
            g.current_user = users_repo(conn).get(id=user_id)
            attendees_repo(conn).delete_where(user_id=user_id, event_id=event.id)
        _add_user_to_event(event, user_id)
        print(current_user.full_name)


with app.app_context():
    with db_conn() as conn:
        event = events_repo(conn).get_or_404(id=490)
        target_users = [u.id for u in users_repo(conn).list() if u.is_member]

    with ThreadPoolExecutor(max_workers=24) as exec:
        for out in exec.map(lambda u: test_add(event, u), target_users):
            pass
