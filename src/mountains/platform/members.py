import copy
import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.db import connection
from mountains.discord import DiscordAPI
from mountains.errors import MountainException
from mountains.utils import req_method

from ..events import attendees as attendees_repo
from ..events import events as events_repo
from ..users import User
from ..users import users as users_repo

logger = logging.getLogger(__name__)


def member_routes(blueprint: Blueprint):
    @blueprint.route("/members")
    def members():
        with connection(current_app.config["DB_NAME"]) as conn:
            members = users_repo(conn).list()

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

        return render_template(
            "platform/members.html.j2", members=members, search=search, limit=limit
        )

    @blueprint.route("/members/<slug>", methods=["GET", "POST", "PUT"])
    def member(slug: str):
        with connection(current_app.config["DB_NAME"]) as conn:
            user = users_repo(conn).get(slug=slug)
        if user is None:
            raise MountainException("User not found!")

        if (method := req_method(request)) != "GET":
            if method == "PUT":
                # TODO: Remove password, unless it's included
                new_user = copy.replace(
                    user,
                    email=request.form["email"],
                    first_name=request.form["first_name"],
                    last_name=request.form["last_name"],
                    about=request.form["about"],
                    mobile=request.form["mobile"],
                )
                logger.info("Updating user %s,  %r -> %r", user, user, new_user)
                # TODO: actually do it
            # TODO: Audit the event

        # Get member activity
        with connection(current_app.config["DB_NAME"]) as conn:
            events_db = events_repo(conn)
            attended = [
                events_db.get(id=att.event_id)
                for att in attendees_repo(conn).list_where(user_id=user.id)
            ]

        num_attended = request.args.get("num_attended", type=int, default=20)
        attended = sorted(
            [e for e in attended if e is not None],
            key=lambda e: e.event_dt,
            reverse=True,
        )

        # Get discord name of member
        discord_name = None
        if user.discord_id is not None:
            discord = DiscordAPI.from_app(current_app)
            member = discord.get_member(member_id=user.discord_id)
            if member is not None:
                discord_name = discord.member_username(member)

        return render_template(
            "platform/member.html.j2",
            user=user,
            discord_name=discord_name,
            attended=attended,
            num_attended=num_attended,
        )

    @blueprint.route("/members/<slug>/discord", methods=["GET", "POST"])
    def member_discord(slug: str):
        with connection(current_app.config["DB_NAME"]) as conn:
            user = users_repo(conn).get(slug=slug)
            if user is None:
                abort(404)

        if request.method == "POST":
            if not g.current_user.is_authorised(user.id):
                abort(403)

            if "remove_id" in request.form:
                discord_id = None
            else:
                discord_id = request.form["discord_id"]

            with connection(current_app.config["DB_NAME"]) as conn:
                users_repo(conn).update(id=user.id, discord_id=discord_id)

            return redirect(url_for("platform.member", slug=slug))

        with connection(current_app.config["DB_NAME"]) as conn:
            taken_ids = set(
                u.discord_id
                for u in users_repo(conn).list()
                if u.discord_id is not None
            )

        discord = DiscordAPI.from_app(current_app)
        discord_members = sorted(
            [
                {"id": m["user"]["id"], "name": discord.member_username(m)}
                for m in discord.fetch_all_members()
                if m["user"]["id"] not in taken_ids
            ],
            key=lambda m: m["name"].lower(),
        )

        return render_template(
            "platform/member.discord.html.j2",
            user=user,
            discord_members=discord_members,
        )

    @blueprint.route("/members/<id>/edit")
    def edit_member(id: str):
        with connection(current_app.config["DB_NAME"]) as conn:
            user = users_repo(conn).get(id=id)
        if user is None:
            raise MountainException("User not found!")
        return render_template("platform/member.edit.html.j2", user=user)


def _member_sort_key(user: User) -> tuple:
    return (
        not user.is_committee,
        not user.is_coordinator,
        not user.is_member,
        user.created_on_utc,
        user.last_name,
    )
