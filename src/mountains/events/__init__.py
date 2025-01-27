from __future__ import annotations

import datetime
import logging
from sqlite3 import Connection

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.context import current_user, db_conn
from mountains.errors import MountainException
from mountains.models.activity import Activity, activity_repo
from mountains.models.events import (
    Attendee,
    Event,
    EventType,
    attendees_repo,
    events_repo,
)
from mountains.models.pages import latest_content, latest_page, pages_repo
from mountains.models.users import User, users_repo
from mountains.payments import EventPaymentMetadata, StripeAPI
from mountains.utils import now_utc, req_method, str_to_bool

logger = logging.getLogger(__name__)

blueprint = Blueprint("events", __name__, template_folder="templates")


@blueprint.route("/upcoming")
@blueprint.route("/")
@blueprint.route("/<int:event_id>")
def events(event_id: int | None = None):
    search = request.args.get("search")
    limit = request.args.get("limit", type=int, default=5)

    if "filters_enabled" in request.args and "event_type" in request.args:
        event_types = request.args.getlist(
            "event_type", type=lambda x: EventType(int(x))
        )
    else:
        event_types = [t for t in EventType]

    with db_conn() as conn:
        if event_id is not None:
            event = events_repo(conn).get_or_404(id=event_id)
        else:
            event = None

        # TODO: Eventually page this (e.g. at least <x> more )
        events = _get_sorted_filtered_events(
            conn,
            event_types=event_types,
            search=search,
        )

        event_attendees, event_members = _events_attendees(conn, events)

    if event is not None:
        # Single event display
        if request.headers.get("HX-Target") == event.slug:
            return render_template(
                "events/_event.html.j2",
                event=event,
                events=events,
                attendees=event_attendees[event.id],
                members=event_members,
            )
        else:
            return render_template(
                "events/event.html.j2",
                event=event,
                events=events,
                attendees=event_attendees[event.id],
                members=event_members,
            )
    else:
        if request.headers.get("HX-Target") == "show-more-events":
            # Infinite scroll
            after_id = int(request.args["after"])
            after_ix = [e.id for e in events].index(after_id)
            return render_template(
                "events/_event.list.html.j2",
                events=events,
                event_type_set=EventType,
                event_attendees=event_attendees,
                members=event_members,
                search=search,
                offset=after_ix + 1,
                limit=limit,
                event_types=event_types,
            )
        else:
            return render_template(
                "events/events.html.j2",
                events=events,
                event_type_set=EventType,
                event_attendees=event_attendees,
                members=event_members,
                search=search,
                limit=limit,
                event_types=event_types,
            )


@blueprint.route("/<id>", methods=["POST"])
def event(id: int):
    if request.form["method"] == "DELETE":
        current_user.check_authorised()

        with db_conn() as conn:
            events_db = events_repo(conn)
            event = events_db.get_or_404(id=id)
            logger.info("Soft deleting event %s", event)
            events_repo(conn).update(id=id, is_deleted=True)
            activity_repo(conn).insert(
                Activity(
                    user_id=current_user.id,
                    event_id=event.id,
                    action="deleted event",
                )
            )

    # TODO: Message / noti
    return redirect(url_for(".events"))


@blueprint.route("/calendar")
@blueprint.route("/calendar/<int:year>/<int:month>")
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
    with db_conn() as conn:
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
        "events/calendar.html.j2",
        month_dt=month_dt,
        prev_month_dt=prev_month_dt,
        next_month_dt=next_month_dt,
        days=days,
        today=now,
        events=events,
    )


@blueprint.route("/add", methods=["GET", "POST"])
@blueprint.route("/<int:id>/edit", methods=["GET", "POST", "PUT"])
def edit_event(id: int | None = None):
    current_user.check_authorised()
    method = req_method(request)

    if id is not None:
        with db_conn() as conn:
            event = events_repo(conn).get(id=id)
        if event is None:
            abort(404)
    else:
        event = None

    error: str | None = None
    if method != "GET":
        try:
            with db_conn(locked=True) as conn:
                events_db = events_repo(conn)
                if method == "POST" and event is None:
                    event = Event.from_form(id=events_db.next_id(), form=request.form)
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
                    Activity(user_id=current_user.id, event_id=event.id, action=action)
                )

            return redirect(url_for(".event", id=event.id))
        except MountainException as e:
            error = str(e)

        return render_template(
            "events/event.edit.html.j2",
            editing=event,
            form=request.form,
            event_types=EventType,
            error=error,
        )
    else:
        event_form = {}

        # For default, use a copy if passed as ?copy_from and the ID is found...
        if event is None and (copy_id := request.args.get("copy_from", type=int)):
            with db_conn() as conn:
                copy_event = events_repo(conn).get(id=copy_id)

            if copy_event is not None:
                event_form = copy_event.to_form()
            else:
                error = "Event not found for attempted copy, using default values..."
                logger.error("Attempt to copy with a missing event ID %s", copy_id)

        # Or use the old event if editing...
        if event is not None and not event_form:
            event_form = event.to_form()

        # If still nothing, and we were passed a template, use that
        if (
            event is None
            and not event_form
            and (template := request.args.get("template", type=int))
        ):
            template_names = {
                EventType.SUMMER_DAY_WALK: "template-summer-day-walk",
                EventType.SUMMER_WEEKEND: "template-summer-weekend",
                EventType.WINTER_DAY_WALK: "template-winter-day-walk",
                EventType.WINTER_WEEKEND: "template-winter-weekend",
                EventType.INDOOR_CLIMBING: "template-indoor-climbing",
                EventType.OUTDOOR_CLIMBING: "template-outdoor-climbing",
                EventType.RUNNING: "template-running",
                EventType.SOCIAL: "template-social",
            }
            event_type = EventType(template)
            event_form["event_type"] = str(event_type.value)
            if event_type in template_names:
                with db_conn() as conn:
                    event_form["description"] = latest_page(
                        template_names[event_type], pages_repo(conn)
                    ).markdown

            if event_type not in (
                EventType.INDOOR_CLIMBING,
                EventType.SOCIAL,
            ):
                event_form["show_participation_ice"] = "true"

            if event_type in (
                EventType.SUMMER_WEEKEND,
                EventType.WINTER_WEEKEND,
                EventType.OUTDOOR_CLIMBING,
            ):
                event_form["is_members_only"] = "true"

        return render_template(
            "events/event.edit.html.j2",
            editing=event,
            form=event_form,
            event_types=EventType,
            error=error,
        )


@blueprint.route("/<int:event_id>/addattendee")
def event_attendee_add(event_id: int):
    with db_conn() as conn:
        if not current_user.is_authorised():
            abort(403)
        event = events_repo(conn).get_or_404(id=event_id)
        current_attending = set(
            a.user_id for a in attendees_repo(conn).list_where(event_id=event.id)
        )
        users = users_repo(conn).list()

    search = request.args.get("search", None)
    if search:
        users = [
            u
            for u in users
            if search.lower() in u.full_name.lower() and u.id not in current_attending
        ]
    else:
        users = []

    if request.headers.get("HX-Request"):
        return render_template(
            "events/admin._addattend.html.j2",
            event=event,
            users=users,
        )
    else:
        return render_template(
            "events/admin.addattend.html.j2",
            event=event,
            users=users,
        )


@blueprint.route("/<int:event_id>/pay", methods=["GET", "POST"])
def pay_event(event_id: int):
    with db_conn() as conn:
        attendee = attendees_repo(conn).get_or_404(
            user_id=current_user.id, event_id=event_id
        )
        event = events_repo(conn).get_or_404(id=event_id)

    if event.price_id is None:
        # TODO: Flash message
        return redirect(url_for(".event", id=event.id))
    elif attendee.is_trip_paid or attendee.is_waiting_list:
        # TODO: Flash message
        return redirect(url_for(".event", id=event.id))

    if request.method == "POST":
        stripe_api = StripeAPI.from_app(current_app)
        metadata = EventPaymentMetadata(user_id=current_user.id, event_id=event_id)
        checkout_url = stripe_api.create_checkout(
            event.price_id,
            success_url=url_for(
                ".event", id=event.id, pay_success=True, _external=True
            ),
            cancel_url=url_for(".event", id=event.id, pay_cancel=True, _external=True),
            metadata=metadata,
        )

        return redirect(checkout_url)
    else:
        notify_signup = "notify_signup" in request.args
        if request.headers.get("HX-Target") == event.slug:
            return render_template(
                "events/_pay.html.j2", event=event, notify_signup=notify_signup
            )
        else:
            return render_template(
                "events/pay.html.j2", event=event, notify_signup=notify_signup
            )


@blueprint.route("/<int:event_id>/attend/")
def attend_event(event_id: int):
    pages = {
        "discord": "discord-popup",
        "members_only": "members-only-popup",
        "ice": "ice-popup",
        "statement": "participation-statement",
        "trial": "trial-popup",
    }

    with db_conn() as conn:
        event = events_repo(conn).get_or_404(id=event_id)
        popup_names = event.popups_for(current_user)

        if request.args.get("trial") != "skip" and not current_user.is_member:
            attending = attendees_repo(conn).list_where(
                user_id=current_user.id, is_waiting_list=False
            )
            events = [
                e
                for e in events_repo(conn).get_all(
                    id=set(a.event_id for a in attending)
                )
            ]
            past_events = [
                e for e in events if not e.is_upcoming() and e.is_part_of_trial()
            ]
            if len(past_events) > current_app.config["CMC_MAX_TRIAL_EVENTS"]:
                popup_names = ["trial"]
        else:
            past_events = None

        popups = {name: latest_content(conn, pages[name]) for name in popup_names}

    if request.headers.get("HX-Target") == event.slug:
        return render_template(
            "events/_attend.html.j2",
            event=event,
            popups=popups,
            user=current_user,
            past_events=past_events,
        )
    else:
        return render_template(
            "events/attend.html.j2",
            event=event,
            popups=popups,
            user=current_user,
            past_events=past_events,
        )


@blueprint.route(
    "/<int:event_id>/attendees/<int:user_id>",
    methods=["POST", "PUT", "DELETE"],
)
def attendee(event_id: int, user_id: int):
    current_user.check_authorised(user_id)

    with db_conn() as conn:
        event = events_repo(conn).get_or_404(id=event_id)
        user = users_repo(conn).get_or_404(id=user_id)

    method = req_method(request)

    if method == "POST":
        if event.is_open() or current_user.is_site_admin:
            attendee = _add_user_to_event(event, user.id)
            if attendee is None:
                # TODO: Message
                return redirect(url_for(".events", event_id=event.id))

            if user.id == current_user.id and event.needs_payment_from(attendee):
                # They need to pay - redirect straightaway
                return redirect(
                    url_for(".pay_event", event_id=event.id, notify_signup=True)
                )
            else:
                return redirect(url_for(".events", event_id=event.id))
        else:
            logger.error("User %s tried to add %s to closed event!", current_user, user)
            # TODO: Message
            return redirect(url_for(".events", event_id=event.id))
    elif method == "PUT":
        with db_conn() as conn:
            attendees_db = attendees_repo(conn)
            attendees_db.get_or_404(event_id=event.id, user_id=user_id)
            if "is_waiting_list" in request.form:
                is_waiting_list = str_to_bool(request.form["is_waiting_list"])
                attendees_db.update(
                    _where=dict(event_id=event.id, user_id=user_id),
                    is_waiting_list=is_waiting_list,
                )

                if is_waiting_list:
                    action = (
                        f"was moved by {current_user.full_name} to waiting list for"
                    )
                else:
                    action = f"was moved by {current_user.full_name} to attending for"
                activity_repo(conn).insert(
                    Activity(
                        user_id=user_id,
                        event_id=event_id,
                        action=action,
                    )
                )
            elif "is_trip_paid" in request.form:
                attendees_db.update(
                    _where=dict(event_id=event.id, user_id=user_id),
                    is_trip_paid=str_to_bool(request.form["is_trip_paid"]),
                )
                attendee = attendees_db.get_or_404(event_id=event.id, user_id=user.id)

                if request.headers.get("HX-Request"):
                    return render_template(
                        "events/event._attendee.html.j2",
                        attendee=attendee,
                        user=user,
                    )
        return redirect(url_for(".events", event_id=event.id))
    elif method == "DELETE":
        with db_conn() as conn:
            attendees_db = attendees_repo(conn)
            attendees_db.get_or_404(event_id=event.id, user_id=user_id)
            attendees_db.delete_where(event_id=event.id, user_id=user_id)
            if current_user.id != user_id:
                action = f"removed {user.full_name} from"
            else:
                action = "left"
            activity_repo(conn).insert(
                Activity(
                    user_id=current_user.id,
                    event_id=event_id,
                    action=action,
                )
            )

        return redirect(url_for(".events", event_id=event.id))
    else:
        abort(405)


def _get_sorted_filtered_events(
    conn,
    event_types: list[EventType],
    search: str | None,
) -> list[Event]:
    events = [
        e
        for e in events_repo(conn).list_where(is_deleted=False)
        if e.event_type in event_types
    ]

    if search:
        events = [e for e in events if search.lower() in e.title.lower()]

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

    return events


def _events_attendees(
    conn: Connection, events: list[Event]
) -> tuple[dict[int, list[Attendee]], dict[int, User]]:
    attendees_db = attendees_repo(conn)
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


def _add_user_to_event(event: Event, user_id: int) -> None | Attendee:
    # Lock here as we need to check the waiting list
    with db_conn(locked=True) as conn:
        attendees_db = attendees_repo(conn)
        event_attendees = attendees_db.list_where(event_id=event.id)
        if user_id in [a.user_id for a in event_attendees]:
            logger.warning(
                "Attempt to add already existing user %s to event %s, ignoring...",
                user_id,
                event.slug,
            )
            return None
        else:
            attendee = Attendee(
                user_id=user_id,
                event_id=event.id,
                is_waiting_list=event.is_full(event_attendees),
            )

            attendees_db.insert(attendee)

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
