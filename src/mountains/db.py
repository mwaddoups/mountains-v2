import datetime
import sqlite3
import typing
from contextlib import contextmanager
from typing import Generator

import attrs
from attrs import define
from cattrs import (
    register_structure_hook,
    register_unstructure_hook,
    structure,
    unstructure,
)


@contextmanager
def connection(
    db_name: str, locked: bool = False
) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_name, autocommit=True)
    conn.execute("pragma journal_mode=wal")
    conn.row_factory = sqlite3.Row
    if locked:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    else:
        yield conn


@register_structure_hook
def structure_datetime(val, _) -> datetime.datetime:
    return datetime.datetime.fromisoformat(val)


@register_unstructure_hook
def unstructure_datetime(val: datetime.datetime) -> str:
    return val.isoformat()


@register_structure_hook
def structure_date(val, _) -> datetime.date:
    return datetime.date.fromisoformat(val)


@register_unstructure_hook
def unstructure_date(val: datetime.date) -> str:
    return val.isoformat()


@define
class Repository[T]:
    conn: sqlite3.Connection
    table_name: str
    schema: list[str]
    storage_cls: type[T]
    id_col: str = "id"

    @property
    def _field_names(self) -> list[str]:
        return [f.name for f in attrs.fields(self.storage_cls)]

    def next_id(self) -> int:
        cur = self.conn.execute(f"SELECT MAX({self.id_col}) + 1 FROM {self.table_name}")
        return cur.fetchone()[0]

    def create_table(self):
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} 
            ({",".join(self.schema)})
            WITHOUT ROWID
        """)

    def drop_table(self):
        self.conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")

    def insert(self, obj: T) -> None:
        self.conn.execute(
            f"""
            INSERT INTO {self.table_name} (
                {",".join(self._field_names)}
            ) VALUES (
                {",".join(":" + f for f in self._field_names)}
            )
        """,
            unstructure(obj),
        )

    def update(
        self, *, id: int | None = None, _where: dict | None = None, **kwargs
    ) -> T | None:
        updates = kwargs.copy()
        if _where is None:
            # Allow simpler call for standard id
            assert id is not None
            _where = {"id": id}

        self.conn.execute(
            f"""
            UPDATE {self.table_name}
            SET {",".join([f"{k} = :{k}" for k in kwargs])}
            WHERE {" AND ".join([f"{k} = :__{k}" for k in _where])}
            """,
            {**updates, **{f"__{k}": v for k, v in _where.items()}},
        )

    def get(self, **kwargs) -> T | None:
        cur = self.conn.execute(
            f"""
            SELECT {",".join(self._field_names)} FROM {self.table_name}
            WHERE {" AND ".join([f"{k} = :{k}" for k in kwargs])}
            LIMIT 1
            """,
            kwargs,
        )
        row = cur.fetchone()

        if row is None:
            return None
        else:
            return structure(dict(row), self.storage_cls)

    def list(self) -> list[T]:
        cur = self.conn.execute(f"""
            SELECT {",".join(self._field_names)} FROM {self.table_name}
        """)
        rows = cur.fetchall()

        return [structure(dict(row), self.storage_cls) for row in rows]

    def list_where(self, **kwargs) -> typing.List[T]:
        cur = self.conn.execute(
            f"""
            SELECT {",".join(self._field_names)} 
            FROM {self.table_name}
            WHERE {" AND ".join([f"{k} = :{k}" for k in kwargs])}
        """,
            kwargs,
        )
        rows = cur.fetchall()

        return [structure(dict(row), self.storage_cls) for row in rows]

    def delete_where(self, **kwargs):
        self.conn.execute(
            f"""
            DELETE FROM {self.table_name}
            WHERE {" AND ".join([f"{k} = :{k}" for k in kwargs])}
            """,
            kwargs,
        )
