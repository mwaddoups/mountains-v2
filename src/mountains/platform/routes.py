import logging

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    session,
    url_for,
)

from mountains.db import connection
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

    member_routes(blueprint)

    event_routes(blueprint)

    photo_routes(blueprint)
