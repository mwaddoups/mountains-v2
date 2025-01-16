import datetime
import logging
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.db import connection
from mountains.photos import Album, Photo, upload_photo
from mountains.photos import albums as albums_repo
from mountains.photos import photos as photos_repo
from mountains.users import User
from mountains.users import users as users_repo
from mountains.utils import req_method, str_to_bool

logger = logging.getLogger(__name__)


def photo_routes(blueprint: Blueprint):
    @blueprint.route("/photos")
    def albums():
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
            "platform/albums.html.j2",
            albums=albums,
            album_photos=album_photos,
            album_users=album_users,
            num_shown=num_shown,
        )

    @blueprint.route("/photos/add", methods=["GET", "POST"])
    def add_album():
        if request.method == "POST":
            if event_date_str := request.form["event_date"]:
                event_date = datetime.date.fromisoformat(event_date_str)
            else:
                event_date = None

            with connection(current_app.config["DB_NAME"], locked=True) as conn:
                albums_db = albums_repo(conn)
                album = Album(
                    id=albums_db.next_id(),
                    name=request.form["name"],
                    event_date=event_date,
                )
                albums_db.insert(album)
            return redirect(url_for("platform.albums"))
        else:
            return render_template("platform/album.add.html.j2")

    @blueprint.route(
        "/photos/<int:id>/<int:highlighted_id>", methods=["GET", "POST", "PUT"]
    )
    @blueprint.route("/photos/<int:id>", methods=["GET", "POST", "PUT"])
    def album(id: int, highlighted_id: int | None = None):
        with connection(current_app.config["DB_NAME"]) as conn:
            album = albums_repo(conn).get(id=id)
            if album is None:
                abort(404)

        if req_method(request) == "POST" and highlighted_id is None:
            for file in request.files.getlist("photos"):
                if file.filename:
                    photo_path = upload_photo(
                        file, Path(current_app.config["STATIC_FOLDER"])
                    )

                    with connection(current_app.config["DB_NAME"], locked=True) as conn:
                        photos_db = photos_repo(conn)
                        photo = Photo(
                            id=photos_db.next_id(),
                            uploader_id=g.current_user.id,
                            album_id=id,
                            starred=False,
                            photo_path=photo_path,
                        )
                        photos_db.insert(photo)

            if request.headers.get("HX-Request"):
                response = make_response()
                response.headers["HX-Location"] = url_for(
                    ".album", id=id, highlighted_id=highlighted_id
                )
                return response
        elif req_method(request) == "PUT" and highlighted_id is not None:
            starred = request.form.get("starred", type=str_to_bool, default=None)
            if starred is not None:
                with connection(current_app.config["DB_NAME"]) as conn:
                    photos_repo(conn).update(id=highlighted_id, starred=starred)

        with connection(current_app.config["DB_NAME"]) as conn:
            photos = sorted(
                photos_repo(conn).list_where(album_id=album.id),
                key=lambda p: p.created_at_utc,
            )

            if highlighted_id:
                highlighted_ix = [p.id for p in photos].index(highlighted_id)
            else:
                highlighted_ix = None

            user_map: dict[int, User] = {}
            for photo in photos:
                if photo.uploader_id not in user_map:
                    user = users_repo(conn).get(id=photo.uploader_id)
                    if user is not None:
                        user_map[photo.uploader_id] = user

        if request.headers.get("HX-Target") == "highlighted":
            if highlighted_id is not None:
                return render_template(
                    "platform/album._highlighted.html.j2",
                    album=album,
                    photos=photos,
                    user_map=user_map,
                    highlighted_ix=highlighted_ix,
                )
            else:
                # Empty response is fine, the dialog gets closed by htmx
                return ""
        else:
            return render_template(
                "platform/album.html.j2",
                album=album,
                photos=photos,
                user_map=user_map,
                highlighted_ix=highlighted_ix,
            )
