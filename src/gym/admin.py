from datetime import date, datetime, time, timedelta

from .auth import EMAIL_PATTERN, _ensure_users_table, _hash_password
from .database import get_oracle_connection

ESTADOS_PAGO = {"PENDIENTE", "PAGADO"}


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _id_generado(variable) -> int:
    valor = variable.getvalue()
    if isinstance(valor, (list, tuple)):
        if not valor:
            raise ValueError("Oracle no devolvió el ID generado.")
        valor = valor[0]
    if valor is None:
        raise ValueError("Oracle no devolvió el ID generado.")
    return int(valor)


def _estado_membresia(inscripciones: list[dict], hoy: date) -> dict:
    activas = [
        membresia
        for membresia in inscripciones
        if membresia["estado"] in {"ACTIVA", "RENOVADA"}
        and membresia["inicio"] <= hoy <= membresia["vencimiento"]
    ]
    if activas:
        elegida = max(activas, key=lambda item: item["id"])
        return {"plan": elegida["plan"], "estado": "ACTIVA", "vencimiento": elegida["vencimiento"]}

    pendientes = [item for item in inscripciones if item["estado"] == "PENDIENTE"]
    if pendientes:
        elegida = max(pendientes, key=lambda item: item["id"])
        return {"plan": elegida["plan"], "estado": "PENDIENTE", "vencimiento": elegida["vencimiento"]}

    programadas = [
        item for item in inscripciones
        if item["estado"] in {"ACTIVA", "RENOVADA"} and item["inicio"] > hoy
    ]
    if programadas:
        elegida = min(programadas, key=lambda item: item["inicio"])
        return {"plan": elegida["plan"], "estado": "PROGRAMADA", "vencimiento": elegida["vencimiento"]}

    vencidas = [item for item in inscripciones if item["estado"] in {"ACTIVA", "RENOVADA"}]
    if vencidas:
        elegida = max(vencidas, key=lambda item: item["id"])
        return {"plan": elegida["plan"], "estado": "VENCIDA", "vencimiento": elegida["vencimiento"]}

    return {"plan": None, "estado": "SIN MEMBRESIA", "vencimiento": None}


def _asegurar_columnas_clientes(cursor) -> None:
    for nombre_columna, tipo in (
        ("CORREO", "VARCHAR2(320)"),
        ("TELEFONO", "VARCHAR2(40)"),
        ("ACTIVO", "NUMBER(1) DEFAULT 1 NOT NULL"),
    ):
        cursor.execute("""
            SELECT COUNT(*) FROM user_tab_columns
            WHERE table_name = 'CLIENTES' AND column_name = :columna
        """, {"columna": nombre_columna})
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"ALTER TABLE clientes ADD ({nombre_columna.lower()} {tipo})")

    cursor.execute("""
        SELECT nullable FROM user_tab_columns
        WHERE table_name = 'CLIENTES' AND column_name = 'PLAN_ACTUAL'
    """)
    columna_plan = cursor.fetchone()
    if columna_plan and columna_plan[0] == "N":
        cursor.execute("ALTER TABLE clientes MODIFY (plan_actual NULL)")


def _sincronizar_planes_actuales(cursor) -> None:
    cursor.execute("""
        MERGE INTO clientes c
        USING (
            SELECT cliente_id, plan FROM (
                SELECT i.cliente_id,
                       LOWER(p.nombre) AS plan,
                       ROW_NUMBER() OVER (
                           PARTITION BY i.cliente_id
                           ORDER BY i.fecha_inscripcion DESC, i.id DESC
                       ) AS rn
                FROM inscripciones i
                JOIN planes p ON p.id = i.plan_id
                JOIN clientes c ON c.id = i.cliente_id
                WHERE NVL(c.activo, 1) = 1
                  AND UPPER(i.estado) IN ('ACTIVA', 'RENOVADA')
                  AND TRUNC(i.fecha_inscripcion) <= TRUNC(SYSDATE)
                  AND TRUNC(SYSDATE) <
                      TRUNC(i.fecha_inscripcion) + NVL(p.duracion_dias, 30)
            ) WHERE rn = 1
        ) vigente ON (c.id = vigente.cliente_id)
        WHEN MATCHED THEN UPDATE SET c.plan_actual = vigente.plan
        WHERE NVL(LOWER(c.plan_actual), ' ') <> vigente.plan
    """)


def listar_clientes_admin(
    busqueda: str = "", incluir_inactivos: bool = False
) -> list[dict]:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        _asegurar_columnas_clientes(cursor)
        _sincronizar_planes_actuales(cursor)
        conn.commit()
        consulta = """
            SELECT c.id, c.nombre, c.plan_actual, c.fecha_registro,
                   c.correo, c.telefono, c.activo,
                   i.id, p.nombre, i.fecha_inscripcion,
                   NVL(p.duracion_dias, 30), i.estado
            FROM clientes c
            LEFT JOIN inscripciones i ON i.cliente_id = c.id
            LEFT JOIN planes p ON p.id = i.plan_id
        """
        parametros = {}
        filtros = []
        if not incluir_inactivos:
            filtros.append("NVL(c.activo, 1) = 1")
        if busqueda.strip():
            filtros.append("LOWER(c.nombre) LIKE :patron")
            parametros["patron"] = f"%{busqueda.strip().lower()}%"
        if filtros:
            consulta += " WHERE " + " AND ".join(filtros)
        consulta += " ORDER BY c.id, i.id DESC"
        cursor.execute(consulta, parametros)

        clientes = {}
        hoy = date.today()
        for row in cursor.fetchall():
            cliente_id, nombre, plan_actual, registro, correo, telefono, activo = row[:7]
            cliente = clientes.setdefault(cliente_id, {
                "id": cliente_id,
                "nombre": nombre,
                "plan": plan_actual,
                "fecha_registro": _as_date(registro),
                "correo": correo or "",
                "telefono": telefono or "",
                "activo": bool(activo),
                "estado": "SIN MEMBRESIA",
                "fecha_vencimiento": None,
                "_inscripciones": [],
            })
            inscripcion_id, plan, inicio, duracion, estado = row[7:]
            inicio = _as_date(inicio)
            if inscripcion_id is not None and inicio is not None:
                cliente["_inscripciones"].append({
                    "id": inscripcion_id,
                    "plan": plan or plan_actual,
                    "inicio": inicio,
                    "vencimiento": inicio + timedelta(days=int(duracion or 30) - 1),
                    "estado": (estado or "ACTIVA").upper(),
                })

        resultado = []
        for cliente in clientes.values():
            membresia = _estado_membresia(cliente.pop("_inscripciones"), hoy)
            cliente.update({
                "plan": membresia["plan"] or cliente["plan"],
                "estado": membresia["estado"] if cliente["activo"] else "BAJA",
                "fecha_vencimiento": membresia["vencimiento"],
            })
            resultado.append(cliente)
        return resultado
    finally:
        conn.close()


def crear_cliente_admin(nombre: str, correo: str = "", telefono: str = "") -> dict:
    nombre_limpio = (nombre or "").strip()
    correo_limpio = (correo or "").strip().lower()
    telefono_limpio = (telefono or "").strip()
    if not nombre_limpio:
        return {"ok": False, "error": "Ingresa el nombre del cliente."}
    if correo_limpio and not EMAIL_PATTERN.fullmatch(correo_limpio):
        return {"ok": False, "error": "Ingresa un correo válido."}
    if len(telefono_limpio) > 40:
        return {"ok": False, "error": "El teléfono no puede superar 40 caracteres."}

    conn = None
    try:
        import oracledb

        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_columnas_clientes(cursor)
        cliente_id_var = cursor.var(oracledb.DB_TYPE_NUMBER)
        cursor.execute("""
            INSERT INTO clientes (nombre, plan_actual, fecha_registro, correo, telefono, activo)
            VALUES (:nombre, NULL, SYSDATE, :correo, :telefono, 1)
            RETURNING id INTO :id
        """, {
            "nombre": nombre_limpio,
            "correo": correo_limpio or None,
            "telefono": telefono_limpio or None,
            "id": cliente_id_var,
        })
        cliente_id = _id_generado(cliente_id_var)
        conn.commit()
        return {"ok": True, "cliente_id": cliente_id}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo crear el cliente en Oracle."}
    finally:
        if conn is not None:
            conn.close()


def actualizar_cliente_admin(
    cliente_id: int, nombre: str, correo: str = "", telefono: str = ""
) -> dict:
    nombre_limpio = (nombre or "").strip()
    correo_limpio = (correo or "").strip().lower()
    telefono_limpio = (telefono or "").strip()
    if not nombre_limpio:
        return {"ok": False, "error": "Ingresa el nombre del cliente."}
    if correo_limpio and not EMAIL_PATTERN.fullmatch(correo_limpio):
        return {"ok": False, "error": "Ingresa un correo válido."}
    if len(telefono_limpio) > 40:
        return {"ok": False, "error": "El teléfono no puede superar 40 caracteres."}

    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_columnas_clientes(cursor)
        cursor.execute(
            "SELECT id FROM clientes WHERE id = :cliente_id",
            {"cliente_id": cliente_id},
        )
        if cursor.fetchone() is None:
            return {"ok": False, "error": "No se encontró el cliente."}
        cursor.execute("""
            UPDATE clientes SET nombre = :nombre, correo = :correo, telefono = :telefono
            WHERE id = :cliente_id
        """, {
            "nombre": nombre_limpio,
            "correo": correo_limpio or None,
            "telefono": telefono_limpio or None,
            "cliente_id": cliente_id,
        })
        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudieron actualizar los datos del cliente."}
    finally:
        if conn is not None:
            conn.close()


def eliminar_cliente_admin(cliente_id: int) -> dict:
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_columnas_clientes(cursor)
        cursor.execute(
            "SELECT id FROM clientes WHERE id = :cliente_id",
            {"cliente_id": cliente_id},
        )
        if cursor.fetchone() is None:
            return {"ok": False, "error": "No se encontró el cliente."}

        tiene_historial = False
        for tabla in ("inscripciones", "ventas", "pagos"):
            cursor.execute(
                f"SELECT COUNT(*) FROM {tabla} WHERE cliente_id = :cliente_id",
                {"cliente_id": cliente_id},
            )
            if cursor.fetchone()[0] > 0:
                tiene_historial = True
                break

        if tiene_historial:
            cursor.execute(
                "UPDATE clientes SET activo = 0 WHERE id = :cliente_id",
                {"cliente_id": cliente_id},
            )
            accion = "desactivado"
        else:
            cursor.execute(
                "DELETE FROM clientes WHERE id = :cliente_id",
                {"cliente_id": cliente_id},
            )
            accion = "eliminado"
        conn.commit()
        return {"ok": True, "accion": accion}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo eliminar o dar de baja al cliente."}
    finally:
        if conn is not None:
            conn.close()


def cambiar_estado_cliente_admin(cliente_id: int, activo: bool) -> dict:
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_columnas_clientes(cursor)
        cursor.execute(
            "UPDATE clientes SET activo = :activo WHERE id = :cliente_id",
            {"activo": int(activo), "cliente_id": cliente_id},
        )
        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo cambiar el estado del cliente."}
    finally:
        if conn is not None:
            conn.close()


def listar_usuarios_admin() -> list[dict]:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        _ensure_users_table(cursor)
        cursor.execute(
            "SELECT id, nombre, correo, rol, fecha_registro "
            "FROM usuarios ORDER BY nombre"
        )
        return [
            {
                "id": row[0],
                "nombre": row[1],
                "correo": row[2],
                "rol": (row[3] or "MIEMBRO").upper(),
                "fecha_registro": _as_date(row[4]),
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def guardar_usuario_admin(
    usuario_id: int | None,
    nombre: str,
    correo: str,
    rol: str,
    password: str = "",
    admin_actual_id: int | None = None,
) -> dict:
    nombre_limpio = (nombre or "").strip()
    correo_limpio = (correo or "").strip().lower()
    rol_limpio = (rol or "").strip().upper()
    password = password or ""
    if not nombre_limpio:
        return {"ok": False, "error": "Ingresa el nombre del usuario."}
    if not EMAIL_PATTERN.fullmatch(correo_limpio):
        return {"ok": False, "error": "Ingresa un correo válido."}
    if rol_limpio not in {"ADMIN", "MIEMBRO"}:
        return {"ok": False, "error": "El rol seleccionado no es válido."}
    if usuario_id is None and len(password) < 8:
        return {"ok": False, "error": "La contraseña inicial debe tener al menos 8 caracteres."}
    if password and len(password) < 8:
        return {"ok": False, "error": "La contraseña debe tener al menos 8 caracteres."}
    if usuario_id == admin_actual_id and rol_limpio != "ADMIN":
        return {"ok": False, "error": "No puedes quitarte tu propio acceso de administrador."}

    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _ensure_users_table(cursor)
        if usuario_id is None:
            cursor.execute(
                "INSERT INTO usuarios (nombre, correo, password_hash, rol) "
                "VALUES (:nombre, :correo, :password_hash, :rol)",
                {
                    "nombre": nombre_limpio,
                    "correo": correo_limpio,
                    "password_hash": _hash_password(password),
                    "rol": rol_limpio,
                },
            )
        else:
            cursor.execute(
                "SELECT id FROM usuarios WHERE id = :usuario_id",
                {"usuario_id": usuario_id},
            )
            if cursor.fetchone() is None:
                return {"ok": False, "error": "No se encontró el usuario."}
            cursor.execute("""
                SELECT COUNT(*) FROM usuarios
                WHERE correo = :correo AND id <> :usuario_id
            """, {"correo": correo_limpio, "usuario_id": usuario_id})
            if cursor.fetchone()[0] > 0:
                return {"ok": False, "error": "Ese correo ya está asignado a otra cuenta."}
            cursor.execute(
                "SELECT rol FROM usuarios WHERE id = :usuario_id",
                {"usuario_id": usuario_id},
            )
            rol_anterior = (cursor.fetchone()[0] or "MIEMBRO").upper()
            if rol_anterior == "ADMIN" and rol_limpio != "ADMIN":
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE UPPER(rol) = 'ADMIN'")
                if cursor.fetchone()[0] <= 1:
                    return {"ok": False, "error": "Debe quedar al menos un administrador."}

            if password:
                cursor.execute("""
                    UPDATE usuarios SET nombre = :nombre, correo = :correo,
                        rol = :rol, password_hash = :password_hash
                    WHERE id = :usuario_id
                """, {
                    "nombre": nombre_limpio,
                    "correo": correo_limpio,
                    "rol": rol_limpio,
                    "password_hash": _hash_password(password),
                    "usuario_id": usuario_id,
                })
            else:
                cursor.execute("""
                    UPDATE usuarios SET nombre = :nombre, correo = :correo, rol = :rol
                    WHERE id = :usuario_id
                """, {
                    "nombre": nombre_limpio,
                    "correo": correo_limpio,
                    "rol": rol_limpio,
                    "usuario_id": usuario_id,
                })
        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo guardar el usuario en Oracle."}
    finally:
        if conn is not None:
            conn.close()


def eliminar_usuario_admin(usuario_id: int, admin_actual_id: int) -> dict:
    if usuario_id == admin_actual_id:
        return {"ok": False, "error": "No puedes eliminar tu propia cuenta de administrador."}

    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _ensure_users_table(cursor)
        cursor.execute(
            "SELECT rol FROM usuarios WHERE id = :usuario_id",
            {"usuario_id": usuario_id},
        )
        usuario = cursor.fetchone()
        if usuario is None:
            return {"ok": False, "error": "No se encontró el usuario."}
        if (usuario[0] or "MIEMBRO").upper() == "ADMIN":
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE UPPER(rol) = 'ADMIN'")
            if cursor.fetchone()[0] <= 1:
                return {"ok": False, "error": "Debe quedar al menos un administrador."}

        cursor.execute(
            "SELECT COUNT(*) FROM user_tables WHERE UPPER(table_name) = 'HISTORIAL_CHAT'"
        )
        if cursor.fetchone()[0] > 0:
            cursor.execute(
                "DELETE FROM historial_chat WHERE usuario_id = :usuario_id",
                {"usuario_id": usuario_id},
            )
        cursor.execute(
            "DELETE FROM usuarios WHERE id = :usuario_id",
            {"usuario_id": usuario_id},
        )
        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo eliminar el usuario de Oracle."}
    finally:
        if conn is not None:
            conn.close()


def listar_planes_admin(solo_activos: bool = False) -> list[dict]:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        consulta = "SELECT id, nombre, precio_clp, duracion_dias, activo FROM planes"
        if solo_activos:
            consulta += " WHERE activo = 1"
        consulta += " ORDER BY precio_clp"
        cursor.execute(consulta)
        return [
            {
                "id": row[0],
                "nombre": row[1],
                "precio": float(row[2]),
                "duracion": int(row[3]),
                "activo": bool(row[4]),
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def guardar_plan_admin(
    plan_id: int | None,
    nombre: str,
    precio: float,
    duracion: int,
    activo: bool = True,
) -> dict:
    nombre_limpio = (nombre or "").strip()
    try:
        precio_float = float(precio)
        duracion_int = int(duracion)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Precio y duración deben ser numéricos."}
    if not nombre_limpio or len(nombre_limpio) > 50:
        return {"ok": False, "error": "El nombre del plan debe tener entre 1 y 50 caracteres."}
    if precio_float <= 0 or duracion_int <= 0:
        return {"ok": False, "error": "El precio y la duración deben ser mayores que cero."}

    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        if plan_id is None:
            cursor.execute("""
                INSERT INTO planes (nombre, descripcion, precio_clp, duracion_dias, activo)
                VALUES (:nombre, :descripcion, :precio, :duracion, :activo)
            """, {
                "nombre": nombre_limpio,
                "descripcion": f"Plan {nombre_limpio}",
                "precio": precio_float,
                "duracion": duracion_int,
                "activo": int(activo),
            })
        else:
            cursor.execute(
                "SELECT duracion_dias FROM planes WHERE id = :plan_id",
                {"plan_id": plan_id},
            )
            plan = cursor.fetchone()
            if plan is None:
                return {"ok": False, "error": "No se encontró el plan."}
            if int(plan[0]) != duracion_int:
                cursor.execute(
                    "SELECT COUNT(*) FROM inscripciones WHERE plan_id = :plan_id",
                    {"plan_id": plan_id},
                )
                if cursor.fetchone()[0] > 0:
                    return {
                        "ok": False,
                        "error": "No se puede cambiar la duración de un plan con inscripciones históricas.",
                    }
            cursor.execute("""
                UPDATE planes SET nombre = :nombre, precio_clp = :precio,
                    duracion_dias = :duracion, activo = :activo
                WHERE id = :plan_id
            """, {
                "nombre": nombre_limpio,
                "precio": precio_float,
                "duracion": duracion_int,
                "activo": int(activo),
                "plan_id": plan_id,
            })
        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo guardar el plan. Revisa si el nombre ya existe."}
    finally:
        if conn is not None:
            conn.close()


def eliminar_plan_admin(plan_id: int) -> dict:
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM planes WHERE id = :plan_id",
            {"plan_id": plan_id},
        )
        if cursor.fetchone() is None:
            return {"ok": False, "error": "No se encontró el plan."}
        cursor.execute(
            "SELECT COUNT(*) FROM inscripciones WHERE plan_id = :plan_id",
            {"plan_id": plan_id},
        )
        if cursor.fetchone()[0] > 0:
            cursor.execute(
                "UPDATE planes SET activo = 0 WHERE id = :plan_id",
                {"plan_id": plan_id},
            )
            accion = "desactivado"
        else:
            cursor.execute(
                "DELETE FROM planes WHERE id = :plan_id",
                {"plan_id": plan_id},
            )
            accion = "eliminado"
        conn.commit()
        return {"ok": True, "accion": accion}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo eliminar o desactivar el plan."}
    finally:
        if conn is not None:
            conn.close()


def listar_pagos_admin(limite: int = 100) -> list[dict]:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM (
                SELECT p.id, c.nombre, p.monto, p.metodo_pago, p.fecha_pago,
                       p.estado, p.venta_id
                FROM pagos p
                JOIN clientes c ON c.id = p.cliente_id
                ORDER BY p.id DESC
            ) WHERE ROWNUM <= :limite
        """, {"limite": max(1, min(int(limite), 500))})
        return [
            {
                "id": row[0],
                "cliente": row[1],
                "monto": float(row[2]),
                "metodo": row[3],
                "fecha": _as_date(row[4]),
                "estado": row[5],
                "venta_id": row[6],
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def obtener_ingresos_mes_admin() -> float:
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT NVL(SUM(monto), 0) FROM pagos
            WHERE estado = 'PAGADO'
              AND fecha_pago >= TRUNC(SYSDATE, 'MM')
              AND fecha_pago < ADD_MONTHS(TRUNC(SYSDATE, 'MM'), 1)
        """)
        return float(cursor.fetchone()[0])
    finally:
        conn.close()


def obtener_datos_graficos_admin(meses: int = 6) -> dict:
    cantidad_meses = max(1, min(int(meses), 24))
    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TO_CHAR(TRUNC(fecha_pago, 'MM'), 'YYYY-MM'), SUM(monto)
            FROM pagos
            WHERE estado = 'PAGADO'
              AND fecha_pago >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), :offset)
            GROUP BY TRUNC(fecha_pago, 'MM')
            ORDER BY TRUNC(fecha_pago, 'MM')
        """, {"offset": 1 - cantidad_meses})
        ingresos_por_mes = {row[0]: float(row[1]) for row in cursor.fetchall()}

        hoy = date.today().replace(day=1)
        ingresos = []
        for offset in range(1 - cantidad_meses, 1):
            indice_mes = hoy.year * 12 + hoy.month - 1 + offset
            mes = date(indice_mes // 12, indice_mes % 12 + 1, 1)
            clave_mes = mes.strftime("%Y-%m")
            ingresos.append({"mes": mes.strftime("%b %Y"), "ingresos": ingresos_por_mes.get(clave_mes, 0.0)})

        cursor.execute("""
            SELECT plan, COUNT(*) FROM (
                SELECT p.nombre AS plan,
                       ROW_NUMBER() OVER (PARTITION BY i.cliente_id ORDER BY i.id DESC) AS rn
                FROM inscripciones i
                JOIN planes p ON p.id = i.plan_id
                WHERE i.estado IN ('ACTIVA', 'RENOVADA')
                                    AND TRUNC(i.fecha_inscripcion) <= TRUNC(SYSDATE)
                                      AND TRUNC(SYSDATE) <
                                          TRUNC(i.fecha_inscripcion) + NVL(p.duracion_dias, 30)
            ) WHERE rn = 1
            GROUP BY plan ORDER BY plan
        """)
        membresias_por_plan = [
            {"plan": row[0], "membresias": int(row[1])}
            for row in cursor.fetchall()
        ]
        return {"ingresos": ingresos, "membresias_por_plan": membresias_por_plan}
    finally:
        conn.close()


def calcular_metricas_admin(
    clientes: list[dict],
    pagos: list[dict],
    hoy: date | None = None,
    ingresos_mes_override: float | None = None,
) -> dict:
    hoy = hoy or date.today()
    mes_inicio = hoy.replace(day=1)
    activas = [cliente for cliente in clientes if cliente["estado"] == "ACTIVA"]
    por_vencer = [
        cliente for cliente in activas
        if cliente["fecha_vencimiento"] is not None
        and 0 <= (cliente["fecha_vencimiento"] - hoy).days <= 7
    ]
    ingresos = sum(
        pago["monto"]
        for pago in pagos
        if pago["estado"] == "PAGADO" and pago["fecha"] and pago["fecha"] >= mes_inicio
    )
    return {
        "clientes": len(clientes),
        "membresias_activas": len(activas),
        "por_vencer": len(por_vencer),
        "ingresos_mes": ingresos if ingresos_mes_override is None else ingresos_mes_override,
    }


def registrar_renovacion_admin(
    cliente_id: int, plan_id: int, metodo: str, estado_pago: str
) -> dict:
    estado_limpio = (estado_pago or "").strip().upper()
    metodo_limpio = (metodo or "").strip().lower()
    if estado_limpio not in ESTADOS_PAGO:
        return {"ok": False, "error": "Estado de pago inválido."}
    if not metodo_limpio:
        return {"ok": False, "error": "Selecciona un método de pago."}

    conn = None
    try:
        import oracledb

        conn = get_oracle_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clientes WHERE id = :cliente_id", {"cliente_id": cliente_id})
        if cursor.fetchone() is None:
            return {"ok": False, "error": "No se encontró el cliente."}

        cursor.execute(
            "SELECT id, nombre, precio_clp, duracion_dias FROM planes "
            "WHERE id = :plan_id AND activo = 1",
            {"plan_id": plan_id},
        )
        plan = cursor.fetchone()
        if plan is None:
            return {"ok": False, "error": "No se encontró el plan activo."}

        cursor.execute("""
            SELECT MAX(i.fecha_inscripcion + NVL(p.duracion_dias, 30) - 1)
            FROM inscripciones i
            JOIN planes p ON p.id = i.plan_id
            WHERE i.cliente_id = :cliente_id
              AND i.estado IN ('ACTIVA', 'RENOVADA')
        """, {"cliente_id": cliente_id})
        fecha_actual = _as_date(cursor.fetchone()[0])
        inicio = date.today()
        if fecha_actual and fecha_actual >= inicio:
            inicio = fecha_actual + timedelta(days=1)

        estado_inscripcion = "ACTIVA" if estado_limpio == "PAGADO" else "PENDIENTE"
        monto = float(plan[2])
        inscripcion_id_var = cursor.var(oracledb.DB_TYPE_NUMBER)
        cursor.execute("""
            INSERT INTO inscripciones
                (cliente_id, plan_id, fecha_inscripcion, estado, monto_total)
            VALUES (:cliente_id, :plan_id, :fecha_inicio, :estado, :monto)
            RETURNING id INTO :id
        """, {
            "cliente_id": cliente_id,
            "plan_id": plan_id,
            "fecha_inicio": datetime.combine(inicio, time.min),
            "estado": estado_inscripcion,
            "monto": monto,
            "id": inscripcion_id_var,
        })
        inscripcion_id = _id_generado(inscripcion_id_var)

        venta_id_var = cursor.var(oracledb.DB_TYPE_NUMBER)
        estado_venta = "CONFIRMADA" if estado_limpio == "PAGADO" else "PENDIENTE"
        cursor.execute("""
            INSERT INTO ventas
                (cliente_id, inscripcion_id, fecha_venta, total, metodo_pago, estado)
            VALUES (:cliente_id, :inscripcion_id, SYSDATE, :total, :metodo, :estado)
            RETURNING id INTO :id
        """, {
            "cliente_id": cliente_id,
            "inscripcion_id": inscripcion_id,
            "total": monto,
            "metodo": metodo_limpio,
            "estado": estado_venta,
            "id": venta_id_var,
        })
        venta_id = _id_generado(venta_id_var)
        cursor.execute("""
            INSERT INTO pagos
                (venta_id, cliente_id, monto, metodo_pago, fecha_pago, estado)
            VALUES (:venta_id, :cliente_id, :monto, :metodo, SYSDATE, :estado)
        """, {
            "venta_id": venta_id,
            "cliente_id": cliente_id,
            "monto": monto,
            "metodo": metodo_limpio,
            "estado": estado_limpio,
        })
        _sincronizar_planes_actuales(cursor)
        conn.commit()
        return {
            "ok": True,
            "monto": monto,
            "estado": estado_limpio,
            "fecha_inicio": inicio,
        }
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo registrar la renovación en Oracle."}
    finally:
        if conn is not None:
            conn.close()


def marcar_pago_pagado(pago_id: int) -> dict:
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cliente_id, venta_id FROM pagos WHERE id = :pago_id AND estado = 'PENDIENTE'",
            {"pago_id": pago_id},
        )
        pago = cursor.fetchone()
        if pago is None:
            return {"ok": False, "error": "No se encontró un pago pendiente con ese ID."}

        cursor.execute(
            "UPDATE pagos SET estado = 'PAGADO', fecha_pago = SYSDATE WHERE id = :pago_id",
            {"pago_id": pago_id},
        )
        cursor.execute(
            "UPDATE ventas SET estado = 'CONFIRMADA' WHERE id = :venta_id",
            {"venta_id": pago[1]},
        )
        cursor.execute("""
            UPDATE inscripciones SET estado = 'ACTIVA',
                fecha_inscripcion = CASE
                    WHEN fecha_inscripcion < TRUNC(SYSDATE) THEN TRUNC(SYSDATE)
                    ELSE fecha_inscripcion
                END
            WHERE id = (SELECT inscripcion_id FROM ventas WHERE id = :venta_id)
        """, {"venta_id": pago[1]})
        _sincronizar_planes_actuales(cursor)
        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo actualizar el pago en Oracle."}
    finally:
        if conn is not None:
            conn.close()


def listar_solicitudes_servicios_admin(limite: int = 100) -> list[dict]:
    from .member import _asegurar_tabla_solicitudes

    conn = get_oracle_connection()
    try:
        cursor = conn.cursor()
        _asegurar_tabla_solicitudes(cursor)
        cursor.execute("""
            SELECT * FROM (
                SELECT s.id, c.nombre, s.servicio, s.actividad,
                       s.fecha_solicitada, s.estado, s.incluida, s.monto,
                      s.pago_estado, s.observaciones, s.pago_id, s.venta_id,
                      p.metodo_pago
                FROM solicitudes_servicios s
                JOIN clientes c ON c.id = s.cliente_id
                  LEFT JOIN pagos p ON p.id = s.pago_id
                ORDER BY s.fecha_solicitada DESC, s.id DESC
            ) WHERE ROWNUM <= :limite
        """, {"limite": max(1, min(int(limite), 500))})
        return [
            {
                "id": row[0],
                "cliente": row[1],
                "servicio": row[2],
                "actividad": row[3] or "",
                "fecha": row[4],
                "estado": row[5],
                "incluida": bool(row[6]),
                "monto": float(row[7]),
                "pago_estado": row[8],
                "observaciones": row[9] or "",
                "pago_id": row[10],
                "venta_id": row[11],
                "metodo": row[12] or "",
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def gestionar_solicitud_servicio_admin(solicitud_id: int, accion: str) -> dict:
    acciones = {"CONFIRMAR", "CONFIRMAR_PAGO", "RECHAZAR"}
    accion_limpia = (accion or "").strip().upper()
    if accion_limpia not in acciones:
        return {"ok": False, "error": "Acción de solicitud inválida."}

    conn = None
    try:
        from .member import _asegurar_tabla_solicitudes

        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_tabla_solicitudes(cursor)
        cursor.execute("""
            SELECT incluida, estado, pago_id, venta_id
            FROM solicitudes_servicios
            WHERE id = :solicitud_id
            FOR UPDATE
        """, {"solicitud_id": solicitud_id})
        solicitud = cursor.fetchone()
        if solicitud is None:
            return {"ok": False, "error": "No se encontró la solicitud."}

        incluida, estado, pago_id, venta_id = solicitud
        if accion_limpia == "CONFIRMAR":
            if not incluida or estado != "SOLICITADA":
                return {"ok": False, "error": "Esta solicitud requiere confirmar el pago."}
            cursor.execute("""
                UPDATE solicitudes_servicios SET estado = 'CONFIRMADA'
                WHERE id = :solicitud_id
            """, {"solicitud_id": solicitud_id})
        elif accion_limpia == "CONFIRMAR_PAGO":
            if incluida or estado != "PENDIENTE_PAGO" or pago_id is None or venta_id is None:
                return {"ok": False, "error": "La solicitud no tiene un pago pendiente que confirmar."}
            cursor.execute("""
                UPDATE pagos SET estado = 'PAGADO', fecha_pago = SYSDATE
                WHERE id = :pago_id AND estado = 'PENDIENTE'
            """, {"pago_id": pago_id})
            cursor.execute(
                "UPDATE ventas SET estado = 'CONFIRMADA' WHERE id = :venta_id",
                {"venta_id": venta_id},
            )
            cursor.execute("""
                UPDATE solicitudes_servicios
                SET estado = 'CONFIRMADA', pago_estado = 'PAGADO'
                WHERE id = :solicitud_id
            """, {"solicitud_id": solicitud_id})
        else:
            if estado in {"CONFIRMADA", "RECHAZADA", "CANCELADA"}:
                return {"ok": False, "error": "La solicitud ya fue procesada."}
            if pago_id is not None:
                cursor.execute("""
                    UPDATE pagos SET estado = 'CANCELADO'
                    WHERE id = :pago_id AND estado = 'PENDIENTE'
                """, {"pago_id": pago_id})
            if venta_id is not None:
                cursor.execute("""
                    UPDATE ventas SET estado = 'CANCELADA'
                    WHERE id = :venta_id AND estado = 'PENDIENTE'
                """, {"venta_id": venta_id})
            cursor.execute("""
                UPDATE solicitudes_servicios SET estado = 'RECHAZADA'
                WHERE id = :solicitud_id
            """, {"solicitud_id": solicitud_id})

        conn.commit()
        return {"ok": True}
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo procesar la solicitud."}
    finally:
        if conn is not None:
            conn.close()