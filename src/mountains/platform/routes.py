import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from mountains.db import connection
from mountains.photos import Album, Photo
from mountains.photos import albums as albums_repo
from mountains.photos import photos as photos_repo
from mountains.tokens import tokens as tokens_repo
from mountains.users import User
from mountains.users import users as users_repo

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
                token = tokens_repo(conn).get(id=token_id)
                if (
                    token is None
                    or (user := users_repo(conn).get(id=token.user_id)) is None
                ):
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
        num_shown = request.args.get("num_shown", type=int, default=10)
        with connection(current_app.config["DB_NAME"]) as conn:
            # TODO: Page / show all
            albums = sorted(
                albums_repo(conn).list(), key=lambda a: a.created_at_utc, reverse=True
            )[:num_shown]
            album_photos: dict[int, list[Photo]] = {}
            album_users: dict[int, list[User]] = {}
            user_map: dict[int, User] = {}
            for album in albums:
                album_photos[album.id] = photos_repo(conn).list_where(album_id=album.id)
                contributors: set[int] = set()
                for photo in album_photos[album.id]:
                    if photo.uploader_id not in user_map:
                        u = users_repo(conn).get(id=photo.uploader_id)
                        if u is not None:
                            user_map[photo.uploader_id] = u

                    if photo.uploader_id in user_map:
                        contributors.add(photo.uploader_id)
                album_users[album.id] = [user_map[u_id] for u_id in contributors]

        return render_template(
            "platform/photos.html.j2",
            albums=albums,
            album_photos=album_photos,
            album_users=album_users,
            num_shown=num_shown,
        )

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
