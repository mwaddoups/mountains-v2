from typing import List

from attr import dataclass
from flask import Blueprint, Response, request, abort, url_for
from icalendar import Calendar, Event as ICalEvent

from mountains.context import db_conn
from mountains.models.events import attendees_repo, events_repo, Event, Attendee
from mountains.models.tokens import tokens_ics_repo
from mountains.utils import now_utc

blueprint = Blueprint("ics", __name__, url_prefix="/ics")

@blueprint.route("/calendar.ics")
def calendar():
    _ = _user_id_or_401()
    events = _events()
    return _return_ics("All CMC Events", events, "All upcoming club events")

@blueprint.route("/user-calendar.ics")
def user_calendar():
    user_id = _user_id_or_401()
    user_events = _user_events(user_id)
    return _return_ics("My CMC Events", user_events, "Upcoming club events you are attending or wait-listed for")


def _user_id_or_401() -> int:
    token_str = request.args.get("token")
    if not token_str:
        abort(401)
    with db_conn() as conn:
        token = tokens_ics_repo(conn).get(id=token_str)
    if token is None:
        abort(401)
    return token.user_id


@dataclass
class _EventWithIsWaitingList:
    event: Event
    is_waiting_list: bool


def _user_events(user_id: int) -> List[_EventWithIsWaitingList]:
    with db_conn() as conn:
        attended = [
            _EventWithIsWaitingList(event=event, is_waiting_list=att.is_waiting_list)
            for att in attendees_repo(conn).list_where(user_id=user_id)
            if (event := events_repo(conn).get(id=att.event_id)) is not None
        ]
    return attended


def _events() -> List[_EventWithIsWaitingList]:
    with db_conn() as conn:
        events = [
            _EventWithIsWaitingList(event=event, is_waiting_list=False)
            for event in events_repo(conn).list_where(is_deleted=False, is_draft=False)
        ]
    return events


def _return_ics(name: str, events: List[_EventWithIsWaitingList], description: str | None = None) -> Response:
    now = now_utc()
    cal = Calendar()
    cal.add("prodid", f"-//clydemc.org//{name}")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", name)
    if description:
        cal.add("X-WR-CALDESC", description)

    for e in events:
        event = e.event
        ical_event = ICalEvent()
        ical_event.add("uid", f"org.clydemc.event.{event.id}")
        if e.is_waiting_list:
            ical_event.add("summary", f"WAIT LIST - {event.title}")
        else:
            ical_event.add("summary", event.title)
        ical_event.add("dtstart", event.event_dt)
        if event.event_end_dt is not None:
            ical_event.add("dtend", event.event_end_dt)
        ical_event.add("description", url_for("platform.events.event", id=event.id, _external=True))
        ical_event.add("dtstamp", now)
        cal.add_component(ical_event)

    return Response(
        cal.to_ical(),
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": "inline"}
    )
