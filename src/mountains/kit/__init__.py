from __future__ import annotations

import logging
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from PIL import Image, ImageOps
from werkzeug.datastructures import FileStorage

from mountains.context import current_user, db_conn
from mountains.models.kit import (
    KitDetail,
    KitGroup,
    KitItem,
    KitRequest,
    kit_details_repo,
    kit_item_repo,
    kit_request_repo,
)
from mountains.models.users import users_repo
from mountains.utils import req_method

logger = logging.getLogger(__name__)

blueprint = Blueprint(
    "kit", __name__, template_folder="templates", static_folder="static"
)


@blueprint.route("/")
def kit():
    with db_conn() as conn:
        # Sort ensuring B2 < B10 by length first
        kit_items = sorted(
            kit_item_repo(conn).list(),
            key=lambda a: (a.kit_group, len(a.club_id), a.club_id),
        )
        kit_requests = kit_request_repo(conn).list()

    search = request.args.get("search")
    if search:
        kit_items = [k for k in kit_items if search.lower() in k.description.lower()]

    kit_status = {}
    for req in kit_requests:
        if req.is_active():
            kit_status[req.kit_id] = "Out"
        elif req.is_in_future():
            kit_status[req.kit_id] = "Requested"
    for kit in kit_items:
        if kit.id not in kit_status:
            kit_status[kit.id] = "Available"

    return render_template(
        "kit/kit.html.j2",
        kit_items=kit_items,
        kit_status=kit_status,
        search=search,
    )


@blueprint.route("/<int:id>/detail", methods=["GET", "POST"])
def kit_details(id: int):
    with db_conn() as conn:
        kit_item = kit_item_repo(conn).get(id=id)
        if kit_item is None:
            abort(404)
        assert kit_item is not None

        kit_details = kit_details_repo(conn).list_where(kit_id=id)

        # Get all users present in notes
        user_map = {
            u.id: u
            for u in users_repo(conn).get_all(id=[k.user_id for k in kit_details])
        }

    if request.method == "POST":
        current_user.check_authorised()
        with db_conn(locked=True) as conn:
            kit_detail_db = kit_details_repo(conn)
            pic = request.files["photo_path"]
            next_id = kit_detail_db.next_id()
            if pic.filename:
                photo_path = _upload_kit_image(
                    filename=f"{next_id}-kit-detail",
                    file=pic,
                    static_dir=Path(current_app.config["STATIC_FOLDER"]),
                )
            else:
                photo_path = None

            kit_detail = KitDetail.from_form(
                id=kit_detail_db.next_id(),
                user_id=current_user.id,
                kit_id=kit_item.id,
                photo_path=photo_path,
                form=request.form,
            )
            logger.info("Adding new kit detail: %s", kit_detail)
            kit_detail_db.insert(kit_detail)

        return redirect(url_for(".kit_details", id=id))

    photos = sorted(
        [k for k in kit_details if k.photo_path is not None], key=lambda k: k.added_dt
    )
    if len(photos) > 0:
        latest_photo_note = photos[-1]
    else:
        latest_photo_note = None

    return render_template(
        "kit/kit.detail.html.j2",
        kit_groups=KitGroup,
        kit_item=kit_item,
        kit_details=kit_details,
        latest_photo_note=latest_photo_note,
        user_map=user_map,
    )


def _upload_kit_image(
    filename: str,
    file: FileStorage,
    static_dir: Path,
) -> str:
    assert file.filename is not None, (
        "upload_profile should always have a file.filename attribute"
    )
    full_filename = Path(filename).with_suffix(Path(file.filename).suffix)
    upload_path = static_dir / "kit-photos" / full_filename
    if not upload_path.parent.exists():
        upload_path.parent.mkdir()
    file.save(upload_path)

    for new_width in [256, 512, 1200]:
        with Image.open(upload_path) as im:
            if im.width > new_width:
                new_height = int(im.height * (new_width / im.width))
                resized = im.resize((new_width, new_height))
                try:
                    ImageOps.exif_transpose(resized, in_place=True)
                except Exception as e:
                    logger.exception(
                        "Exception while transposing newly uploaded kit image.",
                        exc_info=e,
                    )
                target_path = upload_path.with_stem(f"{upload_path.stem}-{new_width}")

                logger.info("Saving image to %s", target_path)
                resized.save(target_path)

    return str(Path("kit-photos") / full_filename)


@blueprint.route("/add/", methods=["GET", "POST"])
@blueprint.route("/<int:id>/edit/", methods=["GET", "POST", "PUT"])
def add_kit(id: int | None = None):
    current_user.check_authorised()
    method = req_method(request)

    if id is not None:
        with db_conn() as conn:
            kit_item = kit_item_repo(conn).get(id=id)
        if kit_item is None:
            abort(404)
    else:
        kit_item = None

    if method != "GET":
        with db_conn(locked=True) as conn:
            kit_db = kit_item_repo(conn)
            if method == "POST" and kit_item is None:
                kit_item = KitItem.from_form(id=kit_db.next_id(), form=request.form)
                logger.info("Adding new kit item %s", kit_item)
                kit_db.insert(kit_item)
            elif method == "PUT" and kit_item is not None:
                kit_item = KitItem.from_form(id=kit_item.id, form=request.form)
                kit_db.delete_where(id=kit_item.id)
                kit_db.insert(kit_item)
            else:
                abort(405)

        return redirect(url_for(".kit"))
    else:
        return render_template(
            "kit/kit.add.html.j2", kit_groups=KitGroup, kit_item=kit_item
        )


@blueprint.route("/<int:id>/request/", methods=["GET", "POST", "DELETE"])
def request_kit(id: int):
    method = req_method(request)

    with db_conn() as conn:
        kit_item = kit_item_repo(conn).get(id=id)
        if kit_item is None:
            abort(404)
        assert kit_item is not None

        current_kit_requests = kit_request_repo(conn).list_where(kit_id=kit_item.id)
        users_db = users_repo(conn)
        current_kit_users = {}
        for kit_request in current_kit_requests:
            request_user = users_db.get(id=kit_request.user_id)
            if request_user is not None:
                current_kit_users[kit_request.user_id] = request_user

    if method == "POST":
        with db_conn(locked=True) as conn:
            req_db = kit_request_repo(conn)
            kit_request = KitRequest.from_form(
                id=req_db.next_id(),
                kit_id=kit_item.id,
                user_id=current_user.id,
                form=request.form,
            )
            logger.info("Adding new kit request %s", kit_request)
            req_db.insert(kit_request)

        return redirect(url_for(".kit"))
    else:
        return render_template(
            "kit/kit.request.html.j2",
            kit_item=kit_item,
            current_requests=current_kit_requests,
            current_request_users=current_kit_users,
        )


@blueprint.route("/requests")
def requests():
    with db_conn() as conn:
        kit_requests = kit_request_repo(conn).list()
        kit_requests = sorted(
            [k for k in kit_requests if k.is_active() or k.is_in_future()],
            key=lambda k: k.pickup_dt,
        )

        kit_item_map = {
            k.id: k
            for k in kit_item_repo(conn).get_all(id=[r.kit_id for r in kit_requests])
        }
        user_map = {
            u.id: u
            for u in users_repo(conn).get_all(id=[r.user_id for r in kit_requests])
        }

    return render_template(
        "kit/requests.html.j2",
        kit_requests=kit_requests,
        kit_item_map=kit_item_map,
        user_map=user_map,
    )


@blueprint.route("/requests/<int:id>", methods=["POST", "PATCH", "DELETE"])
def update_request(id: int):
    method = req_method(request)

    with db_conn() as conn:
        kit_request = kit_request_repo(conn).get(id=id)
        if kit_request is None:
            abort(404)
        assert kit_request is not None

    current_user.check_authorised(kit_request.user_id)

    if method == "PATCH":
        print(request.form, kit_request)
        with db_conn(locked=True) as conn:
            req_db = kit_request_repo(conn)

            if "is_approved" in request.form:
                req_db.update(id=id, is_approved=True)

            # TODO: EMAIL

        return redirect(url_for(".requests"))
    elif method == "DELETE":
        # TODO: EMAIL?
        with db_conn(locked=True) as conn:
            req_db = kit_request_repo(conn)
            req_db.delete_where(id=id)
        return redirect(url_for(".requests"))
    else:
        abort(403)
