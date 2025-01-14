from __future__ import annotations

import datetime
import logging
from sqlite3 import Connection

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.db import connection
from mountains.errors import MountainException
from mountains.utils import now_utc

from ..events import Attendee, Event, EventType, attendees
from ..events import events as events_repo
from ..users import User
from ..users import users as users_repo

logger = logging.getLogger(__name__)


def event_routes(blueprint: Blueprint):
    @blueprint.route("/events", methods=["GET", "POST"])
    def events(id: int | None = None):
        if request.method == "POST":
            # TODO: Permissions
            form_data = request.form

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
                    is_members_only=bool(form_data["is_members_only"]),
                )
                events_db.insert(event)

            # TODO: Audit the event
            return redirect(url_for("events", id=event.id))
        else:
            search = request.args.get("search")
            if start_dt_str := request.args.get("start_dt"):
                start_dt = datetime.date.fromisoformat(start_dt_str)
            elif "start_dt" in request.args:
                # Intentionally empty
                start_dt = None
            else:
                start_dt = now_utc().date()

            if "event_type" in request.args:
                event_types = request.args.getlist("event_type", type=int)
            else:
                event_types = [t.value for t in EventType]

            with connection(current_app.config["DB_NAME"]) as conn:
                events = [
                    e
                    for e in events_repo(conn).list()
                    if e.event_type.value in event_types
                ]

                if search:
                    events = [e for e in events if search.lower() in e.title.lower()]

                if start_dt is not None:
                    events = [e for e in events if e.is_upcoming_on(start_dt)]

                # Sort all future events in ascending, then all past in descending
                today = now_utc().date()
                events = sorted(
                    [e for e in events if e.is_upcoming_on(today)],
                    key=lambda e: e.event_dt,
                ) + sorted(
                    [e for e in events if not e.is_upcoming_on(today)],
                    reverse=True,
                    key=lambda e: e.event_dt,
                )

                event_attendees, event_members = _events_attendees(conn, events)

            return render_template(
                "platform/events.html.j2",
                events=events,
                event_type_set=EventType,
                attendees=event_attendees,
                members=event_members,
                start_dt=start_dt,
                search=search,
                event_types=event_types,
            )

    @blueprint.route("/events/<id>", methods=["GET", "PUT", "DELETE"])
    def event(id: int):
        return render_template(
            "platform/events.html.j2",
            events=events,
            attendees=event_attendees,
            members=event_members,
        )

    @blueprint.route("/events/calendar")
    @blueprint.route("/events/calendar/<int:year>/<int:month>")
    def events_calendar(year: int | None = None, month: int | None = None):
        now = now_utc()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        # Get the first monday before start of month
        start = datetime.datetime(year, month, 1)
        start -= datetime.timedelta(days=start.weekday())

        # Get the last sunday after end of month
        ## Get the month-end
        if month == 12:
            end = datetime.datetime(year + 1, 1, 1)
        else:
            end = datetime.datetime(year, month + 1, 1)
        end -= datetime.timedelta(days=1)
        ## Push forward to next sunday
        end += datetime.timedelta(days=6 - end.weekday())

        # Get all events between both days
        with connection(current_app.config["DB_NAME"]) as conn:
            # TODO: Use WHERE in DB
            events = [
                e
                for e in events_repo(conn).list()
                if (e.event_dt >= start and e.event_dt <= end)
                or (
                    e.event_end_dt is not None
                    and e.event_end_dt >= start
                    and e.event_end_dt <= end
                )
            ]

        days = [
            start.date() + datetime.timedelta(days=i) for i in range((end - start).days)
        ]

        return render_template(
            "platform/events.calendar.html.j2",
            year=year,
            month=month,
            days=days,
            events=events,
        )

    @blueprint.route("/events/<int:event_id>/attend/")
    def attend_event(event_id: int):
        with connection(current_app.config["DB_NAME"]) as conn:
            event = events_repo(conn).get(id=event_id)
            if event is None:
                abort(404, f"Event {event_id} not found!")

        user: User = g.current_user
        popups = []
        # TODO: TRIAL EVENTS!

        if user.discord_id is None:
            popups.append("Discord")
        if event.show_participation_ice or len(user.in_case_emergency) == 0:
            popups.append("Contact Details")
        if event.show_participation_ice:
            popups.append("Participation Statement")

        if len(popups) == 0:
            return redirect(url_for("attendee", event_id=event_id, user_id=user.id))

        # TODO: Editable popup text
        return render_template(
            "platform/event.attend.html.j2", event=event, popups=popups, user=user
        )

    @blueprint.route(
        "/events/<int:event_id>/attendees/<int:user_id>",
        methods=["POST", "PUT", "DELETE"],
    )
    def attendee(event_id: int, user_id: int):
        with connection(current_app.config["DB_NAME"]) as conn:
            event = events_repo(conn).get(id=event_id)
            if event is None:
                abort(404, f"Event {event_id} not found!")
            user = users_repo(conn).get(id=user_id)
            if user is None:
                abort(404, f"User {user_id} not found!")

        if request.method == "POST":
            method = request.form["method"]
        else:
            method = request.method

        # TODO: Permissions for user_id
        if method == "POST":
            # Lock here as we need to check the waiting list
            with connection(current_app.config["DB_NAME"], locked=True) as conn:
                attendees_repo = attendees(conn)
                event_attendees = attendees_repo.list_where(event_id=event.id)
                if user_id in [a.user_id for a in event_attendees]:
                    logger.warning(
                        "Attempt to add already existing user %s to event %s, ignoring...",
                        user_id,
                        event,
                    )
                else:
                    attendee = Attendee(
                        user_id=user_id,
                        event_id=event.id,
                        is_waiting_list=event.is_full(event_attendees),
                    )

                    attendees_repo.insert(attendee)
        elif method == "DELETE":
            with connection(current_app.config["DB_NAME"]) as conn:
                attendees_repo = attendees(conn)
                target_attendee = attendees_repo.get(event_id=event.id, user_id=user_id)
                if target_attendee is None:
                    abort(404, "Attendee not found!")
                else:
                    attendees_repo.delete_where(event_id=event.id, user_id=user_id)

        return redirect(url_for("platform.events") + f"#{event.slug}")

    @blueprint.route("/events/add")
    @blueprint.route("/events/<int:id>/edit")
    def edit_event(id: int | None = None):
        if id is not None:
            with connection(current_app.config["DB_NAME"]) as conn:
                event = events_repo(conn).get(id=id)
            if event is None:
                raise MountainException("Event not found!")
        else:
            event = None
        return render_template(
            "platform/event.edit.html.j2", event=event, event_types=EventType
        )


def _events_attendees(
    conn: Connection, events: list[Event]
) -> tuple[dict[int, list[Attendee]], dict[int, User]]:
    # TODO inner join!
    attendees_db = attendees(conn)
    users_db = users_repo(conn)
    event_attendees: dict[int, list[Attendee]] = {}
    event_members: dict[int, User] = {}
    for event in events:
        evt_attendees = attendees_db.list_where(event_id=event.id)
        for att_user in evt_attendees:
            if att_user.user_id not in event_members:
                user = users_db.get(id=att_user.user_id)

                if user is not None:
                    event_members[user.id] = user
                else:
                    logger.warning(
                        "Event %s has unknown user id %s", event, att_user.user_id
                    )
        event_attendees[event.id] = evt_attendees

    return event_attendees, event_members
