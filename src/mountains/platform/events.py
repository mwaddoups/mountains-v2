from __future__ import annotations

import datetime
import logging
from sqlite3 import Connection

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.activity import Activity, activity_repo
from mountains.db import connection
from mountains.errors import MountainException
from mountains.pages import latest_page, pages_repo
from mountains.utils import now_utc, req_method, str_to_bool

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

    @blueprint.route("/events/<id>", methods=["GET", "POST", "DELETE"])
    def event(id: int):
        with connection(current_app.config["DB_NAME"]) as conn:
            event = events_repo(conn).get(id=id)
            if event is None:
                abort(404, f"Event {id} not found!")

        if request.method != "GET":
            if not g.current_user.is_authorised():
                abort(403)

            with connection(current_app.config["DB_NAME"]) as conn:
                if req_method(request) == "DELETE":
                    logger.info("Soft deleting event %s", event)
                    events_repo(conn).update(id=id, is_deleted=True)
                    activity_repo(conn).insert(
                        Activity(
                            user_id=g.current_user.id,
                            event_id=event.id,
                            action="deleted event",
                        )
                    )
                    return redirect(url_for("platform.events"))

        expanded = request.args.get("expanded", type=str_to_bool, default=False)
        event_attendees, event_members = _events_attendees(conn, [event])

        if request.headers.get("HX-Target") == "selectedEvent":
            # This request also needs the is_dialog part, since its acting
            # more like a link to events/<id>
            return render_template(
                "platform/_event.html.j2",
                is_dialog=True,
                event=event,
                attendees=event_attendees,
                members=event_members,
                expanded=expanded,
            )
        elif request.headers.get("HX-Target") == event.slug:
            # This can skip is_dialog, and should not update the URL as its acting like
            # a refresh
            response = make_response(
                render_template(
                    "platform/_event.html.j2",
                    is_dialog=False,
                    event=event,
                    attendees=event_attendees,
                    members=event_members,
                    expanded=expanded,
                )
            )
            response.headers["HX-Replace-Url"] = "false"
            return response
        else:
            return render_template(
                "platform/event.html.j2",
                event=event,
                attendees=event_attendees,
                members=event_members,
                expanded=expanded,
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
                for e in events_repo(conn).list_where(is_deleted=False)
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

        # These just need to be accurate down to year-month
        month_dt = datetime.datetime(year, month, 1)
        prev_month_dt = month_dt - datetime.timedelta(days=1)
        next_month_dt = month_dt + datetime.timedelta(days=40)

        return render_template(
            "platform/events.calendar.html.j2",
            month_dt=month_dt,
            prev_month_dt=prev_month_dt,
            next_month_dt=next_month_dt,
            days=days,
            today=now,
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
                        action = "created event"
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
                        action = "edited event"
                    else:
                        abort(405)
                    activity_repo(conn).insert(
                        Activity(
                            user_id=g.current_user.id, event_id=event.id, action=action
                        )
                    )

                return redirect(url_for(".event", id=event.id))
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

    @blueprint.route("/events/<int:event_id>/addattendee", methods=["GET", "POST"])
    def event_attendee_add(event_id: int):
        with connection(current_app.config["DB_NAME"]) as conn:
            event = events_repo(conn).get(id=event_id)
            if event is None:
                abort(404, f"Event {event_id} not found!")

        if request.method == "POST":
            with connection(current_app.config["DB_NAME"]) as conn:
                user = users_repo(conn).get(id=request.form.get("user_id", type=int))

            if user is None:
                raise MountainException(
                    "Could not find the user that you wanted to add!"
                )
            else:
                if not g.current_user.is_authorised(user.id):
                    abort(403)

                if event.is_open() or g.current_user.is_site_admin:
                    _add_user_to_event(
                        event,
                        user.id,
                        db_name=current_app.config["DB_NAME"],
                        current_user=g.current_user,
                    )
                else:
                    logger.error(
                        "User %s tried to add self to closed event!", g.current_user
                    )
                return redirect(url_for(".event", id=event.id, expanded=True))
        else:
            with connection(current_app.config["DB_NAME"]) as conn:
                users = users_repo(conn).list()

            search = request.args.get("search", None)
            if search:
                users = [u for u in users if search.lower() in u.full_name.lower()]
            else:
                users = []

            return render_template(
                "platform/event.admin.addattend.html.j2",
                event=event,
                users=users,
            )

    @blueprint.route("/events/<int:event_id>/attend/", methods=["POST"])
    def attend_event(event_id: int):
        with connection(current_app.config["DB_NAME"]) as conn:
            event = events_repo(conn).get(id=event_id)
            if event is None:
                abort(404, f"Event {event_id} not found!")

        user: User = g.current_user
        popups = {}
        # TODO: TRIAL EVENTS!

        with connection(current_app.config["DB_NAME"]) as conn:
            if user.discord_id is None:
                popups["discord"] = latest_page(
                    name="discord-popup", repo=pages_repo(conn)
                ).markdown
            if event.show_participation_ice or len(user.in_case_emergency) == 0:
                popups["ice"] = latest_page(
                    name="ice-popup", repo=pages_repo(conn)
                ).markdown
            if event.show_participation_ice:
                popups["statement"] = latest_page(
                    name="participation-statement", repo=pages_repo(conn)
                ).markdown

        if len(popups) == 0:
            _add_user_to_event(
                event,
                user.id,
                db_name=current_app.config["DB_NAME"],
                current_user=g.current_user,
            )
            return redirect(url_for(".event", id=event.id))

        if request.headers.get("HX-Request"):
            response = make_response(
                render_template(
                    "platform/event._attend.html.j2",
                    event=event,
                    popups=popups,
                    user=user,
                )
            )
            response.headers["HX-Retarget"] = "#selectedEvent"
            response.headers["HX-Reswap"] = "innerHTML"
            return response
        else:
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

        method = req_method(request)

        if method == "POST":
            if event.is_open() or g.current_user.is_site_admin:
                _add_user_to_event(
                    event,
                    user.id,
                    db_name=current_app.config["DB_NAME"],
                    current_user=g.current_user,
                )
            else:
                logger.error(
                    "User %s tried to add self to closed event!", g.current_user
                )

        elif method in ("PUT", "DELETE"):
            with connection(current_app.config["DB_NAME"]) as conn:
                attendees_repo = attendees(conn)
                target_attendee = attendees_repo.get(event_id=event.id, user_id=user_id)
                if target_attendee is None:
                    abort(404, "Attendee not found!")
                else:
                    if method == "PUT":
                        updates = {}
                        for allowed in ("is_waiting_list", "is_trip_paid"):
                            if (
                                value := request.form.get(allowed, type=str_to_bool)
                            ) is not None:
                                updates[allowed] = value

                        attendees_repo.update(
                            _where=dict(event_id=event.id, user_id=user_id),
                            **updates,
                        )
                        if "is_waiting_list" in updates:
                            if updates["is_waiting_list"]:
                                action = f"was moved by {g.current_user.full_name} to waiting list for"
                            else:
                                action = f"was moved by {g.current_user.full_name} to attending for"
                            activity_repo(conn).insert(
                                Activity(
                                    user_id=user_id,
                                    event_id=event_id,
                                    action=action,
                                )
                            )
                    elif method == "DELETE":
                        attendees_repo.delete_where(event_id=event.id, user_id=user_id)
                        if g.current_user.id != user_id:
                            action = f"removed {user.full_name} from"
                        else:
                            action = "left"
                        activity_repo(conn).insert(
                            Activity(
                                user_id=g.current_user.id,
                                event_id=event_id,
                                action=action,
                            )
                        )
                # TODO: Audit!

        return redirect(url_for(".event", id=event.id, expanded=True))


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


def _add_user_to_event(
    event: Event, user_id: int, *, db_name: str, current_user: User
) -> None | Attendee:
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
            return None
        else:
            attendee = Attendee(
                user_id=user_id,
                event_id=event.id,
                is_waiting_list=event.is_full(event_attendees),
            )

            attendees_repo.insert(attendee)

            # Now log the event
            if current_user.id == user_id:
                if attendee.is_waiting_list:
                    action = "joined waiting list for"
                else:
                    action = "joined"
            else:
                if attendee.is_waiting_list:
                    action = (
                        f"was added by {current_user.full_name} to waiting list for"
                    )
                else:
                    action = f"was added by {current_user.full_name} to attending for"
            activity_repo(conn).insert(
                Activity(user_id=user_id, event_id=event.id, action=action)
            )
            return attendee
