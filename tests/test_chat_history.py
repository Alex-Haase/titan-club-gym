from src.gym import chat_history
from langchain_core.messages import AIMessage, HumanMessage


class FakeDatabase:
    def __init__(self):
        self.history_table_exists = False
        self.messages = []

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self):
        return FakeCursor(self.database)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class FakeCursor:
    def __init__(self, database):
        self.database = database
        self.result = None

    def execute(self, sql, params=None):
        normalized_sql = " ".join(sql.lower().split())
        params = params or {}

        if "from user_tables" in normalized_sql:
            self.result = (int(self.database.history_table_exists),)
        elif normalized_sql.startswith("create table historial_chat"):
            self.database.history_table_exists = True
        elif normalized_sql.startswith("insert into historial_chat"):
            message_id = len(self.database.messages) + 1
            self.database.messages.append(
                (message_id, params["usuario_id"], params["rol"], params["contenido"])
            )
        elif "from historial_chat" in normalized_sql:
            messages = [
                row for row in self.database.messages if row[1] == params["usuario_id"]
            ]
            self.result = [
                (message_id, role, content)
                for message_id, _, role, content in messages[-params["limite"]:]
            ]

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


def test_saves_and_restores_chat_for_user(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(chat_history, "get_oracle_connection", database.connect)

    saved = chat_history.guardar_intercambio_chat(7, "¿Qué planes tienen?", "Tenemos Cobre, Plata y Oro.")
    loaded = chat_history.cargar_historial_chat(7)
    other_user = chat_history.cargar_historial_chat(8)

    assert saved["ok"] is True
    assert loaded["ok"] is True
    assert loaded["mensajes"] == [
        HumanMessage(content="¿Qué planes tienen?"),
        AIMessage(content="Tenemos Cobre, Plata y Oro."),
    ]
    assert other_user["mensajes"] == []