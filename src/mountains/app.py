import logging

import markdown
from flask import Flask, Response, render_template, request
from flask.logging import default_handler

from . import auth, platform


def create_app():
    app = Flask(__name__)

    # Set up logging for any logger on 'mountains'
    logger = logging.getLogger("mountains")
    logger.setLevel(logging.INFO)
    logger.addHandler(default_handler)

    # Load from the local .env file
    app.config.from_prefixed_env("FLASK")
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
    def index():
        # TODO: Editable pages.
        return render_template("index.html.j2")

    @app.after_request
    def ensure_preload_cached(response: Response):
        # We need to ensure that any preloaded links are valid for a few seconds
        if request.headers.get("HX-Preloaded") == "true":
            response.headers["Cache-Control"] = "private, max-age=5"
        return response

    return app
