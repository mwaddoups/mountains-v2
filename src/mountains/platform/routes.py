import logging
from collections import defaultdict

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from mountains import members
from mountains.context import current_user, db_conn
from mountains.discord import DiscordAPI
from mountains.models.activity import activity_repo
from mountains.models.events import events_repo
from mountains.models.pages import Page, latest_page, pages_repo
from mountains.models.tokens import tokens_repo
from mountains.models.users import users_repo
from mountains.utils import now_utc

from .events import event_routes
from .photos import photo_routes

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.before_request
    def require_logon():
        if (token_id := session.get("token_id")) is None:
            return redirect(url_for("auth.login"))
        else:
            with db_conn() as conn:
                token = tokens_repo(conn).get(id=token_id)
                if token is None:
                    # Something weird happened
                    del session["token_id"]
                    return redirect(url_for("auth.login"))

                user = users_repo(conn).get(id=token.user_id)
                if user is None:
                    # Something weird happened
                    del session["token_id"]
                    return redirect(url_for("auth.login"))
                elif (
                    user.is_dormant
                    and request.endpoint
                    and not request.endpoint.endswith("dormant")
                ):
                    return redirect(url_for(".dormant"))

    @blueprint.route("/dormant", methods=["GET", "POST"])
    def dormant():
        if request.method == "POST":
            with db_conn() as conn:
                users_repo(conn).update(id=current_user.id, is_dormant=False)
            return redirect(url_for(".home"))
        else:
            with db_conn() as conn:
                page = latest_page(
                    name="dormant-return", repo=pages_repo(conn)
                ).markdown
            return render_template("platform/dormant.html.j2", content=page)

    @blueprint.route("/info")
    @blueprint.route("/info/<page>")
    def home(page: str | None = None):
        info_pages = {
            "day-walks": "info-day-walks",
            "hut-weekends": "info-hut-weekends",
            "climbing": "info-climbing",
            "running": "info-running",
        }
        if page is None:
            with db_conn() as conn:
                pages_db = pages_repo(conn)
                bullet_pages = {
                    c: latest_page(f"bullet-{c}", pages_db).markdown
                    for c in (
                        "day-walks",
                        "hut-weekends",
                        "indoor-climbing",
                        "outdoor-climbing",
                        "running",
                        "winter",
                        "socials",
                    )
                }
            return render_template("platform/home.html.j2", bullet_pages=bullet_pages)
        elif page in info_pages:
            with db_conn() as conn:
                page_text = latest_page(
                    name=info_pages[page], repo=pages_repo(conn)
                ).markdown
            return render_template("platform/info.page.html.j2", content=page_text)
        else:
            abort(404)

    @blueprint.route("/join")
    def join():
        with db_conn() as conn:
            page = latest_page(name="join-club", repo=pages_repo(conn))
        return render_template("platform/joinclub.html.j2", join_page=page.markdown)

    @blueprint.route("/committee")
    def committee():
        if not current_user.is_authorised():
            abort(403)

        num_activities = request.args.get("num_activities", type=int, default=50)

        discord = DiscordAPI.from_app(current_app)
        discord_names = {m.id: m.member_name for m in discord.fetch_all_members()}

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
            "platform/committee.html.j2",
            member_stats=member_stats,
            activities=activities,
            num_activities=num_activities,
            dormant_users=dormant_users,
            user_map=user_map,
            event_map=event_map,
        )

    @blueprint.route("/committee/dormant/<int:user_id>", methods=["POST"])
    def committee_member_dormant(user_id: int):
        with db_conn() as conn:
            users_db = users_repo(conn)
            user = users_db.get(id=user_id)
            if user is None:
                abort(404)

            users_db.update(id=user.id, is_dormant=True)

        return redirect(url_for(".committee", _anchor="dormant-users"))

    @blueprint.route("/committee/pages", methods=["GET", "POST"])
    def committee_pages():
        preview = None
        message = None
        if request.method == "POST":
            if not current_user.is_site_admin:
                abort(403)

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
                            message = f"Could not create page - name {page.name} already exists!"
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

        with db_conn() as conn:
            all_pages = pages_repo(conn).list()
            page_names = set(p.name for p in all_pages)
            pages = sorted(
                [latest_page(name, pages_repo(conn)) for name in page_names],
                key=lambda p: p.description,
            )
        return render_template(
            "platform/pages.edit.html.j2", pages=pages, preview=preview, message=message
        )

    # member_routes(blueprint)
    blueprint.register_blueprint(members.blueprint, url_prefix="/members")

    event_routes(blueprint)

    photo_routes(blueprint)
