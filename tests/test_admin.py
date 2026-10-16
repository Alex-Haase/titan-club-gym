from datetime import date, timedelta

from src.gym import admin


class FakeOutput:
    def __init__(self):
        self.value = None

    def setvalue(self, position, value):
        self.value = value

    def getvalue(self):
        return [self.value]


class FakeCursor:
    def __init__(self):
        self.result = None
        self.calls = []

    def var(self, value_type):
        return FakeOutput()

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        params = params or {}
        self.calls.append((normalized_sql, params))

        if normalized_sql.startswith("select id from clientes"):
            self.result = (12,)
        elif normalized_sql.startswith("select id, nombre, precio_clp"):
            self.result = (3, "Plata", 55000, 30)
        elif normalized_sql.startswith("select max(i.fecha_inscripcion"):
            self.result = (None,)
        elif normalized_sql.startswith("select cliente_id, venta_id from pagos"):
            self.result = (12, 201)
        elif normalized_sql.startswith("insert into inscripciones"):
            params["id"].setvalue(0, 101)
        elif normalized_sql.startswith("insert into ventas"):
            params["id"].setvalue(0, 201)

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
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


def test_membership_expiration_and_dashboard_metrics():
    today = date(2026, 10, 15)
    expiring_membership = {
        "id": 1,
        "plan": "Plata",
        "inicio": today - timedelta(days=23),
        "vencimiento": today + timedelta(days=6),
        "estado": "ACTIVA",
    }
    membership = admin._estado_membresia([expiring_membership], today)
    clients = [{"estado": membership["estado"], "fecha_vencimiento": membership["vencimiento"]}]
    payments = [{"estado": "PAGADO", "fecha": today, "monto": 55000.0}]

    metrics = admin.calcular_metricas_admin(clients, payments, today)

    assert membership["estado"] == "ACTIVA"
    assert metrics == {
        "clientes": 1,
        "membresias_activas": 1,
        "por_vencer": 1,
        "ingresos_mes": 55000.0,
    }


def test_registers_pending_renewal_without_claiming_payment(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.registrar_renovacion_admin(12, 3, "transferencia", "PENDIENTE")

    assert result["ok"] is True
    assert result["estado"] == "PENDIENTE"
    assert connection.committed is True
    inserts = [call for call in connection.cursor_obj.calls if call[0].startswith("insert into")]
    assert inserts[0][1]["estado"] == "PENDIENTE"
    assert inserts[1][1]["estado"] == "PENDIENTE"
    assert inserts[2][1]["estado"] == "PENDIENTE"
    assert not any(call[0].startswith("update clientes") for call in connection.cursor_obj.calls)


def test_monthly_revenue_uses_database_aggregate(monkeypatch):
    class RevenueCursor:
        def execute(self, sql):
            assert "SUM(monto)" in sql
            assert "estado = 'PAGADO'" in sql

        def fetchone(self):
            return (275000,)

    class RevenueConnection:
        def cursor(self):
            return RevenueCursor()

        def close(self):
            pass

    monkeypatch.setattr(admin, "get_oracle_connection", RevenueConnection)

    assert admin.obtener_ingresos_mes_admin() == 275000.0


def test_confirming_pending_payment_activates_membership(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.marcar_pago_pagado(44)

    assert result["ok"] is True
    assert connection.committed is True
    statements = [sql for sql, _ in connection.cursor_obj.calls]
    assert any(sql.startswith("update pagos set estado = 'pagado'") for sql in statements)
    assert any(sql.startswith("update inscripciones set estado = 'activa'") for sql in statements)


class CrudCursor:
    def __init__(self, results):
        self.results = results
        self.result = None
        self.calls = []

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        self.calls.append((normalized_sql, params or {}))
        for prefix, result in self.results:
            if normalized_sql.startswith(prefix):
                self.result = result
                return

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class CrudConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class ClientCrudCursor:
    def __init__(self, history_count=0, client_exists=True):
        self.history_count = history_count
        self.client_exists = client_exists
        self.result = None
        self.calls = []

    def var(self, value_type):
        return FakeOutput()

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        params = params or {}
        self.calls.append((normalized_sql, params))
        if "select count(*) from user_tab_columns" in normalized_sql:
            self.result = (1,)
        elif "select nullable from user_tab_columns" in normalized_sql:
            self.result = ("Y",)
        elif normalized_sql.startswith("select id from clientes"):
            self.result = (19,) if self.client_exists else None
        elif normalized_sql.startswith("select count(*) from inscripciones"):
            self.result = (self.history_count,)
        elif normalized_sql.startswith("select count(*) from ventas"):
            self.result = (0,)
        elif normalized_sql.startswith("select count(*) from pagos"):
            self.result = (0,)
        elif normalized_sql.startswith("insert into clientes"):
            params["id"].setvalue(0, 19)

    def fetchone(self):
        return self.result


def test_admin_can_create_client_without_membership(monkeypatch):
    cursor = ClientCrudCursor()
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.crear_cliente_admin("Ana Torres", " ANA@example.com ", "+56 9 1234 5678")

    assert result == {"ok": True, "cliente_id": 19}
    insert_call = next(call for call in cursor.calls if call[0].startswith("insert into clientes"))
    assert insert_call[1]["nombre"] == "Ana Torres"
    assert insert_call[1]["correo"] == "ana@example.com"
    assert insert_call[1]["telefono"] == "+56 9 1234 5678"
    assert connection.committed is True


def test_admin_can_update_client_identity_and_contact(monkeypatch):
    cursor = ClientCrudCursor()
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.actualizar_cliente_admin(19, "Ana Rojas", "ana.rojas@example.com", "+56 9 1111 2222")

    assert result["ok"] is True
    update_call = next(call for call in cursor.calls if call[0].startswith("update clientes set nombre"))
    assert update_call[1] == {
        "nombre": "Ana Rojas",
        "correo": "ana.rojas@example.com",
        "telefono": "+56 9 1111 2222",
        "cliente_id": 19,
    }
    assert connection.committed is True


def test_client_with_history_is_deactivated_not_deleted(monkeypatch):
    cursor = ClientCrudCursor(history_count=2)
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.eliminar_cliente_admin(19)

    assert result == {"ok": True, "accion": "desactivado"}
    assert any(call[0].startswith("update clientes set activo = 0") for call in cursor.calls)
    assert not any(call[0].startswith("delete from clientes") for call in cursor.calls)


def test_client_without_history_can_be_deleted(monkeypatch):
    cursor = ClientCrudCursor()
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.eliminar_cliente_admin(19)

    assert result == {"ok": True, "accion": "eliminado"}
    assert any(call[0].startswith("delete from clientes") for call in cursor.calls)


def test_user_crud_hashes_password_and_persists_role(monkeypatch):
    cursor = CrudCursor([
        ("select count(*) from user_tables", (1,)),
        ("select count(*) from user_tab_columns", (1,)),
        ("select id from usuarios where id", (7,)),
        ("select count(*) from usuarios", (0,)),
        ("select rol from usuarios", ("MIEMBRO",)),
    ])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.guardar_usuario_admin(
        7, "Alex Rojas", "alex@example.com", "ADMIN", "NuevaClave-2026", 1
    )

    assert result["ok"] is True
    update_call = next(call for call in cursor.calls if call[0].startswith("update usuarios"))
    assert update_call[1]["rol"] == "ADMIN"
    assert update_call[1]["password_hash"].startswith("pbkdf2_sha256$")
    assert "NuevaClave-2026" not in update_call[1]["password_hash"]
    assert connection.committed is True


def test_admin_can_create_a_user_with_initial_password(monkeypatch):
    cursor = CrudCursor([
        ("select count(*) from user_tables", (1,)),
        ("select count(*) from user_tab_columns", (1,)),
    ])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.guardar_usuario_admin(
        None, "Bea Soto", "bea@example.com", "MIEMBRO", "clave-inicial-2026", 1
    )

    assert result["ok"] is True
    insert_call = next(call for call in cursor.calls if call[0].startswith("insert into usuarios"))
    assert insert_call[1]["rol"] == "MIEMBRO"
    assert insert_call[1]["password_hash"].startswith("pbkdf2_sha256$")


def test_cannot_demote_last_admin(monkeypatch):
    cursor = CrudCursor([
        ("select count(*) from user_tables", (1,)),
        ("select count(*) from user_tab_columns", (1,)),
        ("select id from usuarios where id", (7,)),
        ("select count(*) from usuarios", (0,)),
        ("select rol from usuarios", ("ADMIN",)),
        ("select count(*) from usuarios where upper(rol)", (1,)),
    ])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.guardar_usuario_admin(7, "Owner", "owner@example.com", "MIEMBRO", "", 1)

    assert result["ok"] is False
    assert "al menos un administrador" in result["error"]
    assert connection.committed is False


def test_admin_can_delete_member_account(monkeypatch):
    cursor = CrudCursor([
        ("select count(*) from user_tables", (1,)),
        ("select count(*) from user_tab_columns", (1,)),
        ("select rol from usuarios", ("MIEMBRO",)),
    ])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.eliminar_usuario_admin(2, 1)

    assert result["ok"] is True
    assert any(call[0].startswith("delete from usuarios") for call in cursor.calls)
    assert connection.committed is True


def test_plan_duration_cannot_change_after_inscriptions(monkeypatch):
    cursor = CrudCursor([
        ("select duracion_dias from planes", (30,)),
        ("select count(*) from inscripciones", (4,)),
    ])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.guardar_plan_admin(3, "Plata Plus", 60000, 45, True)

    assert result["ok"] is False
    assert "duración" in result["error"]
    assert connection.committed is False


def test_admin_can_create_a_plan(monkeypatch):
    cursor = CrudCursor([])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.guardar_plan_admin(None, "Familiar", 99000, 30, True)

    assert result["ok"] is True
    insert_call = next(call for call in cursor.calls if call[0].startswith("insert into planes"))
    assert insert_call[1]["nombre"] == "Familiar"
    assert insert_call[1]["activo"] == 1
    assert connection.committed is True


def test_used_plan_is_deactivated_instead_of_deleted(monkeypatch):
    cursor = CrudCursor([
        ("select id from planes", (3,)),
        ("select count(*) from inscripciones", (2,)),
    ])
    connection = CrudConnection(cursor)
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.eliminar_plan_admin(3)

    assert result == {"ok": True, "accion": "desactivado"}
    assert any(call[0].startswith("update planes set activo = 0") for call in cursor.calls)
    assert not any(call[0].startswith("delete from planes") for call in cursor.calls)


def test_charts_include_recent_months_and_active_plans(monkeypatch):
    class ChartCursor:
        def __init__(self):
            self.statements = []
            self.results = [
                [(date.today().strftime("%Y-%m"), 300000)],
                [("Plata", 3)],
            ]

        def execute(self, sql, params=None):
            self.statements.append(" ".join(sql.lower().split()))

        def fetchall(self):
            return self.results.pop(0)

    connection = CrudConnection(ChartCursor())
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    charts = admin.obtener_datos_graficos_admin()

    assert len(charts["ingresos"]) == 6
    assert charts["ingresos"][-1]["ingresos"] == 300000.0
    assert charts["membresias_por_plan"] == [{"plan": "Plata", "membresias": 3}]
    assert "trunc(i.fecha_inscripcion) <= trunc(sysdate)" in connection.cursor_obj.statements[1]


class ServiceAdminCursor:
    def __init__(self, request):
        self.request = request
        self.result = None
        self.calls = []

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        self.calls.append((normalized_sql, params or {}))
        if "from user_tables" in normalized_sql:
            self.result = (1,)
        elif normalized_sql.startswith("select incluida, estado, pago_id, venta_id"):
            self.result = self.request

    def fetchone(self):
        return self.result


def test_admin_confirms_included_service_without_payment(monkeypatch):
    connection = CrudConnection(
        ServiceAdminCursor((1, "SOLICITADA", None, None))
    )
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.gestionar_solicitud_servicio_admin(8, "CONFIRMAR")

    assert result["ok"] is True
    assert any(
        sql.startswith("update solicitudes_servicios set estado = 'confirmada'")
        for sql, _ in connection.cursor_obj.calls
    )
    assert not any(sql.startswith("update pagos") for sql, _ in connection.cursor_obj.calls)


def test_admin_confirms_extra_service_payment_before_booking(monkeypatch):
    connection = CrudConnection(
        ServiceAdminCursor((0, "PENDIENTE_PAGO", 45, 35))
    )
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.gestionar_solicitud_servicio_admin(8, "CONFIRMAR_PAGO")

    assert result["ok"] is True
    statements = [sql for sql, _ in connection.cursor_obj.calls]
    assert any(sql.startswith("update pagos set estado = 'pagado'") for sql in statements)
    assert any(sql.startswith("update ventas set estado = 'confirmada'") for sql in statements)
    assert any("pago_estado = 'pagado'" in sql for sql in statements)


def test_admin_rejects_paid_service_and_cancels_pending_charge(monkeypatch):
    connection = CrudConnection(
        ServiceAdminCursor((0, "PENDIENTE_PAGO", 45, 35))
    )
    monkeypatch.setattr(admin, "get_oracle_connection", lambda: connection)

    result = admin.gestionar_solicitud_servicio_admin(8, "RECHAZAR")

    assert result["ok"] is True
    statements = [sql for sql, _ in connection.cursor_obj.calls]
    assert any(sql.startswith("update pagos set estado = 'cancelado'") for sql in statements)
    assert any(sql.startswith("update ventas set estado = 'cancelada'") for sql in statements)