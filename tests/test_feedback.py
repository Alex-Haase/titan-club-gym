from src.gym import feedback


class FeedbackCursor:
    def __init__(self, table_exists=True):
        self.table_exists = table_exists
        self.result = None
        self.calls = []

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        self.calls.append((normalized_sql, params or {}))
        if "from user_tables" in normalized_sql:
            self.result = (int(self.table_exists),)
        elif normalized_sql.startswith("select * from ("):
            self.result = [(5, "Ana", "ana@example.com", "Mejorar horarios", "NUEVA", None)]

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class FeedbackConnection:
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


def test_feedback_validates_and_persists_suggestion(monkeypatch):
    cursor = FeedbackCursor(table_exists=False)
    connection = FeedbackConnection(cursor)
    monkeypatch.setattr(feedback, "get_oracle_connection", lambda: connection)

    result = feedback.enviar_sugerencia("Ana", " ANA@example.com ", "Más clases de yoga")

    assert result["ok"] is True
    assert any(call[0].startswith("create table sugerencias") for call in cursor.calls)
    insert = next(call for call in cursor.calls if call[0].startswith("insert into sugerencias"))
    assert insert[1] == {
        "nombre": "Ana",
        "correo": "ana@example.com",
        "mensaje": "Más clases de yoga",
    }
    assert connection.committed is True


def test_feedback_rejects_invalid_email_and_empty_message(monkeypatch):
    def unexpected_connection():
        raise AssertionError("Invalid suggestions should not reach Oracle")

    monkeypatch.setattr(feedback, "get_oracle_connection", unexpected_connection)

    assert feedback.enviar_sugerencia("Ana", "correo-invalido", "Sugerencia")["ok"] is False
    assert feedback.enviar_sugerencia("Ana", "ana@example.com", " ")["ok"] is False


def test_admin_lists_and_updates_feedback_status(monkeypatch):
    cursor = FeedbackCursor()
    connection = FeedbackConnection(cursor)
    monkeypatch.setattr(feedback, "get_oracle_connection", lambda: connection)

    suggestions = feedback.listar_sugerencias_admin()
    updated = feedback.cambiar_estado_sugerencia_admin(5, "REVISADA")

    assert suggestions[0]["mensaje"] == "Mejorar horarios"
    assert updated["ok"] is True
    assert any(
        call[0].startswith("update sugerencias set estado")
        and call[1]["estado"] == "REVISADA"
        for call in cursor.calls
    )