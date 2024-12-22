import logging

from quart import Quart, render_template
from quart.logging import default_handler

from . import platform

logger = logging.getLogger("mountains")


def create_app():
    app = Quart(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(default_handler)
    app.config.from_prefixed_env("QUART_")

    app.register_blueprint(platform.blueprint)

    @app.route("/")
    async def index():
        return await render_template("index.html.j2")

    return app
