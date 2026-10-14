from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import Connection


@contextmanager
def connect(database_url: str) -> Iterator[Connection]:
    with psycopg.connect(database_url) as connection:
        yield connection


def initialize_database(connection: Connection) -> None:
    sql_dir = Path(__file__).resolve().parents[2] / "sql"
    for sql_path in sorted(sql_dir.glob("*.sql")):
        connection.execute(sql_path.read_text(encoding="utf-8"))
    connection.commit()

