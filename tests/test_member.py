from datetime import date, datetime, timedelta

from src.gym import member


class MemberCursor:
    def __init__(self, client_rows, subscriptions, payments):
        self.client_rows = client_rows
        self.subscriptions = subscriptions
        self.payments = payments
        self.result = None
        self.last_query = ""
        self.queries = []

    def execute(self, sql, params=None):
        self.last_query = " ".join(sql.lower().split())
        self.queries.append(self.last_query)
        if "select count(*) from user_tab_columns" in self.last_query:
            self.result = (1,)
        elif "from user_tables" in self.last_query:
            self.result = (1,)
        elif "select nullable from user_tab_columns" in self.last_query:
            self.result = ("Y",)
        elif self.last_query.startswith("select id, nombre, correo, telefono"):
            self.result = self.client_rows
        elif "from inscripciones i" in self.last_query:
            self.result = self.subscriptions
        elif "from pagos where cliente_id" in self.last_query:
            self.result = self.payments
        elif "from solicitudes_servicios" in self.last_query:
            self.result = []

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class MemberConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


def test_member_portal_returns_only_email_linked_profile(monkeypatch):
    today = date.today()
    cursor = MemberCursor(
        [(8, "Ana Torres", "ana@example.com", "123456", "Plata", today, 1)],
        [(31, "Plata", today, 30, "ACTIVA", 55000)],
        [(41, 55000, "transferencia", today, "PAGADO")],
    )
    monkeypatch.setattr(member, "get_oracle_connection", lambda: MemberConnection(cursor))

    result = member.obtener_portal_miembro(" ANA@example.com ")

    assert result["ok"] is True
    assert result["cliente"]["id"] == 8
    assert result["estado"] == "ACTIVA"
    assert result["membresia"]["plan"] == "Plata"
    assert result["pagos"][0]["estado"] == "PAGADO"
    assert any(
        "from pagos where cliente_id" in query and query.endswith("order by id desc")
        for query in cursor.queries
    )
    solicitudes_query = next(
        query for query in cursor.queries if "from solicitudes_servicios s" in query
    )
    assert "where s.cliente_id = :cliente_id" in solicitudes_query
    assert "select s.id, s.servicio" in solicitudes_query


def test_member_portal_handles_unlinked_account_without_exposing_other_clients(monkeypatch):
    cursor = MemberCursor([], [], [])
    monkeypatch.setattr(member, "get_oracle_connection", lambda: MemberConnection(cursor))

    result = member.obtener_portal_miembro("member@example.com")

    assert result == {
        "ok": True,
        "cliente": None,
        "membresia": None,
        "inscripciones": [],
        "pagos": [],
    }
    assert "where lower(correo) = :correo" in cursor.last_query


def test_member_portal_marks_expired_membership(monkeypatch):
    today = date.today()
    start_date = today - timedelta(days=40)
    cursor = MemberCursor(
        [(8, "Ana Torres", "ana@example.com", "", "Plata", start_date, 1)],
        [(31, "Plata", start_date, 30, "ACTIVA", 55000)],
        [],
    )
    monkeypatch.setattr(member, "get_oracle_connection", lambda: MemberConnection(cursor))

    result = member.obtener_portal_miembro("ana@example.com")

    assert result["estado"] == "VENCIDA"
    assert result["membresia"] is None


class QuotaCursor:
    def __init__(self, used=0):
        self.used = used
        self.params = None
        self.query = ""

    def execute(self, sql, params=None):
        self.query = " ".join(sql.lower().split())
        self.params = params or {}

    def fetchone(self):
        return (self.used,)


def test_membership_free_service_quotas():
    appointment = datetime(2026, 10, 21, 10, 0)

    assert member._servicio_incluido(
        QuotaCursor(), 10, "plata", "CLASE_GRUPAL", appointment
    ) is True
    assert member._servicio_incluido(
        QuotaCursor(used=1), 10, "plata", "EVALUACION_FISICA", appointment
    ) is False

    weekly_cursor = QuotaCursor()
    assert member._servicio_incluido(
        weekly_cursor, 12, "oro", "ENTRENADOR_PERSONAL", appointment
    ) is True
    assert weekly_cursor.params["inicio_periodo"] == datetime(2026, 10, 19)
    assert weekly_cursor.params["fin_periodo"] == datetime(2026, 10, 26)

    assert member._servicio_incluido(
        QuotaCursor(used=1), 12, "oro", "NUTRICIONISTA", appointment
    ) is False
    assert member._servicio_incluido(
        QuotaCursor(), 13, "cobre", "NUTRICIONISTA", appointment
    ) is False


class RequestOutput:
    def __init__(self):
        self.value = None

    def getvalue(self):
        return [self.value]


class RequestCursor:
    def __init__(self, free_service=False, duplicate=None):
        self.free_service = free_service
        self.duplicate = duplicate
        self.result = None
        self.calls = []
        self.next_id = 40

    def var(self, value_type):
        return RequestOutput()

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        params = params or {}
        self.calls.append((normalized_sql, params))
        if "from user_tables" in normalized_sql:
            self.result = (1,)
        elif normalized_sql.startswith("select id from clientes"):
            self.result = (8,)
        elif normalized_sql.startswith("select id, estado, incluida, monto, pago_id"):
            self.result = self.duplicate
        elif "select cliente_id, inscripcion_id, plan from" in normalized_sql:
            self.result = (8, 21, "plata" if self.free_service else "cobre")
        elif "select count(*) from solicitudes_servicios" in normalized_sql:
            self.result = (0,)
        elif normalized_sql.startswith("insert into ventas"):
            params["id"].value = 101
        elif normalized_sql.startswith("insert into pagos"):
            params["id"].value = 102
        elif normalized_sql.startswith("insert into solicitudes_servicios"):
            params["id"].value = 103
        self.next_id += 1

    def fetchone(self):
        return self.result


class RequestConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_extra_service_request_creates_pending_payment(monkeypatch):
    cursor = RequestCursor(free_service=False)
    connection = RequestConnection(cursor)
    monkeypatch.setattr(member, "get_oracle_connection", lambda: connection)

    result = member.solicitar_servicio_miembro(
        "ana@example.com",
        "NUTRICIONISTA",
        datetime.now() + timedelta(days=1),
        "Consulta inicial",
        "Quiero revisar mi plan alimenticio",
        "transferencia",
    )

    assert result == {
        "ok": True,
        "solicitud_id": 103,
        "incluida": False,
        "monto": 15000.0,
        "estado": "PENDIENTE_PAGO",
        "pago_id": 102,
    }
    assert connection.committed is True
    sale = next(call for call in cursor.calls if call[0].startswith("insert into ventas"))
    payment = next(call for call in cursor.calls if call[0].startswith("insert into pagos"))
    assert sale[1]["total"] == 15000.0
    assert payment[1]["monto"] == 15000.0


def test_included_service_request_has_no_charge(monkeypatch):
    cursor = RequestCursor(free_service=True)
    connection = RequestConnection(cursor)
    monkeypatch.setattr(member, "get_oracle_connection", lambda: connection)

    result = member.solicitar_servicio_miembro(
        "ana@example.com",
        "CLASE_GRUPAL",
        datetime.now() + timedelta(days=1),
        "Yoga",
    )

    assert result["ok"] is True
    assert result["incluida"] is True
    assert result["monto"] == 0.0
    assert result["estado"] == "SOLICITADA"
    assert not any(call[0].startswith("insert into pagos") for call in cursor.calls)


def test_duplicate_service_request_does_not_create_new_charge(monkeypatch):
    cursor = RequestCursor(duplicate=(77, "PENDIENTE_PAGO", 0, 15000, 99))
    connection = RequestConnection(cursor)
    monkeypatch.setattr(member, "get_oracle_connection", lambda: connection)

    result = member.solicitar_servicio_miembro(
        "ana@example.com",
        "NUTRICIONISTA",
        datetime.now() + timedelta(days=1),
        "Consulta",
        "",
        "transferencia",
    )

    assert result == {
        "ok": True,
        "duplicada": True,
        "solicitud_id": 77,
        "incluida": False,
        "monto": 15000.0,
        "estado": "PENDIENTE_PAGO",
        "pago_id": 99,
    }
    assert not any(call[0].startswith("insert into ventas") for call in cursor.calls)
    assert not any(call[0].startswith("insert into pagos") for call in cursor.calls)
    assert not any(call[0].startswith("insert into solicitudes_servicios") for call in cursor.calls)