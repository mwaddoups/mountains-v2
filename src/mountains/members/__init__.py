import datetime
import logging
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from requests.exceptions import ConnectionError
from werkzeug.security import generate_password_hash

from mountains.context import current_user, db_conn
from mountains.discord import DiscordAPI
from mountains.models.events import attendees_repo, events_repo
from mountains.models.users import CommitteeRole, User, upload_profile, users_repo
from mountains.utils import str_to_bool

logger = logging.getLogger(__name__)

__all__ = ["blueprint"]

blueprint = Blueprint(
    "members", __name__, template_folder="templates", static_folder="static"
)


@blueprint.route("/")
def members():
    with db_conn() as conn:
        members = users_repo(conn).list()

    if search := request.args.get("search"):
        low_search = search.lower()
        members = [u for u in members if low_search in u.full_name.lower()]

    members = sorted(members, key=_member_sort_key)
    limit = int(request.args.get("limit", 25))

    return render_template(
        "members/members.html.j2", members=members, search=search, limit=limit
    )


@blueprint.route("/<slug>", methods=["GET", "POST"])
def member(slug: str):
    if request.method == "POST":
        with db_conn() as conn:
            user = users_repo(conn).get_or_404(slug=slug)
            current_user.check_authorised(user.id)

            if "membership_expiry" in request.form:
                discord = DiscordAPI.from_app(current_app)
                if expiry_str := request.form["membership_expiry"]:
                    # We are making them a member
                    users_repo(conn).update(
                        id=user.id,
                        membership_expiry=datetime.datetime.strptime(
                            expiry_str, "%Y-%m-%d"
                        ).date(),
                    )

                    if user.membership_expiry is None and user.discord_id is not None:
                        # They were previously not a member, lets set it on Discord.
                        discord.set_member_role(user.discord_id)
                else:
                    # We are removing membership
                    if user.membership_expiry is not None:
                        users_repo(conn).update(id=user.id, membership_expiry=None)
                        if user.discord_id is not None:
                            discord.remove_member_role(user.discord_id)
            elif (
                is_coordinator := request.form.get(
                    "is_coordinator", type=str_to_bool, default=None
                )
            ) is not None:
                users_repo(conn).update(id=user.id, is_coordinator=is_coordinator)
            elif (
                is_winter_skills := request.form.get(
                    "is_winter_skills", type=str_to_bool, default=None
                )
            ) is not None:
                users_repo(conn).update(id=user.id, is_winter_skills=is_winter_skills)

            return redirect(url_for(".member", slug=slug))

    with db_conn() as conn:
        user = users_repo(conn).get_or_404(slug=slug)

        # Get member activity
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
        try:
            member = discord.get_member(member_id=user.discord_id)
            if member is not None:
                discord_name = member.member_name
        except ConnectionError:
            discord_name = "<Error communicating with discord>"

    return render_template(
        "members/member.html.j2",
        user=user,
        discord_name=discord_name,
        attended=attended,
        num_attended=num_attended,
    )


@blueprint.route("/<slug>/discord", methods=["GET", "POST"])
def member_discord(slug: str):
    if request.method == "POST":
        with db_conn() as conn:
            user = users_repo(conn).get_or_404(slug=slug)

            current_user.check_authorised(user.id)

            if "remove_id" in request.form:
                discord_id = None
            else:
                discord_id = request.form["discord_id"]

            users_repo(conn).update(id=user.id, discord_id=discord_id)

        return redirect(url_for(".member", slug=slug))
    else:
        with db_conn() as conn:
            user = users_repo(conn).get_or_404(slug=slug)
            taken_ids = set(
                u.discord_id
                for u in users_repo(conn).list()
                if u.discord_id is not None
            )

        discord = DiscordAPI.from_app(current_app)
        try:
            discord_members = sorted(
                [m for m in discord.fetch_all_members() if m.id not in taken_ids],
                key=lambda m: m.member_name.lower(),
            )
        except ConnectionError:
            discord_members = []

        return render_template(
            "members/member.discord.html.j2",
            user=user,
            discord_members=discord_members,
        )


@blueprint.route("/<int:id>/committee", methods=["GET", "POST"])
def committee_edit(id: int):
    with db_conn() as conn:
        user = users_repo(conn).get_or_404(id=id)

        if not (current_user.is_committee or current_user.is_admin):
            abort(403)

        if request.method == "POST":
            is_committee = "is_committee" in request.form

            if request.form["committee_role"] == "" or not is_committee:
                committee_role = None
            else:
                committee_role = CommitteeRole(
                    int(request.form["committee_role"])
                ).value

            users_repo(conn).update(
                id=user.id,
                is_committee="is_committee" in request.form,
                committee_bio=request.form["committee_bio"],
                committee_role=committee_role,
            )
            return redirect(url_for(".member", slug=user.slug))

    return render_template(
        "members/member.committee.html.j2", user=user, committee_roles=CommitteeRole
    )


@blueprint.route("/<int:id>/edit", methods=["GET", "POST"])
def edit_member(id: int):
    with db_conn() as conn:
        user = users_repo(conn).get_or_404(id=id)

    current_user.check_authorised(user.id)
    message = None
    if request.method == "POST":
        updates = {}

        if "profile_picture" in request.files:
            pic = request.files["profile_picture"]
            if pic.filename:
                updates["profile_picture_url"] = upload_profile(
                    file=request.files["profile_picture"],
                    static_dir=Path(current_app.config["STATIC_FOLDER"]),
                    user=user,
                )
            else:
                message = "No photo found to upload!"
        elif "password" in request.form:
            if request.form["password"] == request.form["confirm_password"]:
                updates["password_hash"] = generate_password_hash(
                    request.form["password"]
                )
            else:
                message = "Passwords do not match!"
        else:
            for field in [
                "first_name",
                "last_name",
                "mobile",
                "in_case_emergency",
                "about",
            ]:
                if field in request.form:
                    # TODO: Find a better way to share the user form data if validation fails
                    setattr(user, field, request.form[field])
                    if (
                        field in ["first_name", "last_name"]
                        and len(request.form[field]) == 0
                    ):
                        message = "Email, first name and last name cannot be blank!"
                    else:
                        updates[field] = request.form[field]

        if updates:
            with db_conn() as conn:
                users_repo(conn).update(id=user.id, **updates)

            # TODO: Flash message

            return redirect(url_for(".member", slug=user.slug))

    return render_template("members/member.edit.html.j2", user=user, message=message)


def _member_sort_key(user: User) -> tuple:
    return (
        not user.is_committee,
        not user.is_coordinator,
        not user.is_member,
        user.created_on_utc,
        user.last_name,
    )
