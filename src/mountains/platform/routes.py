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

from mountains.db import connection
from mountains.pages import Page, pages_repo
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

    @blueprint.route("/home")
    def home():
        return render_template("platform/home.html.j2")

    @blueprint.route("/committee")
    def committee():
        if not g.current_user.is_authorised():
            abort(403)

        with connection(current_app.config["DB_NAME"]) as conn:
            member_stats = [
                dict(s)
                for s in conn.execute("""
                SELECT membership_expiry_utc, COUNT(id) as num_members 
                FROM users GROUP BY membership_expiry_utc
            """).fetchall()
            ]

            for r in member_stats:
                if r["membership_expiry_utc"] is not None:
                    r["membership_expiry_utc"] = datetime.datetime.fromisoformat(
                        r["membership_expiry_utc"]
                    )

        return render_template("platform/committee.html.j2", member_stats=member_stats)

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
                    page = Page(
                        name=request.form["name"],
                        description=request.form["description"],
                        markdown=request.form["markdown"],
                    )
                    exists = pages_db.get(name=page.name) is not None
                    if "new" in request.form:
                        if exists:
                            pages_db.insert(page)
                            message = f"Created new page {page.name}"
                        else:
                            message = f"Could not create page - name {page.name} already exists!"

                    if "edit" in request.form:
                        if exists:
                            pages_db.delete_where(name=page.name)
                            pages_db.insert(page)
                            message = f"Page {page.name} was updated successfully!"
                        else:
                            message = (
                                f"Could not find page to edit with name: {page.name}!"
                            )

        with connection(current_app.config["DB_NAME"]) as conn:
            pages = pages_repo(conn).list()
        return render_template(
            "platform/pages.edit.html.j2", pages=pages, preview=preview, message=message
        )

    member_routes(blueprint)

    event_routes(blueprint)

    photo_routes(blueprint)
