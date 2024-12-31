import logging

from quart import (
    Blueprint,
    current_app,
    g,
    redirect,
    render_template,
    session,
    url_for,
)

from mountains.db import connection
from mountains.tokens import tokens
from mountains.users import users

from .events import event_routes
from .members import member_routes

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.before_request
    async def current_user():
        # Ensure all requests have access to the current user
        if (token_id := session.get("token_id")) is None:
            return redirect(url_for("auth.login"))
        else:
            with connection(current_app.config["DB_NAME"]) as conn:
                token = tokens(conn).get(id=token_id)
                if token is None or (user := users(conn).get(id=token.user_id)) is None:
                    # Something weird happened
                    del session["token_id"]
                    return redirect(url_for("index"))
                else:
                    g.current_user = user

    @blueprint.route("/home")
    async def home():
        return await render_template("platform/home.html.j2")

    member_routes(blueprint)

    event_routes(blueprint)
