import logging

from quart import Quart, Response, redirect, render_template, request, session, url_for
from quart.logging import default_handler
from werkzeug.security import check_password_hash

from . import platform, repos
from .models import User


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

    @app.route("/")
    async def index():
        return await render_template("index.html.j2")

    @app.route("/login", methods=["GET", "POST"])
    async def login():
        if request.method == "POST":
            form = await request.form
            db = repos.users(app.config["DB_NAME"])
            # TODO: Tokens db, add token to user, etc.
            # TODO: Password
            user = db.get(email=form["email"])
            if user is None or not check_password_hash(
                user.password_hash, form["password"]
            ):
                # TODO: Error handling
                return await render_template(
                    "login.html.j2", error="Login failed - check username and password"
                )
            else:
                logger.info("Logging in %s", user)
                session["user_id"] = user.id
                return redirect(url_for("platform.home"))
        else:
            return await render_template("login.html.j2")

    @app.route("/register", methods=["GET", "POST"])
    async def register():
        if request.method == "POST":
            form = await request.form
            if form["password"] != form["confirm_password"]:
                return await render_template(
                    "register.html.j2", error="Passwords do not match!"
                )
            user = User.from_registration(
                email=form["email"],
                password=form["password"],
                first_name=form["first_name"],
                last_name=form["last_name"],
                about=form["about"],
            )
            db = repos.users(app.config["DB_NAME"])
            db.insert(user)
            logger.info("New user registered: %s", user)
            return redirect(url_for("login"))
        else:
            return await render_template("register.html.j2")

    @app.route("/logout", methods=["POST"])
    async def logout():
        del session["user_id"]
        return redirect(url_for("index"))

    @app.after_request
    async def ensure_preload_cached(response: Response):
        # We need to ensure that any preloaded links are valid for a few seconds
        if request.headers.get("HX-Preloaded") == "true":
            response.headers["Cache-Control"] = "private, max-age=5"
        return response

    return app
