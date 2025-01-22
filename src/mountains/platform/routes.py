import logging

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

from mountains import committee, members
from mountains.context import current_user, db_conn
from mountains.models.pages import latest_content
from mountains.models.tokens import tokens_repo
from mountains.models.users import users_repo
from mountains.payments import StripeAPI

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
                page = latest_content(conn, "dormant-return")
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
                bullet_pages = {
                    c: latest_content(conn, f"bullet-{c}")
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
                page_text = latest_content(conn, info_pages[page])
            return render_template("platform/info.page.html.j2", content=page_text)
        else:
            abort(404)

    @blueprint.route("/join")
    def join():
        with db_conn() as conn:
            page = latest_content(conn, "join-club")
        stripe_api = StripeAPI.from_app(current_app)
        active_expiry = current_app.config["CMC_MEMBERSHIP_EXPIRY"]
        membership_prices = stripe_api.membership_options(active_expiry)
        print(membership_prices)
        return render_template(
            "platform/joinclub.html.j2",
            join_page=page,
            membership_expiry=active_expiry,
            membership_prices=membership_prices,
        )

    blueprint.register_blueprint(members.blueprint, url_prefix="/members")
    blueprint.register_blueprint(committee.blueprint, url_prefix="/committee")

    event_routes(blueprint)

    photo_routes(blueprint)
