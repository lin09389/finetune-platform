from __future__ import annotations

from contextlib import contextmanager
import sys
from types import SimpleNamespace

from rag.structured.db_connector import ConnectionConfig, MySQLConnector, PostgreSQLConnector


def test_postgres_dict_params_use_named_limit_placeholder(monkeypatch):
    connector = PostgreSQLConnector(ConnectionConfig(db_type="postgresql", database="demo"))
    captured: dict[str, object] = {}
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "psycopg2.extras", SimpleNamespace(RealDictCursor=object))

    class Cursor:
        description = []

        def execute(self, query, values=None):
            captured["sql"] = query
            captured["params"] = values

        def fetchall(self):
            return []

    class Conn:
        def cursor(self, cursor_factory=None):
            return Cursor()

    @contextmanager
    def fake_conn():
        yield Conn()

    connector._get_connection = fake_conn  # type: ignore[method-assign]
    connector.query("SELECT * FROM demo WHERE name = %(name)s", params={"name": "alice"}, limit=5)

    assert captured["sql"] == "SELECT * FROM demo WHERE name = %(name)s LIMIT %(_limit)s"
    assert captured["params"] == {"name": "alice", "_limit": 5}


def test_mysql_dict_params_use_named_limit_placeholder():
    connector = MySQLConnector(ConnectionConfig(db_type="mysql", database="demo"))
    captured: dict[str, object] = {}

    class Cursor:
        description = []

        def execute(self, query, values=None):
            captured["sql"] = query
            captured["params"] = values

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cursor()

    @contextmanager
    def fake_conn():
        yield Conn()

    connector._get_connection = fake_conn  # type: ignore[method-assign]
    connector.query("SELECT * FROM demo WHERE name = %(name)s", params={"name": "alice"}, limit=5)

    assert captured["sql"] == "SELECT * FROM demo WHERE name = %(name)s LIMIT %(_limit)s"
    assert captured["params"] == {"name": "alice", "_limit": 5}
