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
    redirect,
    render_template,
    request,
    url_for,
)

from mountains.context import current_user, db_conn
from mountains.models.kit import KitGroup, KitItem, kit_item_repo
from mountains.utils import str_to_bool

if TYPE_CHECKING:
    from sqlite3 import Connection

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
def add_kit():
    if request.method == "POST":
        current_user.check_authorised()
        with db_conn(locked=True) as conn:
            kit_db = kit_item_repo(conn)
            kit_item = KitItem(
                id=kit_db.next_id(),
                club_id=request.form["club_id"],
                description=request.form["description"],
                brand=request.form["brand"],
                color=request.form["color"],
                size=request.form["size"],
                kit_type=request.form["kit_type"],
                kit_group=KitGroup(request.form.get("kit_group", type=int)),
                purchased_on=datetime.date.fromisoformat(request.form["purchased_on"]),
                purchase_price=float(request.form["purchase_price"]),
            )
            logger.info("Adding new kit item %s", kit_item)
            kit_db.insert(kit_item)
        return redirect(url_for(".kit"))
    else:
        return render_template("kit/kit.add.html.j2", kit_groups=KitGroup)
