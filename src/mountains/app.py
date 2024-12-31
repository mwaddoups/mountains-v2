import logging

import markdown
from quart import Quart, Response, render_template, request
from quart.logging import default_handler

from . import auth, platform


def create_app():
    app = Quart(__name__)

    # Set up logging for any logger on 'mountains'
    logger = logging.getLogger("mountains")
    logger.setLevel(logging.INFO)
    logger.addHandler(default_handler)

    # Load from the local .env file
    app.config.from_prefixed_env("QUART")
    logger.info("Running on DB: %s", app.config["DB_NAME"])
    # Ensure the session cookie as secure
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    app.register_blueprint(platform.blueprint)
    app.register_blueprint(auth.blueprint)

    @app.template_filter("markdown")
    def convert_markdown(s: str) -> str:
        return markdown.markdown(s)

    @app.route("/")
    async def index():
        # TODO: Editable pages.
        return await render_template("index.html.j2")

    @app.after_request
    async def ensure_preload_cached(response: Response):
        # We need to ensure that any preloaded links are valid for a few seconds
        if request.headers.get("HX-Preloaded") == "true":
            response.headers["Cache-Control"] = "private, max-age=5"
        return response

    return app
