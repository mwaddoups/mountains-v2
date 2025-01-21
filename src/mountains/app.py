import datetime
import logging

import mistune
from flask import Flask, Response, g, render_template, request, session
from flask.logging import default_handler

from . import auth, platform
from .db import connection
from .models.pages import latest_page, pages_repo
from .models.tokens import tokens_repo
from .models.users import users_repo


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
        return mistune.html(s)  # type: ignore

    @app.context_processor
    def now_dt() -> dict:
        return {"now": datetime.datetime.now()}

    @app.route("/")
    def index():
        with connection(app.config["DB_NAME"]) as conn:
            page = latest_page(name="front-page", repo=pages_repo(conn))
        return render_template("page.html.j2", page=page)

    @app.route("/faqs")
    def faqs():
        with connection(app.config["DB_NAME"]) as conn:
            page = latest_page(name="faqs", repo=pages_repo(conn))
        return render_template("page.html.j2", page=page)

    @app.after_request
    def ensure_preload_cached(response: Response):
        # We need to ensure that any preloaded links are valid for a few seconds
        if request.headers.get("HX-Preloaded") == "true":
            response.headers["Cache-Control"] = "private, max-age=5"
        return response

    @app.before_request
    def current_user():
        # Ensure all requests have access to the current user, if logged in
        if (token_id := session.get("token_id")) is not None:
            with connection(app.config["DB_NAME"]) as conn:
                token = tokens_repo(conn).get(id=token_id)
                if (
                    token is not None
                    and (user := users_repo(conn).get(id=token.user_id)) is not None
                ):
                    g.current_user = user

    return app
