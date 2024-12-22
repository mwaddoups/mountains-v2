import logging

from quart import Blueprint, render_template, request

from mountains.models import User

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.route("/register", methods=["GET", "POST"])
    async def register():
        if request.method == "POST":
            form = await request.form
            logger.debug("Registration form: %r", form)
            user = User.from_registration(**form)
            logger.info("User: %s", user)
            return await render_template("platform/register.html.j2")
        else:
            return await render_template("platform/register.html.j2")

    @blueprint.route("/home")
    async def home():
        return await render_template("platform/home.html.j2")

    @blueprint.route("/members")
    async def members():
        return await render_template("platform/members.html.j2")
