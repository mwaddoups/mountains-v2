import logging
from collections import defaultdict
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

from mountains.context import current_user, db_conn
from mountains.discord import DiscordAPI
from mountains.models.activity import activity_repo
from mountains.models.events import attendees_repo, events_repo
from mountains.models.pages import Page, latest_page, pages_repo
from mountains.models.users import users_repo
from mountains.utils import now_utc, slugify

logger = logging.getLogger(__name__)


__all__ = ["blueprint"]

blueprint = Blueprint(
    "committee", __name__, template_folder="templates", static_folder="static"
)


@blueprint.before_request
def check_authorised():
    if not current_user.is_committee and not current_user.is_admin:
        abort(403)


@blueprint.route("/")
def overview():
    num_activities = request.args.get("num_activities", type=int, default=50)

    with db_conn() as conn:
        # Get these for sharing data
        user_map = {u.id: u for u in users_repo(conn).list()}
        event_map = {e.id: e for e in events_repo(conn).list()}

        # Get activities
        activities = sorted(
            activity_repo(conn).list(), key=lambda a: a.dt, reverse=True
        )

    # Get member counts
    member_stats = defaultdict(int)
    for u in user_map.values():
        if not u.is_dormant:
            member_stats[u.membership_expiry] += 1

    return render_template(
        "committee/overview.html.j2",
        member_stats=member_stats,
        activities=activities,
        num_activities=num_activities,
        user_map=user_map,
        event_map=event_map,
    )


@blueprint.route("/maintenance/")
def maintenance():
    with db_conn() as conn:
        # Get these for sharing data
        user_map = {u.id: u for u in users_repo(conn).list()}
        event_map = {e.id: e for e in events_repo(conn).list()}
        # Get activities
        activities = sorted(
            activity_repo(conn).list(), key=lambda a: a.dt, reverse=True
        )

    try:
        discord = DiscordAPI.from_app(current_app)
        discord_names = {m.id: m.member_name for m in discord.fetch_all_members()}
    except ConnectionError:
        # Discord is down
        discord_names = {
            u.discord_id: "<Error communicating with discord>"
            for u in user_map.values()
            if u.discord_id is not None
        }

    # Calculate dormant user info
    dormant_users = [
        {
            "user": u,
            "discord_name": discord_names.get(
                u.discord_id, "<ID missing from Discord?>"
            )
            if u.discord_id
            else None,
            "last_activity": max(
                [a.dt for a in activities if a.user_id == u.id],
                default=None,
            ),
        }
        for u in user_map.values()
        if not u.is_dormant and u.is_inactive_on(now_utc(), threshold_days=90)
    ]

    return render_template(
        "committee/maintenance.html.j2",
        activities=activities,
        message=request.args.get("message"),
        dormant_users=dormant_users,
        user_map=user_map,
        event_map=event_map,
    )


@blueprint.route("/dormant/<int:user_id>/", methods=["POST"])
def member_dormant(user_id: int):
    with db_conn() as conn:
        users_db = users_repo(conn)
        user = users_db.get(id=user_id)
        if user is None:
            abort(404)

        users_db.update(id=user.id, is_dormant=True)

    return redirect(
        url_for(
            ".maintenance",
            _anchor="dormant-users",
            message=f"Made {user.full_name} dormant!",
        )
    )


@blueprint.route("/treasurer/")
def treasurer():
    with db_conn() as conn:
        # Get these for sharing data
        user_map = {u.id: u for u in users_repo(conn).list()}
        event_map = {e.id: e for e in events_repo(conn).list()}

        # Get unpaid users
        attendees = attendees_repo(conn).list_where(
            is_trip_paid=False, is_waiting_list=False
        )
        unpaid_attendees = [
            a
            for a in attendees
            if event_map[a.event_id].price_id is not None
            and event_map[a.event_id].is_upcoming()
        ]
        unpaid_events = [
            event_map[e_id] for e_id in set(a.event_id for a in unpaid_attendees)
        ]

    return render_template(
        "committee/treasurer.html.j2",
        active_expiry=current_app.config["CMC_MEMBERSHIP_EXPIRY"],
        user_map=user_map,
        event_map=event_map,
        unpaid_events=unpaid_events,
        unpaid_attendees=unpaid_attendees,
    )


@blueprint.route("/pages/", methods=["GET", "POST"])
def page_editor():
    CONTENT_PATH = Path(current_app.config["STATIC_FOLDER"]) / "content"
    preview = None
    message = request.args.get("message")
    if request.method == "POST":
        message = None
        if "preview" in request.form:
            preview = request.form
        else:
            with db_conn() as conn:
                pages_db = pages_repo(conn)
                if "new" in request.form:
                    page = Page(
                        name=request.form["name"],
                        description=request.form["description"],
                        markdown=request.form["markdown"],
                        version=1,
                    )
                    if pages_db.get(name=page.name) is None:
                        pages_db.insert(page)
                        message = f"Created new page {page.name}"
                    else:
                        message = (
                            f"Could not create page - name {page.name} already exists!"
                        )
                elif "edit" in request.form:
                    latest = latest_page(request.form["name"], repo=pages_db)
                    page = Page(
                        name=request.form["name"],
                        description=request.form["description"],
                        markdown=request.form["markdown"],
                        version=latest.version + 1,
                    )
                    pages_db.insert(page)
                    message = f"Page {page.name} was updated successfully!"
                elif "update_name" in request.form:
                    old_name = request.form["old_name"]
                    new_name = request.form["new_name"]
                    pages_db.update(_where={"name": old_name}, name=new_name)
                    message = f"Changed name from {old_name} -> {new_name}"
                elif "add_image" in request.form:
                    file = request.files["image_file"]
                    if file.filename is not None:
                        name = slugify(request.form["name"])
                        file_name = Path(file.filename).with_stem(name)
                        file_path = CONTENT_PATH / file_name
                        if file_path.exists():
                            message = f"File name {file_name} already exists!"
                        else:
                            file.save(CONTENT_PATH / file_name)
                            message = f"Image {file_name} uploaded successfully."

            if message is not None:
                return redirect(url_for(".page_editor", message=message))
            else:
                return redirect(url_for(".page_editor"))

    with db_conn() as conn:
        all_pages = pages_repo(conn).list()
        page_names = set(p.name for p in all_pages)
        pages = sorted(
            [latest_page(name, pages_repo(conn)) for name in page_names],
            key=lambda p: p.description,
        )

    image_paths = [Path("content") / f.name for f in CONTENT_PATH.glob("*")]

    # Get images
    return render_template(
        "committee/pages.edit.html.j2",
        pages=pages,
        preview=preview,
        message=message,
        image_paths=image_paths,
    )
