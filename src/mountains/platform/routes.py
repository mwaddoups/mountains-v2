import copy
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

from ..repos import users

logger = logging.getLogger(__name__)


def users_repo():
    return users(current_app.config["DB_NAME"])


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

        if request.method in ("POST", "PUT"):
            # We keep POST support for legacy forms
            form_data = await request.form
            new_user = copy.replace(user, **form_data)
            logger.info("Updating user %s,  %r -> %r", user, user, new_user)
            # TODO: actually do it
        return await render_template("platform/member.html.j2", user=user)

    @blueprint.route("/members/<id>/edit")
    async def edit_member(id: str):
        user = users_repo().get(id=id)
        if user is None:
            raise MountainException("User not found!")
        return await render_template("platform/edit.member.html.j2", user=user)
