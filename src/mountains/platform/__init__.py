from quart import Blueprint, render_template

__all__ = ["blueprint"]

blueprint = Blueprint(
    "platform", __name__, url_prefix="/platform", template_folder="templates"
)


@blueprint.route("/")
@blueprint.route("/home")
async def home():
    return await render_template("platform/home.html.j2")


@blueprint.route("/")
@blueprint.route("/members")
async def members():
    return await render_template("platform/members.html.j2")
