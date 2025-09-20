from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.context import current_user, db_conn
from mountains.models.kit import (
    KitGroup,
    KitItem,
    KitRequest,
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
        kit_items = sorted(
            kit_item_repo(conn).list(), key=lambda a: (a.kit_group, a.club_id)
        )

    return render_template(
        "kit/kit.html.j2",
        kit_items=kit_items,
    )


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
def request_kit(id: int | None = None):
    method = req_method(request)

    with db_conn() as conn:
        kit_item = kit_item_repo(conn).get(id=id)
        if kit_item is None:
            abort(404)
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
