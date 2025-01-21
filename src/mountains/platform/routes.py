import datetime
import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from mountains.activity import activity_repo
from mountains.db import connection
from mountains.events import events as events_repo
from mountains.pages import Page, latest_page, pages_repo
from mountains.tokens import tokens as tokens_repo
from mountains.users import users as users_repo

from .events import event_routes
from .members import member_routes
from .photos import photo_routes

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.before_request
    def require_logon():
        if (token_id := session.get("token_id")) is None:
            return redirect(url_for("auth.login"))
        else:
            with connection(current_app.config["DB_NAME"]) as conn:
                token = tokens_repo(conn).get(id=token_id)
                if token is None or users_repo(conn).get(id=token.user_id) is None:
                    # Something weird happened
                    del session["token_id"]
                    return redirect(url_for("auth.login"))

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
            with connection(current_app.config["DB_NAME"]) as conn:
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
            with connection(current_app.config["DB_NAME"]) as conn:
                page_text = latest_page(
                    name=info_pages[page], repo=pages_repo(conn)
                ).markdown
            return render_template("platform/info.page.html.j2", content=page_text)
        else:
            abort(404)

    @blueprint.route("/join")
    def join():
        with connection(current_app.config["DB_NAME"]) as conn:
            page = latest_page(name="join-club", repo=pages_repo(conn))
        return render_template("platform/joinclub.html.j2", join_page=page.markdown)

    @blueprint.route("/committee")
    def committee():
        if not g.current_user.is_authorised():
            abort(403)

        num_activities = request.args.get("num_activities", type=int, default=50)

        with connection(current_app.config["DB_NAME"]) as conn:
            member_stats = [
                dict(s)
                for s in conn.execute("""
                SELECT membership_expiry, COUNT(id) as num_members 
                FROM users GROUP BY membership_expiry
            """).fetchall()
            ]

            for r in member_stats:
                if r["membership_expiry"] is not None:
                    r["membership_expiry"] = datetime.datetime.fromisoformat(
                        r["membership_expiry"]
                    )

            user_map = {u.id: u for u in users_repo(conn).list()}
            event_map = {e.id: e for e in events_repo(conn).list()}

            activities = sorted(
                activity_repo(conn).list(), key=lambda a: a.dt, reverse=True
            )

        return render_template(
            "platform/committee.html.j2",
            member_stats=member_stats,
            activities=activities,
            num_activities=num_activities,
            user_map=user_map,
            event_map=event_map,
        )

    @blueprint.route("/committee/pages", methods=["GET", "POST"])
    def committee_pages():
        preview = None
        message = None
        if request.method == "POST":
            if not g.current_user.is_site_admin:
                abort(403)

            if "preview" in request.form:
                preview = request.form
            else:
                with connection(current_app.config["DB_NAME"]) as conn:
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

        with connection(current_app.config["DB_NAME"]) as conn:
            all_pages = pages_repo(conn).list()
            page_names = set(p.name for p in all_pages)
            pages = sorted(
                [latest_page(name, pages_repo(conn)) for name in page_names],
                key=lambda p: p.description,
            )
        return render_template(
            "platform/pages.edit.html.j2", pages=pages, preview=preview, message=message
        )

    member_routes(blueprint)

    event_routes(blueprint)

    photo_routes(blueprint)
