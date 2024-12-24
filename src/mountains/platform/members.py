import copy
import logging

from quart import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.errors import MountainException

from ..users import User, users

logger = logging.getLogger(__name__)


def users_repo():
    return users(current_app.config["DB_NAME"])


def member_routes(blueprint: Blueprint):
    @blueprint.route("/members", methods=["GET", "POST"])
    async def members():
        if request.method == "POST":
            # New user registration
            form = await request.form
            if form["password"] != form["confirm_password"]:
                return await render_template(
                    "register.html.j2", error="Passwords do not match!"
                )
            user = User.from_registration(
                email=form["email"],
                password=form["password"],
                first_name=form["first_name"],
                last_name=form["last_name"],
                about=form["about"],
                mobile=form["mobile"],
            )

            users_repo().insert(user)
            return redirect(url_for("login"))
        else:
            users = users_repo().list()

            if search := request.args.get("search"):
                # Have the search match either first or last name, in lowercase
                low_search = search.lower()
                users = [
                    u
                    for u in users
                    if low_search in u.first_name.lower()
                    or low_search in u.last_name.lower()
                ]

            #
            users = sorted(users, key=_member_sort_key)

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
            elif method == "POST":
                form = await request.form
                if form["password"] != form["confirm_password"]:
                    return await render_template(
                        "register.html.j2", error="Passwords do not match!"
                    )
                user = User.from_registration(
                    email=form["email"],
                    password=form["password"],
                    first_name=form["first_name"],
                    last_name=form["last_name"],
                    about=form["about"],
                    mobile=form["mobile"],
                )

                users_repo().insert(user)

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
