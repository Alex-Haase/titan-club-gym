from src.gym import auth


class FakeDatabase:
    def __init__(self):
        self.users = {}

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
            self.result = (1,)
        elif "select count(*) from usuarios" in normalized_sql:
            self.result = (int(params["correo"] in self.database.users),)
        elif normalized_sql.startswith("insert into usuarios"):
            user_id = len(self.database.users) + 1
            self.database.users[params["correo"]] = (
                user_id,
                params["nombre"],
                params["correo"],
                params["password_hash"],
                params["rol"],
            )
        elif normalized_sql.startswith("select id from usuarios"):
            user = self.database.users.get(params["correo"])
            self.result = (user[0],) if user else None
        elif normalized_sql.startswith("select id, nombre, correo, password_hash"):
            self.result = self.database.users.get(params["correo"])

    def fetchone(self):
        return self.result


def test_register_and_login_user_with_hashed_password(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(auth, "get_oracle_connection", database.connect)

    registered = auth.registrar_usuario("Ana Torres", " ANA@EXAMPLE.COM ", "clave-segura-123")

    assert registered["ok"] is True
    assert registered["usuario"]["id"] == 1
    assert registered["usuario"]["correo"] == "ana@example.com"
    stored_user = database.users["ana@example.com"]
    assert stored_user[3] != "clave-segura-123"

    login = auth.iniciar_sesion("ana@example.com", "clave-segura-123")
    invalid_login = auth.iniciar_sesion("ana@example.com", "incorrecta")

    assert login == {
        "ok": True,
        "usuario": {
            "id": 1,
            "nombre": "Ana Torres",
            "correo": "ana@example.com",
            "rol": "MIEMBRO",
        },
    }
    assert invalid_login["ok"] is False


def test_admin_role_comes_from_email_allowlist(monkeypatch):
    monkeypatch.setenv("GYM_ADMIN_EMAILS", "owner@example.com, second@example.com")

    assert auth._rol_para_correo("owner@example.com") == "ADMIN"
    assert auth._rol_para_correo("other@example.com") == "MIEMBRO"


def test_login_uses_persisted_role_after_allowlist_is_removed(monkeypatch):
    database = FakeDatabase()
    database.users["owner@example.com"] = (
        1,
        "Owner",
        "owner@example.com",
        auth._hash_password("clave-segura-123"),
        "ADMIN",
    )
    monkeypatch.setattr(auth, "get_oracle_connection", database.connect)
    monkeypatch.delenv("GYM_ADMIN_EMAILS", raising=False)

    result = auth.iniciar_sesion("owner@example.com", "clave-segura-123")

    assert result["ok"] is True
    assert result["usuario"]["rol"] == "ADMIN"


def test_registration_rejects_duplicate_and_short_password(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(auth, "get_oracle_connection", database.connect)

    assert auth.registrar_usuario("Ana", "ana@example.com", "corta")["ok"] is False
    assert auth.registrar_usuario("Ana", "ana@example.com", "clave-segura-123")["ok"] is True
    duplicate = auth.registrar_usuario("Ana", "ANA@example.com", "clave-segura-123")

    assert duplicate["ok"] is False
    assert duplicate["error"] == "Ya existe una cuenta con ese correo."