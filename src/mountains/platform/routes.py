import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    session,
    url_for,
)

from mountains.db import connection
from mountains.photos import albums as albums_repo
from mountains.photos import photos as photos_repo
from mountains.tokens import tokens
from mountains.users import users

from .events import event_routes
from .members import member_routes

logger = logging.getLogger(__name__)


def routes(blueprint: Blueprint):
    @blueprint.before_request
    def current_user():
        # Ensure all requests have access to the current user
        if (token_id := session.get("token_id")) is None:
            return redirect(url_for("auth.login"))
        else:
            with connection(current_app.config["DB_NAME"]) as conn:
                token = tokens(conn).get(id=token_id)
                if token is None or (user := users(conn).get(id=token.user_id)) is None:
                    # Something weird happened
                    del session["token_id"]
                    return redirect(url_for("index"))
                else:
                    g.current_user = user

    @blueprint.route("/home")
    def home():
        return render_template("platform/home.html.j2")

    @blueprint.route("/photos")
    def photos():
        with connection(current_app.config["DB_NAME"]) as conn:
            albums = sorted(
                albums_repo(conn).list(), key=lambda a: a.created_at_utc, reverse=True
            )
        return render_template("platform/photos.html.j2", albums=albums)

    @blueprint.route("/photos/<int:id>")
    def album(id: int):
        with connection(current_app.config["DB_NAME"]) as conn:
            album = albums_repo(conn).get(id=id)
            if album is None:
                abort(404)

            photos = photos_repo(conn).list_where(album_id=album.id)
        return render_template("platform/album.html.j2", album=album, photos=photos)

    member_routes(blueprint)

    event_routes(blueprint)
