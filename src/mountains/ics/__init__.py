from datetime import date, timedelta
from typing import List
from zoneinfo import ZoneInfo

from attr import dataclass
from dateutil.relativedelta import relativedelta
from flask import Blueprint, Response, request, abort, url_for
from icalendar import Calendar, Event as ICalEvent

from mountains.context import db_conn
from mountains.models.events import attendees_repo, events_repo, Event
from mountains.models.tokens import tokens_ics_repo
from mountains.models.users import users_repo
from mountains.utils import now_utc

blueprint = Blueprint("ics", __name__)

@blueprint.route("/calendar.ics")
def calendar():
    _check_token_or_401()
    date_cut_off = (date.today() - relativedelta(months=1)).strftime("%Y-%m-%d")
    with db_conn() as conn:
        events = [
            _EventWithIsWaitingList(event=event, is_waiting_list=False)
            for event in events_repo(conn).list_where(is_deleted=False, is_draft=False, event_dt=(">", date_cut_off))
        ]
    return _return_ics("All CMC Events", events, "All upcoming club events")


@blueprint.route("/user-calendar.ics")
def user_calendar():
    user_id = _check_token_or_401()
    with db_conn() as conn:
        user_events = [
            _EventWithIsWaitingList(event=event, is_waiting_list=att.is_waiting_list)
            for att in attendees_repo(conn).list_where(user_id=user_id)
            if (event := events_repo(conn).get(id=att.event_id)) is not None
        ]
    return _return_ics("My CMC Events", user_events, "Upcoming club events you are attending or wait-listed for")


def _check_token_or_401() -> int:
    token_str = request.args.get("token")
    if not token_str:
        abort(401)
    with db_conn() as conn:
        token = tokens_ics_repo(conn).get(id=token_str)
        if token is None:
            abort(401)
        user = users_repo(conn).get(id=token.user_id)
        if user is None:
            abort(401)
    return user.id


@dataclass
class _EventWithIsWaitingList:
    event: Event
    is_waiting_list: bool


def _return_ics(name: str, events: List[_EventWithIsWaitingList], description: str | None = None) -> Response:
    london = ZoneInfo("Europe/London")
    cal = Calendar()
    cal.add("prodid", f"-//clydemc.org//{name}")
    cal.add("version", "2.0")
    cal.add("X-WR-TIMEZONE", "Europe/London")
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
        start_london = event.event_dt.astimezone(london)
        ical_event.add("dtstart", start_london)
        if event.event_end_dt is not None:
            end_london = event.event_end_dt.astimezone(london)
            ical_event.add("dtend", end_london)
        else:
            ical_event.add("duration", timedelta(hours=2))
        ical_event.add("url", url_for("platform.events.event", id=event.id, _external=True))
        ical_event.add("dtstamp", event.created_on_utc)
        ical_event.add("last-modified", event.updated_on_utc)
        cal.add_component(ical_event)
    cal.add_missing_timezones()
    return Response(
        cal.to_ical(),
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": "inline"}
    )
