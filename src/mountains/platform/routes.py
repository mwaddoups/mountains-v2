import functools
import logging
from typing import Awaitable, Callable

from quart import (
    Blueprint,
    current_app,
    g,
    redirect,
    render_template,
    session,
    url_for,
)
from werkzeug import Response

from mountains.models import User

from ..repos import users

logger = logging.getLogger(__name__)


def needs_auth(method):
    @functools.wraps(method)
    async def _needs_auth(*args, **kwargs):
        if session.get("user_id") is not None:
            return await method(*args, **kwargs)
        else:
            return redirect(url_for("platform.login"))

    return _needs_auth


def routes(blueprint: Blueprint):
    @blueprint.before_request
    async def current_user():
        # Ensure all requests have access to the current user

        if (user_id := session.get("user_id")) is None:
            return redirect(url_for("login"))
        else:
            current_user = users(current_app.config["DB_NAME"]).get(id=user_id)
            if current_user is None:
                # Something weird happened
                return redirect(url_for("logout"))
            else:
                g.user = current_user

    @blueprint.route("/home")
    async def home():
        return await render_template("platform/home.html.j2")

    @blueprint.route("/members")
    async def members():
        return await render_template("platform/members.html.j2")
