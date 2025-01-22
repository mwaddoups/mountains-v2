from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from flask import current_app, g
from werkzeug.local import LocalProxy

from mountains.db import connection
from mountains.email import send_mail_api

if TYPE_CHECKING:
    from sqlite3 import Connection
    from typing import Generator

    from mountains.models.users import User


@contextmanager
def db_conn(locked: bool = False) -> Generator[Connection, None, None]:
    """
    A helper method to save us typing.
    """
    with connection(current_app.config["DB_NAME"], locked=locked) as conn:
        yield conn


def get_current_user() -> User:
    return g.current_user


current_user: User = LocalProxy(get_current_user)  # type: ignore - technically LocalProxy[User] but this is more helpful


def send_mail(*, to: list[str], subject: str, msg_markdown: str) -> None:
    """
    Helper for sending mail in the app context
    """
    return send_mail_api(
        to=to,
        subject=subject,
        msg_markdown=msg_markdown,
        debug=current_app.debug,
        api_key=current_app.config["MAILGUN_API_KEY"],
    )
