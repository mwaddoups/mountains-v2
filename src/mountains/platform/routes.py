import logging

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from mountains import albums, committee, events, members
from mountains.context import current_user, db_conn
from mountains.models.pages import latest_content
from mountains.models.tokens import tokens_repo
from mountains.models.users import users_repo
from mountains.payments import MembershipPaymentMetadata, StripeAPI

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.before_request
    def require_logon():
        logon_url_with_redirect = _hard_redirect(
            url_for("auth.login", redirect=request.path)
        )
        if (token_id := session.get("token_id")) is None:
            return logon_url_with_redirect
        else:
            with db_conn() as conn:
                token = tokens_repo(conn).get(id=token_id)
                if token is None:
                    # Something weird happened
                    del session["token_id"]
                    return logon_url_with_redirect

                user = users_repo(conn).get(id=token.user_id)
                if user is None:
                    # Something weird happened
                    del session["token_id"]
                    return logon_url_with_redirect
                elif (
                    user.is_dormant
                    and request.endpoint
                    and not request.endpoint.endswith("dormant")
                ):
                    # Needs to be absolute as wont necesarily be called from within this app
                    return _hard_redirect(url_for("platform.dormant"))

    @blueprint.route("/dormant/", methods=["GET", "POST"])
    def dormant():
        if request.method == "POST":
            with db_conn() as conn:
                users_repo(conn).update(id=current_user.id, is_dormant=False)
            return redirect(url_for(".home"))
        else:
            with db_conn() as conn:
                page = latest_content(conn, "dormant-return")
            return render_template("platform/dormant.html.j2", content=page)

    @blueprint.route("/")
    @blueprint.route("/info/")
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

    @blueprint.route("/resources/")
    def resources():
        with db_conn() as conn:
            page_text = latest_content(conn, "club-resources")
        return render_template("platform/info.page.html.j2", content=page_text)

    @blueprint.route("/feedback/")
    def feedback():
        with db_conn() as conn:
            page_text = latest_content(conn, "feedback-and-complaints")
        return render_template("platform/info.page.html.j2", content=page_text)

    @blueprint.route("/join/", methods=["GET", "POST"])
    def join():
        with db_conn() as conn:
            page = latest_content(conn, "join-club")
        active_expiry = current_app.config["CMC_MEMBERSHIP_EXPIRY"]
        stripe_api = StripeAPI.from_app(current_app)
        if request.method == "POST":
            metadata = MembershipPaymentMetadata(
                user_id=current_user.id,
                membership_expiry=active_expiry,
                date_of_birth=request.form["date_of_birth"],
                address=request.form["address"],
                postcode=request.form["postcode"],
                mobile_number=request.form["mobile_number"],
                ms_number=request.form["ms_number"],
            )

            checkout_url = stripe_api.create_checkout(
                request.form["price_id"],
                success_url=url_for(".join", _external=True, success=True),
                cancel_url=url_for(".join", _external=True, cancel=True),
                metadata=metadata,
            )

            return redirect(checkout_url)
        else:
            try:
                membership_prices = stripe_api.membership_options(active_expiry)
            except Exception:
                logger.exception("Error while fetching membership options from stripe!")
                membership_prices = []
            return render_template(
                "platform/joinclub.html.j2",
                join_page=page,
                join_success="success" in request.args,
                join_cancel="cancel" in request.args,
                membership_expiry=active_expiry,
                membership_prices=membership_prices,
            )

    blueprint.register_blueprint(members.blueprint, url_prefix="/members")
    blueprint.register_blueprint(committee.blueprint, url_prefix="/committee")
    blueprint.register_blueprint(albums.blueprint, url_prefix="/albums")
    blueprint.register_blueprint(events.blueprint, url_prefix="/events")


def _hard_redirect(url):
    if request.headers.get("HX-Request"):
        response = Response(status=200)
        response.headers["HX-Redirect"] = url
        return response
    else:
        response = redirect(url)

    return response
