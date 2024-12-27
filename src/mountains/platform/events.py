import datetime

from quart import Blueprint, current_app, render_template, request

from mountains.db import connection
from mountains.errors import MountainException

from ..events import Event, attendees
from ..events import events as events_repo
from ..users import users


def event_routes(blueprint: Blueprint):
    @blueprint.route("/events", methods=["GET", "POST"])
    async def events():
        if request.method == "POST":
            form_data = await request.form

            with connection(current_app.config["DB_NAME"], locked=True) as conn:
                events_db = events_repo(conn)

                event = Event.from_new_event(
                    id=events_db.next_id(),
                    title=form_data["title"],
                    description=form_data["description"],
                    event_dt_str=form_data["event_dt"],
                    event_end_dt_str=form_data["event_end_dt"],
                    event_type_str=form_data["event_type"],
                    max_attendees_str=form_data["max_attendees"],
                    is_members_only=form_data["is_members_only"],
                )
                events_db.insert(event)

            # TODO: Audit the event

        # TODO: reasonable day threshold, old and new events
        with connection(current_app.config["DB_NAME"]) as conn:
            events = sorted(
                [
                    e
                    for e in events_repo(conn).list()
                    if e.event_dt > datetime.datetime.now() - datetime.timedelta(days=2)
                ],
                key=lambda e: e.event_dt,
            )

            # Fetch the attendees and users we absolutely need
            # TODO inner join!
            attendees_db = attendees(conn)
            users_db = users(conn)
            event_attendees = {}
            event_members = {}
            for event in events:
                attending_users = attendees_db.list_where(event_id=event.id)
                for att_user in attending_users:
                    if att_user.user_id not in event_members:
                        event_members[att_user.user_id] = users_db.get(
                            id=att_user.user_id
                        )
                event_attendees[event.id] = attending_users

        return await render_template(
            "platform/events.html.j2",
            events=events,
            attendees=event_attendees,
            members=event_members,
        )

    @blueprint.route("/events/add")
    @blueprint.route("/events/edit/<id>")
    async def edit_event(id: str | None = None):
        if id is not None:
            with connection(current_app.config["DB_NAME"]) as conn:
                event = events_repo(conn).get(id=id)
            if event is None:
                raise MountainException("Event not found!")
        else:
            event = None
        return await render_template(
            "platform/event.edit.html.j2", event=event, event_types=Event.event_types()
        )
