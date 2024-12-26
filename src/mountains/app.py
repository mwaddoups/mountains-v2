import logging
import uuid

import markdown
from quart import Quart, Response, redirect, render_template, request, session, url_for
from quart.logging import default_handler
from werkzeug.security import check_password_hash, generate_password_hash

from . import platform
from .db import connection
from .email import send_mail
from .tokens import AuthToken, tokens
from .users import User, users


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

    @app.template_filter("markdown")
    def convert_markdown(s: str) -> str:
        return markdown.markdown(s)

    @app.route("/")
    async def index():
        return await render_template("index.html.j2")

    @app.route("/auth/login", methods=["GET", "POST"])
    async def login(error: str | None = None):
        if request.method == "POST":
            form = await request.form
            with connection(app.config["DB_NAME"]) as conn:
                user_db = users(conn)
                token_db = tokens(conn)

                user = user_db.get(email=form["email"])
                if user is None or not check_password_hash(
                    user.password_hash, form["password"]
                ):
                    # TODO: Error handling
                    return redirect(
                        url_for(
                            "login", error="Login failed - check username and password."
                        )
                    )
                else:
                    logger.info("Logging in %s", user)
                    token = token_db.get(user_id=user.id)
                    if token is None:
                        logger.info("Generating new token for %s...", user)
                        token = AuthToken.from_id(id=user.id, valid_days=30)
                        token_db.insert(token)

                    # TODO: This needs to be a proper permanent token
                    session["token_id"] = token.id
                    return redirect(url_for("platform.home"))

        return await render_template("login.html.j2", error=error)

    @app.route("/auth/forgotpassword", methods=["GET", "POST"])
    async def forgot_password():
        if request.method == "POST":
            form = await request.form
            email = form["email"]
            with connection(app.config["DB_NAME"]) as conn:
                user_db = users(conn)
                if (user := user_db.get(email=email)) is not None:
                    logger.info("Resetting password for %s", user)
                    token_db = tokens(conn)
                    # Delete all old tokens
                    token_db.delete_where(user_id=user.id)

                    # Reset the password to some nonsense
                    user_db.update(id=user.id, password_hash=str(uuid.uuid4()))

                    # Create a short-term token
                    token = AuthToken.from_id(id=user.id, valid_mins=15)
                    token_db.insert(token)

                    reset_url = url_for(
                        "reset_password", token=token.id, _external=True
                    )
                    send_mail(
                        user.email,
                        "Password reset for CMC",
                        f"Reset your password: {reset_url}",
                    )
            return await render_template("forgotpassword.html.j2", was_reset=True)
        else:
            return await render_template("forgotpassword.html.j2")

    @app.route("/auth/resetpassword", methods=["GET", "POST"])
    async def reset_password():
        with connection(app.config["DB_NAME"]) as conn:
            token_id = request.args.get("token")
            token_db = tokens(conn)
            if token_id is None or (token := token_db.get(id=token_id)) is None:
                return await render_template("resetpassword.html.j2", is_valid=False)

            if request.method == "POST":
                user_db = users(conn)
                user = user_db.get(id=token.user_id)
                assert user is not None
                form = await request.form
                if form["password"] != form["confirm_password"]:
                    return await render_template(
                        "resetpassword.html.j2", error="Entered passwords do not match."
                    )
                else:
                    password_hash = generate_password_hash(form["password"])
                    user_db.update(id=user.id, password_hash=password_hash)

                    return redirect(
                        url_for("login", error="Password reset - please login.")
                    )
        return await render_template("resetpassword.html.j2")

    @app.route("/auth/register", methods=["GET", "POST"])
    async def register():
        if request.method == "POST":
            # New user registration
            form = await request.form
            if form["password"] != form["confirm_password"]:
                return await render_template(
                    "register.html.j2", error="Passwords do not match!"
                )
            with connection(app.config["DB_NAME"]) as conn:
                user_db = users(conn)
                if user_db.get(email=form["email"]) is not None:
                    return await render_template(
                        "register.html.j2", error="Email is not unique - try again!"
                    )
                password_hash = generate_password_hash(form["password"])
                user = User.from_registration(
                    id=user_db.next_id(),
                    email=form["email"],
                    password_hash=password_hash,
                    first_name=form["first_name"],
                    last_name=form["last_name"],
                    about=form["about"],
                    mobile=form["mobile"],
                )

                logger.info("Registering new user %s...", user)
                user_db.insert(user)
                return redirect(url_for("login"))
        return await render_template("register.html.j2")

    @app.route("/auth/logout", methods=["POST"])
    async def logout():
        del session["token_id"]
        return redirect(url_for("index"))

    @app.after_request
    async def ensure_preload_cached(response: Response):
        # We need to ensure that any preloaded links are valid for a few seconds
        if request.headers.get("HX-Preloaded") == "true":
            response.headers["Cache-Control"] = "private, max-age=5"
        return response

    return app
