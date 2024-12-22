from cattrs import structure

from mountains.db import Repository
from mountains.models import User

users = Repository(
    db_name="test.db",
    table_name="users",
    schema=[
        "id TEXT PRIMARY KEY",
        "email TEXT UNIQUE NOT NULL",
        "first_name TEXT NOT NULL",
        "last_name TEXT NOT NULL",
        "about TEXT",
    ],
    storage_cls=User,
)

users.drop_table()
users.create_table()
users.insert(
    User(id="hello-me", email="x@y.com", first_name="Hello", last_name="me", about=None)
)
users.insert(
    User(id="hello-me", email="x@z.com", first_name="Hello", last_name="me", about=None)
)

print(users.get("hello-me"))
print(users.get("hello-you"))


print(users.list())
