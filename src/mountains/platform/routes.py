import logging

from quart import (
    Blueprint,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from mountains.errors import MountainException

from ..events import Event, events
from .members import member_routes, users_repo

logger = logging.getLogger(__name__)


def events_repo():
    return events(current_app.config["DB_NAME"])


def routes(blueprint: Blueprint):
    @blueprint.before_request
    async def current_user():
        # Ensure all requests have access to the current user

        if (user_id := session.get("user_id")) is None:
            return redirect(url_for("login"))
        else:
            current_user = users_repo().get(id=user_id)
            if current_user is None:
                # Something weird happened
                del session["user_id"]
                return redirect(url_for("index"))
            else:
                g.current_user = current_user

    @blueprint.route("/home")
    async def home():
        return await render_template("platform/home.html.j2")

    # Add the member routes
    member_routes(blueprint)

    @blueprint.route("/events", methods=["GET", "POST"])
    async def events():
        if request.method == "POST":
            form_data = await request.form

            event = Event.from_new_event(
                title=form_data["title"],
                description=form_data["description"],
                event_dt_str=form_data["event_dt"],
                event_end_dt_str=form_data["event_end_dt"],
                event_type_str=form_data["event_type"],
                max_attendees_str=form_data["max_attendees"],
            )
            events_repo().insert(event)

            # TODO: Audit the event
        events = events_repo().list()
        return await render_template("platform/events.html.j2", events=events)

    @blueprint.route("/events/add")
    @blueprint.route("/events/edit/<id>")
    async def edit_event(id: str | None = None):
        if id is not None:
            event = events_repo().get(id=id)
            if event is None:
                raise MountainException("Event not found!")
        else:
            event = None
        return await render_template(
            "platform/event.edit.html.j2", event=event, event_types=Event.event_types()
        )
