from flask import Blueprint

from .routes import routes

__all__ = ["blueprint"]

blueprint = Blueprint("auth", __name__, url_prefix="/auth", template_folder="templates")

routes(blueprint)
