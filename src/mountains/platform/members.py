import copy
import logging

from quart import (
    Blueprint,
    current_app,
    render_template,
    request,
)

from mountains.db import connection
from mountains.errors import MountainException

from ..users import User, users

logger = logging.getLogger(__name__)


def member_routes(blueprint: Blueprint):
    @blueprint.route("/members")
    async def members():
        with connection(current_app.config["DB_NAME"]) as conn:
            members = users(conn).list()

        if search := request.args.get("search"):
            # Have the search match either first or last name, in lowercase
            low_search = search.lower()
            members = [
                u
                for u in members
                if low_search in u.first_name.lower()
                or low_search in u.last_name.lower()
            ]

        members = sorted(members, key=_member_sort_key)
        limit = int(request.args.get("limit", 25))

        return await render_template(
            "platform/members.html.j2", members=members, search=search, limit=limit
        )

    @blueprint.route("/members/<id>", methods=["GET", "POST", "PUT"])
    async def member(id: str):
        with connection(current_app.config["DB_NAME"]) as conn:
            user = users(conn).get(id=id)
        if user is None:
            raise MountainException("User not found!")

        if request.method != "GET":
            form = await request.form
            if request.headers.get("HX-Request"):
                method = request.method
            else:
                method = form["method"]

            if method == "PUT":
                # TODO: Remove password, unless it's included
                new_user = copy.replace(
                    user,
                    email=form["email"],
                    first_name=form["first_name"],
                    last_name=form["last_name"],
                    about=form["about"],
                    mobile=form["mobile"],
                )
                logger.info("Updating user %s,  %r -> %r", user, user, new_user)
                # TODO: actually do it
            # TODO: Audit the event

        return await render_template("platform/member.html.j2", user=user)

    @blueprint.route("/members/<id>/edit")
    async def edit_member(id: str):
        with connection(current_app.config["DB_NAME"]) as conn:
            user = users(conn).get(id=id)
        if user is None:
            raise MountainException("User not found!")
        return await render_template("platform/member.edit.html.j2", user=user)


def _member_sort_key(user: User) -> tuple:
    return (
        not user.is_committee,
        not user.is_coordinator,
        not user.is_member,
        user.created_on_utc,
        user.last_name,
    )
