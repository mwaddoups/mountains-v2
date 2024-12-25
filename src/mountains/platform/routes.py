import logging

from quart import (
    Blueprint,
    g,
    redirect,
    render_template,
    session,
    url_for,
)

from .events import event_routes
from .members import member_routes, users_repo

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.before_request
    async def current_user():
        # Ensure all requests have access to the current user

        if (user_id := session.get("user_id")) is None:
            return redirect(url_for("login"))
        else:
            current_user = users_repo().get(id=user_id)
            if current_user is None:
                # Something weird happened
                del session["user_id"]
                return redirect(url_for("index"))
            else:
                g.current_user = current_user

    @blueprint.route("/home")
    async def home():
        return await render_template("platform/home.html.j2")

    member_routes(blueprint)

    event_routes(blueprint)
