import copy
import datetime
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
from ..users import users

logger = logging.getLogger(__name__)


def users_repo():
    return users(current_app.config["DB_NAME"])


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
                return redirect(url_for("logout"))
            else:
                g.current_user = current_user

    @blueprint.route("/home")
    async def home():
        return await render_template("platform/home.html.j2")

    @blueprint.route("/members")
    async def members():
        users = users_repo().list()
        return await render_template("platform/members.html.j2", members=users)

    @blueprint.route("/members/<id>", methods=["GET", "POST", "PUT"])
    async def member(id: str):
        user = users_repo().get(id=id)
        if user is None:
            raise MountainException("User not found!")

        if request.method != "GET":
            form_data = await request.form
            if request.headers["HX-Request"]:
                method = request.method
            else:
                method = form_data["method"]

            if method == "PUT":
                new_user = copy.replace(user, **form_data)
                logger.info("Updating user %s,  %r -> %r", user, user, new_user)
                # TODO: actually do it

            # TODO: Audit the event

        return await render_template("platform/member.html.j2", user=user)

    @blueprint.route("/members/<id>/edit")
    async def edit_member(id: str):
        user = users_repo().get(id=id)
        if user is None:
            raise MountainException("User not found!")
        return await render_template("platform/member.edit.html.j2", user=user)

    @blueprint.route("/events", methods=["GET", "POST"])
    async def events():
        if request.method == "POST":
            form_data = await request.form

            event = Event.from_new_event(
                title=form_data["title"],
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
