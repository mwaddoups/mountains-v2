from __future__ import annotations

import datetime
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from werkzeug import Request


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None)


def readable_id(values: list[str]) -> str:
    return slugify(" ".join(v[:15].lower() for v in values))


def slugify(value: str) -> str:
    """
    Converts to lowercase, removes non-word characters (alphanumerics and
    underscores) and converts spaces to hyphens. Also strips leading and
    trailing whitespace.
    """
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def req_method(request: Request) -> str:
    if (
        "method" in request.form
        and request.method == "POST"
        and not request.headers.get("HX-Request")
    ):
        # Use the hidden METHOD form field to set the request
        return request.form["method"]
    else:
        return request.method


def str_to_bool(val: str) -> bool:
    if val in ("True", "true"):
        return True
    elif val in ("False", "false"):
        return False
    else:
        raise ValueError(f"Could not interpret string {val:!r} as bool")
