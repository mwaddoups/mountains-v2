import copy
import logging

from quart import (
    Blueprint,
    current_app,
    render_template,
    request,
)

from mountains.errors import MountainException

from ..users import User, users

logger = logging.getLogger(__name__)


def users_repo():
    return users(current_app.config["DB_NAME"])


def member_routes(blueprint: Blueprint):
    @blueprint.route("/members")
    async def members():
        users = sorted(users_repo().list(), key=_member_sort_key)

        if search := request.args.get("search"):
            # Have the search match either first or last name, in lowercase
            low_search = search.lower()
            users = [
                u
                for u in users
                if low_search in u.first_name.lower()
                or low_search in u.last_name.lower()
            ]

        # TODO: Infinite scroll for members, this request is slow
        return await render_template(
            "platform/members.html.j2", members=users, search=search
        )

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


def _member_sort_key(user: User) -> tuple:
    return (
        not user.is_committee,
        not user.is_coordinator,
        not user.is_member,
        user.created_on_utc,
        user.last_name,
    )
