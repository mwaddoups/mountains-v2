import csv
import logging
from collections import defaultdict
from io import StringIO
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from requests.exceptions import ConnectionError

from mountains.context import current_user, db_conn
from mountains.discord import DiscordAPI
from mountains.events import EventType
from mountains.models.activity import activity_repo
from mountains.models.events import attendees_repo, events_repo
from mountains.models.pages import Page, latest_page, pages_repo
from mountains.models.stripetransaction import stripe_transactions_repo
from mountains.models.users import users_repo
from mountains.payments import StripeAPI
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

    discord_names: dict[str | None, str]
    discord_is_member: dict[str | None, bool]
    try:
        discord = DiscordAPI.from_app(current_app)
        discord_members = {m.id: m for m in discord.fetch_all_members()}
        discord_names = {m.id: m.member_name for m in discord_members.values()}
        discord_is_member = {m.id: m.is_member for m in discord_members.values()}
    except ConnectionError:
        # Discord is down
        discord_is_member = {}
        discord_names = {
            u.discord_id: "<Error communicating with discord>"
            for u in user_map.values()
            if u.discord_id is not None
        }

    # Calculate dormant user info
    discord_names[None] = "<No Discord link set>"
    dormant_users = [
        {
            "user": u,
            "discord_name": discord_names.get(
                u.discord_id, "<Was on discord, but now missing?>"
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

    member_mismatches = [
        {
            "user": u,
            "discord_name": discord_names.get(
                u.discord_id, "<Was on discord, but now missing?>"
            ),
            "discord_member": discord_is_member.get(u.discord_id, False),
        }
        for u in user_map.values()
        if (u.is_member and not discord_is_member.get(u.discord_id, False))
        or (not u.is_member and discord_is_member.get(u.discord_id, False))
    ]

    return render_template(
        "committee/maintenance.html.j2",
        activities=activities,
        message=request.args.get("message"),
        dormant_users=dormant_users,
        member_mismatches=member_mismatches,
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

        users_db.update(id=user.id, is_dormant=True, discord_id=None)

    return redirect(
        url_for(
            ".maintenance",
            _anchor="dormant-users",
            message=f"Made {user.full_name} dormant!",
        )
    )


@blueprint.route("/treasurer/", methods=["GET", "POST"])
def treasurer():
    if request.method == "POST":
        details = ""
        if "stripe" in request.form:
            api = StripeAPI.from_app(current_app)
            with db_conn() as conn:
                current_trans = stripe_transactions_repo(conn).list()
                last_trans = max(current_trans, key=lambda x: x.dt_utc, default=None)
            transactions = api.fetch_balance_transactions(since=last_trans)
            with db_conn() as conn:
                trans_repo = stripe_transactions_repo(conn)
                for t in transactions:
                    trans_repo.insert(t)
            details = f"Inserted {len(transactions)} newer transactions."
        elif "stripe_older" in request.form:
            api = StripeAPI.from_app(current_app)
            with db_conn() as conn:
                current_trans = stripe_transactions_repo(conn).list()
                last_trans = min(current_trans, key=lambda x: x.dt_utc, default=None)
            transactions = api.fetch_balance_transactions(before=last_trans)
            with db_conn() as conn:
                trans_repo = stripe_transactions_repo(conn)
                for t in transactions:
                    trans_repo.insert(t)
            details = f"Inserted {len(transactions)} older transactions."
        else:
            logger.info("Deleting all transactions from stripe DB!")
            with db_conn() as conn:
                trans_repo = stripe_transactions_repo(conn)
                all_trans = trans_repo.list()
                for t in all_trans:
                    trans_repo.delete_where(id=t.id)
                details = f"Removed {len(all_trans)} transactions."

        return redirect(url_for(".treasurer", details=details))
    else:
        with db_conn() as conn:
            # Get these for sharing data
            user_map = {u.id: u for u in users_repo(conn).list()}
            event_map = {e.id: e for e in events_repo(conn).list()}

            # Get unpaid users
            attendees = attendees_repo(conn).list_where(
                is_trip_paid=False, is_waiting_list=False
            )
            unpaid_attendees = [a for a in attendees if event_map[a.event_id].price_id]

            stripe_trans = sorted(
                stripe_transactions_repo(conn).list(),
                key=lambda x: x.dt_utc,
                reverse=True,
            )

        # All paid events, or historic ones where users still haven't paid
        upcoming_paid_events = [
            e
            for e in event_map.values()
            if (e.is_upcoming() and e.price_id)
            or (e.id in set(a.event_id for a in unpaid_attendees))
        ]

        upcoming_weekends_without_prices = [
            e
            for e in event_map.values()
            if e.is_upcoming()
            and e.event_type in (EventType.SUMMER_WEEKEND, EventType.WINTER_WEEKEND)
            and not e.price_id
        ]

        return render_template(
            "committee/treasurer.html.j2",
            active_expiry=current_app.config["CMC_MEMBERSHIP_EXPIRY"],
            user_map=user_map,
            event_map=event_map,
            upcoming_paid_events=upcoming_paid_events,
            upcoming_weekends_without_prices=upcoming_weekends_without_prices,
            unpaid_attendees=unpaid_attendees,
            stripe_trans=stripe_trans,
            num_trans=request.args.get("num_trans", 10, type=int),
            details=request.args.get("details"),
        )


@blueprint.route("/treasurer/transactions")
def transactions_csv():
    with db_conn() as conn:
        stripe_trans = sorted(
            stripe_transactions_repo(conn).list(),
            key=lambda x: x.dt_utc,
            reverse=True,
        )
        user_map = {u.id: u for u in users_repo(conn).list()}
        event_map = {e.id: e for e in events_repo(conn).list()}

    output = StringIO()
    csv_w = csv.DictWriter(
        output,
        [
            "trans_id",
            "date",
            "category",
            "stripe_type",
            "net",
            "gross",
            "fee",
            "user_id",
            "user_full_name",
            "event_id",
            "event_title",
        ],
    )
    csv_w.writeheader()
    csv_w.writerows([
        {
            "trans_id": t.id,
            "date": t.dt_utc,
            "category": t.category(),
            "stripe_type": t.stripe_type,
            "net": t.net(),
            "gross": t.gross(),
            "fee": t.stripe_fee(),
            "user_id": t.user_id,
            "user_full_name": user_map[t.user_id].full_name
            if t.user_id in user_map
            else "",
            "event_id": t.event_id,
            "event_title": event_map[t.event_id].title
            if t.event_id in event_map
            else "",
        }
        for t in stripe_trans
    ])

    output = make_response(output.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=transactions.csv"
    output.headers["Content-type"] = "text/csv"
    return output


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
