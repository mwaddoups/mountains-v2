import logging
import uuid

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from mountains.db import connection
from mountains.email import send_mail
from mountains.tokens import AuthToken, tokens
from mountains.users import User, users

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            form = request.form
            with connection(current_app.config["DB_NAME"]) as conn:
                user_db = users(conn)
                token_db = tokens(conn)

                user = user_db.get(email=form["email"])
                if user is None or not check_password_hash(
                    user.password_hash, form["password"]
                ):
                    # TODO: Error handling
                    return redirect(
                        url_for(
                            "auth.login",
                            error="Login failed - check username and password.",
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

        return render_template("auth/login.html.j2", error=request.args.get("error"))

    @blueprint.route("/forgotpassword", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            form = request.form
            email = form["email"]
            with connection(current_app.config["DB_NAME"]) as conn:
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
            return render_template("auth/forgotpassword.html.j2", was_reset=True)
        else:
            return render_template("auth/forgotpassword.html.j2")

    @blueprint.route("/resetpassword", methods=["GET", "POST"])
    def reset_password():
        with connection(current_app.config["DB_NAME"]) as conn:
            token_id = request.args.get("token")
            token_db = tokens(conn)
            if token_id is None or (token := token_db.get(id=token_id)) is None:
                return render_template("auth/resetpassword.html.j2", is_valid=False)

            if request.method == "POST":
                user_db = users(conn)
                user = user_db.get(id=token.user_id)
                assert user is not None
                form = request.form
                if form["password"] != form["confirm_password"]:
                    return render_template(
                        "resetpassword.html.j2", error="Entered passwords do not match."
                    )
                else:
                    password_hash = generate_password_hash(form["password"])
                    user_db.update(id=user.id, password_hash=password_hash)

                    return redirect(
                        url_for("auth.login", error="Password reset - please login.")
                    )
        return render_template("resetpassword.html.j2")

    @blueprint.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            # New user registration
            form = request.form
            if form["password"] != form["confirm_password"]:
                return render_template(
                    "register.html.j2", error="Passwords do not match!"
                )
            with connection(current_app.config["DB_NAME"]) as conn:
                user_db = users(conn)
                if user_db.get(email=form["email"]) is not None:
                    return render_template(
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
                return redirect(url_for("auth.login"))
        return render_template("auth/register.html.j2")

    @blueprint.route("/logout", methods=["POST"])
    def logout():
        del session["token_id"]
        return redirect(url_for("index"))
