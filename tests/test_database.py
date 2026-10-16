import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from database import build_oracle_dsn, get_oracle_connection_params


def test_build_oracle_dsn_from_env(monkeypatch):
    monkeypatch.setenv("ORACLE_HOST", "localhost")
    monkeypatch.setenv("ORACLE_PORT", "1521")
    monkeypatch.setenv("ORACLE_SERVICE", "xe")

    assert build_oracle_dsn() == "localhost:1521/xe"


def test_get_oracle_connection_params_reads_env(monkeypatch):
    monkeypatch.setenv("ORACLE_USER", "GYM_ADMIN")
    monkeypatch.setenv("ORACLE_PASSWORD", "GIM_ADMIN1")
    monkeypatch.setenv("ORACLE_HOST", "localhost")
    monkeypatch.setenv("ORACLE_PORT", "1521")
    monkeypatch.setenv("ORACLE_SERVICE", "xe")

    params = get_oracle_connection_params()

    assert params["user"] == "GYM_ADMIN"
    assert params["password"] == "GIM_ADMIN1"
    assert params["dsn"] == "localhost:1521/xe"


def test_registrar_cliente_en_oracle(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def fetchone(self):
            return (0,)

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            pass

        def close(self):
            pass

    fake_conn = FakeConnection()

    def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(database, "get_oracle_connection", fake_connect)

    resultado = database.registrar_cliente("Ana Torres", "oro")

    assert resultado["ok"] is True
    assert resultado["nombre"] == "Ana Torres"
    assert resultado["plan"] == "oro"


def test_actualizar_plan_cliente_en_oracle(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = []

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            pass

        def close(self):
            pass

    fake_conn = FakeConnection()

    def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(database, "get_oracle_connection", fake_connect)

    resultado = database.actualizar_plan_cliente("Ana Torres", "oro")

    assert resultado["ok"] is True
    assert resultado["plan"] == "oro"


def test_registrar_pago_en_oracle(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.values = [(0,), (0,), (0,)]

        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return self.values.pop(0)

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            pass

        def close(self):
            pass

    fake_conn = FakeConnection()

    def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(database, "get_oracle_connection", fake_connect)

    resultado = database.registrar_pago("Ana Torres", "oro", 85000, "transferencia")

    assert resultado["ok"] is True
    assert resultado["monto"] == 85000.0
    assert resultado["metodo"] == "transferencia"


def test_registrar_flujo_completo_en_oracle(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = []
            self.lookup = {"count_clientes": 0, "count_planes": 0, "count_inscripciones": 0, "count_ventas": 0, "count_pagos": 0}

        def execute(self, sql, params=None):
            self.executed.append((sql, params))
            upper_sql = sql.upper()
            if "FROM USER_TABLES" in upper_sql and "CLIENTES" in upper_sql:
                self.lookup["count_clientes"] = 0
            elif "FROM USER_TABLES" in upper_sql and "PLANES" in upper_sql:
                self.lookup["count_planes"] = 0
            elif "FROM USER_TABLES" in upper_sql and "INSCRIPCIONES" in upper_sql:
                self.lookup["count_inscripciones"] = 0
            elif "FROM USER_TABLES" in upper_sql and "VENTAS" in upper_sql:
                self.lookup["count_ventas"] = 0
            elif "FROM USER_TABLES" in upper_sql and "PAGOS" in upper_sql:
                self.lookup["count_pagos"] = 0

        def fetchone(self):
            return (0,)

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            pass

        def close(self):
            pass

    fake_conn = FakeConnection()

    def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(database, "get_oracle_connection", fake_connect)

    resultado = database.registrar_flujo_completo("Ana Torres", "oro", 85000, "transferencia")

    assert resultado["ok"] is True
    assert resultado["cliente"] == "Ana Torres"
    assert resultado["plan"] == "oro"
    assert resultado["monto"] == 85000.0
    assert resultado["pago_registrado"] is False
    assert resultado["pago_pendiente"] is True
    statements = [sql.upper() for sql, _ in fake_conn.cursor_obj.executed]
    assert any("INSCRIPCIONES" in sql and "'PENDIENTE'" in sql for sql in statements)
    assert any("VENTAS" in sql and "'PENDIENTE'" in sql for sql in statements)
    assert any("PAGOS" in sql and "'PENDIENTE'" in sql for sql in statements)
    assert not any("UPDATE CLIENTES SET PLAN_ACTUAL" in sql for sql in statements)


def test_active_memberships_query_counts_same_day_starts(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(" ".join(sql.lower().split()))

        def fetchone(self):
            return (1,)

        def fetchall(self):
            return [(" Cobre ", 2), ("PLATA", 1), ("Oro", 1)]

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            pass

    fake_conn = FakeConnection()
    monkeypatch.setattr(database, "get_oracle_connection", lambda: fake_conn)

    memberships = database.obtener_membresias_activas_por_plan()

    assert memberships == {"cobre": 2, "plata": 1, "oro": 1}
    query = fake_conn.cursor_obj.statements[-1]
    assert "trunc(i.fecha_inscripcion) <= trunc(sysdate)" in query
    assert "row_number() over" in query


def test_current_plan_query_normalizes_same_day_start(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.statements = []

        def execute(self, sql, params=None):
            self.statements.append(" ".join(sql.lower().split()))

        def fetchone(self):
            return (1,) if len(self.statements) == 1 else ("ORO",)

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            pass

    fake_conn = FakeConnection()
    monkeypatch.setattr(database, "get_oracle_connection", lambda: fake_conn)

    current_plan = database.obtener_plan_vigente_cliente("Ana Torres")

    assert current_plan == "oro"
    assert "trunc(i.fecha_inscripcion) <= trunc(sysdate)" in fake_conn.cursor_obj.statements[-1]
