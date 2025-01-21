from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from flask import current_app, g

from mountains.db import connection

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


def current_user() -> User:
    return g.current_user
