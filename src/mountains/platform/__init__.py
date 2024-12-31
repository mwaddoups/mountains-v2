from flask import Blueprint

from .routes import routes

__all__ = ["blueprint"]

blueprint = Blueprint(
    "platform", __name__, url_prefix="/platform", template_folder="templates"
)

routes(blueprint)
