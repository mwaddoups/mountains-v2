import sqlite3
from contextlib import contextmanager
from typing import Generator

import attrs
from attrs import define
from cattrs import structure


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


@define
class Repository[T]:
    db_name: str
    table_name: str
    schema: list[str]
    storage_cls: type[T]
    id_col: str = "id"

    @property
    def _field_names(self) -> list[str]:
        return [f.name for f in attrs.fields(self.storage_cls)]

    def create_table(self):
        with connection(self.db_name) as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} 
                ({",".join(self.schema)})
                WITHOUT ROWID
            """)

    def drop_table(self):
        with connection(self.db_name) as conn:
            conn.execute(f"DROP TABLE {self.table_name}")

    def insert(self, obj: T) -> None:
        with connection(self.db_name) as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table_name} (
                    {",".join(self._field_names)}
                ) VALUES (
                    {",".join(":" + f for f in self._field_names)}
                )
            """,
                attrs.asdict(obj),
            )

    def get(self, **kwargs) -> T | None:
        with connection(self.db_name) as conn:
            cur = conn.execute(
                f"""
                SELECT {",".join(self._field_names)} FROM {self.table_name}
                WHERE {",".join([f"{k} = :{k}" for k in kwargs])}
                LIMIT 1
                """,
                kwargs,
            )
            row = cur.fetchone()

        if row is None:
            return None
        else:
            return structure(row, self.storage_cls)

    def list(self) -> list[T]:
        with connection(self.db_name) as conn:
            cur = conn.execute(f"""
                SELECT {",".join(self._field_names)} FROM {self.table_name}
            """)
            rows = cur.fetchall()

        return [structure(row, self.storage_cls) for row in rows]
