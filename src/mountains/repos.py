from mountains.db import Repository
from mountains.models import User


def users(db_name: str) -> Repository[User]:
    return Repository(
        db_name=db_name,
        table_name="users",
        schema=[
            "id TEXT PRIMARY KEY",
            "email TEXT UNIQUE NOT NULL",
            "password_hash TEXT NOT NULL",
            "first_name TEXT NOT NULL",
            "last_name TEXT NOT NULL",
            "about TEXT",
        ],
        storage_cls=User,
    )
