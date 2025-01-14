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
from mountains.utils import now_utc, req_method

from ..events import Attendee, Event, EventType, attendees
from ..events import events as events_repo
from ..users import User
from ..users import users as users_repo

logger = logging.getLogger(__name__)


def event_routes(blueprint: Blueprint):
    @blueprint.route("/events")
    def events(id: int | None = None):
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
                for e in events_repo(conn).list_where(is_deleted=False)
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

    @blueprint.route("/events/<id>", methods=["POST", "DELETE"])
    def event(id: int):
        if not g.current_user.is_authorised():
            abort(403)

        with connection(current_app.config["DB_NAME"]) as conn:
            event = events_repo(conn).get(id=id)
            if event is None:
                abort(404, f"Event {id} not found!")

            if req_method(request) == "DELETE":
                logger.info("Soft deleting event %s", event)
                events_repo(conn).update(id=id, is_deleted=True)
                return redirect(url_for("platform.events"))
            else:
                return redirect(url_for("platform.events") + "#" + event.slug)

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

    @blueprint.route("/events/add", methods=["GET", "POST"])
    @blueprint.route("/events/<int:id>/edit", methods=["GET", "POST", "PUT"])
    def edit_event(id: int | None = None):
        method = req_method(request)

        if id is not None:
            with connection(current_app.config["DB_NAME"]) as conn:
                event = events_repo(conn).get(id=id)
            if event is None:
                abort(404)
        else:
            event = None

        error: str | None = None
        if method != "GET":
            if not g.current_user.is_authorised():
                abort(403)

            try:
                with connection(current_app.config["DB_NAME"], locked=True) as conn:
                    events_db = events_repo(conn)
                    if method == "POST" and event is None:
                        event = Event.from_form(
                            id=events_db.next_id(), form=request.form
                        )
                        events_db.insert(event)
                    elif method == "PUT" and event is not None:
                        assert event is not None
                        event = Event.from_form(
                            id=event.id,
                            form=request.form,
                            created_on_utc=event.created_on_utc,
                            is_deleted=event.is_deleted,
                        )
                        events_db.delete_where(id=event.id)
                        events_db.insert(event)
                    else:
                        abort(405)

                # TODO: Audit the event
                return redirect(_single_event_url(event))
            except MountainException as e:
                error = str(e)

            return render_template(
                "platform/event.edit.html.j2",
                editing=event,
                form=request.form,
                event_types=EventType,
                error=error,
            )
        else:
            # For default, use a copy if passed as ?copy_from and the ID is found...
            event_form = None
            if event is None and (copy_id := request.args.get("copy_from", type=int)):
                with connection(current_app.config["DB_NAME"]) as conn:
                    copy_event = events_repo(conn).get(id=copy_id)

                if copy_event is not None:
                    event_form = copy_event.to_form()
                else:
                    error = (
                        "Event not found for attempted copy, using default values..."
                    )
                    logger.error("Attempt to copy with a missing event ID %s", copy_id)

            # Or use the old event if editing...
            if event is not None and event_form is None:
                event_form = event.to_form()

            return render_template(
                "platform/event.edit.html.j2",
                editing=event,
                form=event_form,
                event_types=EventType,
                error=error,
            )

    @blueprint.route("/events/<int:event_id>/attend/", methods=["POST"])
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
            _add_user_to_event(event, user.id, db_name=current_app.config["DB_NAME"])
            return redirect(_single_event_url(event))

        # TODO: Editable popup text
        return render_template(
            "platform/event.attend.html.j2", event=event, popups=popups, user=user
        )

    @blueprint.route(
        "/events/<int:event_id>/attendees/<int:user_id>",
        methods=["POST", "PUT", "DELETE"],
    )
    def attendee(event_id: int, user_id: int):
        if not g.current_user.is_authorised(user_id):
            abort(403)

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

        if method == "POST":
            _add_user_to_event(event, user_id, db_name=current_app.config["DB_NAME"])
        elif method == "DELETE":
            with connection(current_app.config["DB_NAME"]) as conn:
                attendees_repo = attendees(conn)
                target_attendee = attendees_repo.get(event_id=event.id, user_id=user_id)
                if target_attendee is None:
                    abort(404, "Attendee not found!")
                else:
                    attendees_repo.delete_where(event_id=event.id, user_id=user_id)
                # TODO: Audit!

        return redirect(_single_event_url(event))


def _single_event_url(event: Event) -> str:
    return url_for("platform.events", _anchor=event.slug)


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


def _add_user_to_event(event: Event, user_id: int, *, db_name: str):
    # Lock here as we need to check the waiting list
    with connection(db_name, locked=True) as conn:
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

        # TODO: AUDIT!
