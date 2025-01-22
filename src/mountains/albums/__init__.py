from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING

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

from mountains.context import db_conn
from mountains.models.photos import Album, Photo, albums_repo, photos_repo, upload_photo
from mountains.models.users import User, users_repo
from mountains.utils import str_to_bool

if TYPE_CHECKING:
    from sqlite3 import Connection

logger = logging.getLogger(__name__)

blueprint = Blueprint(
    "albums", __name__, template_folder="templates", static_folder="static"
)


@blueprint.route("/")
def albums():
    num_shown = request.args.get("num_shown", type=int, default=10)
    with db_conn() as conn:
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
        "albums/albums.html.j2",
        albums=albums,
        album_photos=album_photos,
        album_users=album_users,
        num_shown=num_shown,
    )


@blueprint.route("/add", methods=["GET", "POST"])
def add_album():
    if request.method == "POST":
        if event_date_str := request.form["event_date"]:
            event_date = datetime.date.fromisoformat(event_date_str)
        else:
            event_date = None

        with db_conn(locked=True) as conn:
            albums_db = albums_repo(conn)
            album = Album(
                id=albums_db.next_id(),
                name=request.form["name"],
                event_date=event_date,
            )
            albums_db.insert(album)
        return redirect(url_for(".albums"))
    else:
        return render_template("albums/album.add.html.j2")


@blueprint.route("/<int:id>", methods=["GET", "POST"])
def album(id: int):
    with db_conn() as conn:
        album = albums_repo(conn).get_or_404(id=id)

    if request.method == "POST":
        # Photo Upload
        for file in request.files.getlist("photos"):
            if file.filename:
                photo_path = upload_photo(
                    file, Path(current_app.config["STATIC_FOLDER"])
                )

                with db_conn(locked=True) as conn:
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
            response.headers["HX-Location"] = url_for(".album", id=id)
            return response

    with db_conn() as conn:
        photos = sorted(
            photos_repo(conn).list_where(album_id=album.id),
            key=lambda p: p.created_at_utc,
        )

        user_map: dict[int, User] = {}
        for photo in photos:
            if photo.uploader_id not in user_map:
                user = users_repo(conn).get(id=photo.uploader_id)
                if user is not None:
                    user_map[photo.uploader_id] = user

    return render_template(
        "albums/album.html.j2",
        album=album,
        photos=photos,
        user_map=user_map,
    )


@blueprint.route("/<int:album_id>/photos/<int:photo_id>", methods=["GET", "POST"])
def album_photo(album_id: int, photo_id: int):
    if request.method == "POST":
        starred = request.form.get("starred", type=str_to_bool, default=None)
        if starred is not None:
            with db_conn() as conn:
                photos_repo(conn).update(id=photo_id, starred=starred)

        return redirect(url_for(".album_photo", album_id=album_id, photo_id=photo_id))
    else:
        with db_conn() as conn:
            album = albums_repo(conn).get_or_404(id=album_id)
            photos = _get_sorted_photos(conn, album)

            try:
                photo_ix = [p.id for p in photos].index(photo_id)
            except ValueError:
                abort(404, "Photo not found.")

            photo = photos[photo_ix]

            prev_photo = None
            if photo_ix != 0:
                prev_photo = photos[photo_ix - 1]

            next_photo = None
            if (photo_ix + 1) != len(photos):
                next_photo = photos[photo_ix + 1]

        return render_template(
            "albums/album.photo.html.j2",
            album=album,
            prev_photo=prev_photo,
            photo=photo,
            next_photo=next_photo,
        )


def _get_sorted_photos(conn: Connection, album: Album) -> list[Photo]:
    return sorted(
        photos_repo(conn).list_where(album_id=album.id),
        key=lambda p: p.created_at_utc,
    )
