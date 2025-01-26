import logging
import uuid
from typing import Mapping

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

from mountains.context import db_conn, send_mail
from mountains.errors import MountainException
from mountains.models.tokens import AuthToken, tokens_repo
from mountains.models.users import User, users_repo
from mountains.utils import now_utc

logger = logging.getLogger(__name__)

__all__ = ["blueprint"]

blueprint = Blueprint("auth", __name__, url_prefix="/auth", template_folder="templates")


@blueprint.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        form = request.form
        with db_conn() as conn:
            user_db = users_repo(conn)
            token_db = tokens_repo(conn)

            user = user_db.get(email=form["email"])
            if user is None or not check_password_hash(
                user.password_hash, form["password"]
            ):
                return redirect(
                    url_for(
                        "auth.login",
                        error="Login failed - check username and password.",
                    )
                )
            else:
                # Do login (update last_login)
                logger.info("Logging in %s", user)
                user_db.update(id=user.id, last_login_utc=now_utc())

                logger.debug("Expiring any old tokens for %s...", user)
                for token in token_db.list_where(id=user.id):
                    if not token.is_valid():
                        logger.info("Removing old token %r", token)
                        token_db.delete_where(id=token.id)

                logger.debug("Generating new token for %s...", user)
                token = AuthToken.from_id(id=user.id, valid_days=30)
                token_db.insert(token)
                session["token_id"] = token.id
                return redirect(url_for("platform.home"))

    return render_template("auth/login.html.j2", error=request.args.get("error"))


@blueprint.route("/forgotpassword", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        with db_conn() as conn:
            user_db = users_repo(conn)
            if (user := user_db.get(email=email)) is not None:
                logger.info("Resetting password for %s", user)
                token_db = tokens_repo(conn)
                # Delete all old tokens
                token_db.delete_where(user_id=user.id)

                # Reset the password to some nonsense
                user_db.update(id=user.id, password_hash=str(uuid.uuid4()))

                # Create a short-term token
                token = AuthToken.from_id(id=user.id, valid_mins=15)
                token_db.insert(token)

                reset_url = url_for(
                    "auth.reset_password", token=token.id, _external=True
                )
                send_mail(
                    to=[user.email],
                    subject="Password reset for CMC",
                    msg_markdown=f"Reset your password: {reset_url}",
                )
        return render_template("auth/forgotpassword.html.j2", was_reset=True)
    else:
        return render_template("auth/forgotpassword.html.j2")


@blueprint.route("/resetpassword", methods=["GET", "POST"])
def reset_password():
    with db_conn() as conn:
        token_id = request.args.get("token")
        token_db = tokens_repo(conn)
        if token_id is None or (token := token_db.get(id=token_id)) is None:
            return render_template("auth/resetpassword.html.j2", is_valid=False)

        if request.method == "POST":
            user_db = users_repo(conn)
            user = user_db.get(id=token.user_id)
            assert user is not None
            form = request.form
            if form["password"] != form["confirm_password"]:
                return render_template(
                    "auth/resetpassword.html.j2",
                    error="Entered passwords do not match.",
                )
            else:
                password_hash = generate_password_hash(form["password"])
                user_db.update(id=user.id, password_hash=password_hash)

                return redirect(
                    url_for("auth.login", error="Password reset - please login.")
                )
    return render_template("auth/resetpassword.html.j2")


@blueprint.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            _register_new_user(current_app.config["DB_NAME"], request.form)
            return render_template("auth/register.html.j2", success=True)
        except MountainException as e:
            print(e)
            return render_template(
                "auth/register.html.j2", error=str(e), form=request.form
            )
    return render_template("auth/register.html.j2")


@blueprint.route("/logout", methods=["POST"])
def logout():
    del session["token_id"]
    return redirect(url_for("index"))


def _register_new_user(db_name: str, form: Mapping[str, str]):
    # Check the password matches and generate a hash
    if form["password"] != form["confirm_password"]:
        raise MountainException("Passwords do not match!")
    password_hash = generate_password_hash(form["password"])

    # Lock the DB so we can generate a new user ID and insert
    with db_conn(locked=True) as conn:
        user_db = users_repo(conn)
        if user_db.get(email=form["email"]) is not None:
            raise MountainException(
                f"The email {form['email']} has already been registered."
            )
        user = User.from_registration(
            id=user_db.next_id(),
            email=form["email"],
            password_hash=password_hash,
            first_name=form["first_name"],
            last_name=form["last_name"],
            about=form["about"],
        )
        logger.info("Registering new user %s...", user)
        user_db.insert(user)
