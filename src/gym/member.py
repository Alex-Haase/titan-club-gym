from datetime import date, datetime, timedelta

from .admin import _asegurar_columnas_clientes
from .database import get_oracle_connection

SERVICIOS_DISPONIBLES = {
    "NUTRICIONISTA",
    "CLASE_GRUPAL",
    "ENTRENADOR_PERSONAL",
    "EVALUACION_FISICA",
}
PRECIO_SESION_EXTRA = 15000.0


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def obtener_portal_miembro(correo: str) -> dict:
    correo_limpio = (correo or "").strip().lower()
    if not correo_limpio:
        return {"ok": False, "error": "La cuenta no tiene un correo válido."}

    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_columnas_clientes(cursor)
        cursor.execute("""
            SELECT id, nombre, correo, telefono, plan_actual, fecha_registro, activo
            FROM clientes
            WHERE LOWER(correo) = :correo
        """, {"correo": correo_limpio})
        filas_cliente = cursor.fetchall()
        if not filas_cliente:
            return {"ok": True, "cliente": None, "membresia": None, "inscripciones": [], "pagos": []}
        if len(filas_cliente) > 1:
            return {
                "ok": False,
                "error": "Este correo está asociado a más de una ficha. Contacta a administración.",
            }

        fila = filas_cliente[0]
        cliente_id = fila[0]
        cliente = {
            "id": cliente_id,
            "nombre": fila[1],
            "correo": fila[2],
            "telefono": fila[3] or "",
            "plan_actual": fila[4],
            "fecha_registro": _as_date(fila[5]),
            "activo": bool(fila[6]),
        }

        cursor.execute("""
            SELECT i.id, p.nombre, i.fecha_inscripcion,
                   NVL(p.duracion_dias, 30), i.estado, i.monto_total
            FROM inscripciones i
            JOIN planes p ON p.id = i.plan_id
            WHERE i.cliente_id = :cliente_id
            ORDER BY i.id DESC
        """, {"cliente_id": cliente_id})
        hoy = date.today()
        inscripciones = []
        for row in cursor.fetchall():
            inicio = _as_date(row[2])
            duracion = int(row[3] or 30)
            vencimiento = inicio + timedelta(days=duracion - 1) if inicio else None
            estado = (row[4] or "ACTIVA").upper()
            if estado in {"ACTIVA", "RENOVADA"} and inicio and vencimiento:
                if inicio > hoy:
                    estado = "PROGRAMADA"
                elif hoy > vencimiento:
                    estado = "VENCIDA"
                else:
                    estado = "ACTIVA"
            inscripciones.append({
                "id": row[0],
                "plan": row[1],
                "inicio": inicio,
                "vencimiento": vencimiento,
                "estado": estado,
                "monto": float(row[5]),
            })

        membresia = next(
            (item for item in inscripciones if item["estado"] == "ACTIVA"),
            None,
        )
        if membresia is None:
            membresia = next(
                (item for item in inscripciones if item["estado"] == "PENDIENTE"),
                None,
            )
        if not cliente["activo"]:
            estado_cliente = "BAJA"
        elif membresia is not None:
            estado_cliente = membresia["estado"]
        elif any(item["estado"] == "VENCIDA" for item in inscripciones):
            estado_cliente = "VENCIDA"
        else:
            estado_cliente = "SIN MEMBRESIA"

        cursor.execute("""
            SELECT id, monto, metodo_pago, fecha_pago, estado
            FROM pagos WHERE cliente_id = :cliente_id
            ORDER BY id DESC
        """, {"cliente_id": cliente_id})
        pagos = [
            {
                "id": row[0],
                "monto": float(row[1]),
                "metodo": row[2] or "",
                "fecha": _as_date(row[3]),
                "estado": (row[4] or "PENDIENTE").upper(),
            }
            for row in cursor.fetchall()
        ]

        _asegurar_tabla_solicitudes(cursor)
        cursor.execute("""
             SELECT s.id, s.servicio, s.actividad, s.fecha_solicitada,
                 s.estado, s.incluida, s.monto, s.pago_estado,
                 s.observaciones, p.metodo_pago
                 FROM solicitudes_servicios s
                 LEFT JOIN pagos p ON p.id = s.pago_id
                 WHERE s.cliente_id = :cliente_id
                 ORDER BY s.fecha_solicitada DESC, s.id DESC
        """, {"cliente_id": cliente_id})
        solicitudes = [
            {
                "id": row[0],
                "servicio": row[1],
                "actividad": row[2] or "",
                "fecha": row[3],
                "estado": row[4],
                "incluida": bool(row[5]),
                "monto": float(row[6]),
                "pago_estado": row[7],
                "observaciones": row[8] or "",
                "metodo": row[9] or "",
            }
            for row in cursor.fetchall()
        ]

        return {
            "ok": True,
            "cliente": cliente,
            "estado": estado_cliente,
            "membresia": membresia,
            "inscripciones": inscripciones,
            "pagos": pagos,
            "solicitudes": solicitudes,
        }
    except Exception:
        return {"ok": False, "error": "No se pudo cargar tu ficha desde Oracle."}
    finally:
        if conn is not None:
            conn.close()


def _asegurar_tabla_solicitudes(cursor) -> None:
    cursor.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = 'SOLICITUDES_SERVICIOS'"
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            CREATE TABLE solicitudes_servicios (
                id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                cliente_id NUMBER NOT NULL,
                inscripcion_id NUMBER NOT NULL,
                servicio VARCHAR2(30) NOT NULL,
                actividad VARCHAR2(100),
                fecha_solicitada DATE NOT NULL,
                estado VARCHAR2(30) NOT NULL,
                incluida NUMBER(1) DEFAULT 0 NOT NULL,
                monto NUMBER(10,2) DEFAULT 0 NOT NULL,
                pago_estado VARCHAR2(20) NOT NULL,
                venta_id NUMBER,
                pago_id NUMBER,
                observaciones VARCHAR2(500),
                fecha_creacion DATE DEFAULT SYSDATE,
                CONSTRAINT fk_solserv_cliente FOREIGN KEY (cliente_id) REFERENCES clientes(id),
                CONSTRAINT fk_solserv_inscrip FOREIGN KEY (inscripcion_id) REFERENCES inscripciones(id),
                CONSTRAINT fk_solserv_venta FOREIGN KEY (venta_id) REFERENCES ventas(id),
                CONSTRAINT fk_solserv_pago FOREIGN KEY (pago_id) REFERENCES pagos(id)
            )
        """)


def _obtener_membresia_para_fecha(cursor, correo: str, fecha: datetime):
    cursor.execute("""
        SELECT cliente_id, inscripcion_id, plan FROM (
            SELECT c.id AS cliente_id,
                   i.id AS inscripcion_id,
                   LOWER(p.nombre) AS plan,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.id ORDER BY i.fecha_inscripcion DESC, i.id DESC
                   ) AS rn
            FROM clientes c
            JOIN inscripciones i ON i.cliente_id = c.id
            JOIN planes p ON p.id = i.plan_id
            WHERE LOWER(c.correo) = :correo
              AND NVL(c.activo, 1) = 1
              AND UPPER(i.estado) IN ('ACTIVA', 'RENOVADA')
              AND TRUNC(:fecha_solicitada) >= TRUNC(i.fecha_inscripcion)
              AND TRUNC(:fecha_solicitada) <
                  TRUNC(i.fecha_inscripcion) + NVL(p.duracion_dias, 30)
        ) WHERE rn = 1
    """, {"correo": correo, "fecha_solicitada": fecha})
    return cursor.fetchone()


def _servicio_incluido(
    cursor,
    inscripcion_id: int,
    plan: str,
    servicio: str,
    fecha: datetime,
) -> bool:
    if plan == "plata" and servicio == "CLASE_GRUPAL":
        return True

    if plan == "plata" and servicio == "EVALUACION_FISICA":
        inicio_periodo = fecha.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if inicio_periodo.month == 12:
            fin_periodo = inicio_periodo.replace(year=inicio_periodo.year + 1, month=1)
        else:
            fin_periodo = inicio_periodo.replace(month=inicio_periodo.month + 1)
    elif plan == "oro" and servicio == "ENTRENADOR_PERSONAL":
        inicio_periodo = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
        inicio_periodo -= timedelta(days=inicio_periodo.weekday())
        fin_periodo = inicio_periodo + timedelta(days=7)
    elif plan == "oro" and servicio == "NUTRICIONISTA":
        cursor.execute("""
            SELECT COUNT(*) FROM solicitudes_servicios
            WHERE inscripcion_id = :inscripcion_id
              AND servicio = :servicio
              AND incluida = 1
              AND estado NOT IN ('RECHAZADA', 'CANCELADA')
        """, {"inscripcion_id": inscripcion_id, "servicio": servicio})
        return cursor.fetchone()[0] == 0
    else:
        return False

    cursor.execute("""
        SELECT COUNT(*) FROM solicitudes_servicios
        WHERE inscripcion_id = :inscripcion_id
          AND servicio = :servicio
          AND incluida = 1
          AND estado NOT IN ('RECHAZADA', 'CANCELADA')
          AND fecha_solicitada >= :inicio_periodo
          AND fecha_solicitada < :fin_periodo
    """, {
        "inscripcion_id": inscripcion_id,
        "servicio": servicio,
        "inicio_periodo": inicio_periodo,
        "fin_periodo": fin_periodo,
    })
    return cursor.fetchone()[0] == 0


def _validar_solicitud(servicio: str, fecha: datetime, actividad: str, observaciones: str) -> str | None:
    if servicio not in SERVICIOS_DISPONIBLES:
        return "Selecciona un tipo de sesión válido."
    if fecha <= datetime.now():
        return "El horario debe ser posterior al momento actual."
    if len(actividad) > 100:
        return "La actividad no puede superar 100 caracteres."
    if len(observaciones) > 500:
        return "Las observaciones no pueden superar 500 caracteres."
    return None


def cotizar_solicitud_miembro(correo: str, servicio: str, fecha: datetime) -> dict:
    correo_limpio = (correo or "").strip().lower()
    servicio_limpio = (servicio or "").strip().upper()
    error = _validar_solicitud(servicio_limpio, fecha, "", "")
    if error:
        return {"ok": False, "error": error}
    conn = None
    try:
        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_tabla_solicitudes(cursor)
        membresia = _obtener_membresia_para_fecha(cursor, correo_limpio, fecha)
        if membresia is None:
            return {"ok": False, "error": "Necesitas una membresía vigente para solicitar una sesión."}
        incluida = _servicio_incluido(
            cursor, membresia[1], str(membresia[2]).strip().lower(), servicio_limpio, fecha
        )
        return {
            "ok": True,
            "incluida": incluida,
            "precio": 0.0 if incluida else PRECIO_SESION_EXTRA,
            "plan": str(membresia[2]).strip().lower(),
        }
    except Exception:
        return {"ok": False, "error": "No se pudo consultar tu beneficio en Oracle."}
    finally:
        if conn is not None:
            conn.close()


def solicitar_servicio_miembro(
    correo: str,
    servicio: str,
    fecha: datetime,
    actividad: str = "",
    observaciones: str = "",
    metodo_pago: str = "transferencia",
) -> dict:
    correo_limpio = (correo or "").strip().lower()
    servicio_limpio = (servicio or "").strip().upper()
    actividad_limpia = (actividad or "").strip()
    observaciones_limpias = (observaciones or "").strip()
    metodo_limpio = (metodo_pago or "transferencia").strip().lower()
    error = _validar_solicitud(
        servicio_limpio, fecha, actividad_limpia, observaciones_limpias
    )
    if error:
        return {"ok": False, "error": error}

    conn = None
    try:
        import oracledb

        conn = get_oracle_connection()
        cursor = conn.cursor()
        _asegurar_tabla_solicitudes(cursor)
        cursor.execute("""
            SELECT id FROM clientes
            WHERE LOWER(correo) = :correo AND NVL(activo, 1) = 1
            FOR UPDATE
        """, {"correo": correo_limpio})
        cliente = cursor.fetchone()
        if cliente is None:
            return {"ok": False, "error": "No encontramos una ficha activa vinculada a tu cuenta."}

        cursor.execute("""
            SELECT id, estado, incluida, monto, pago_id FROM (
                SELECT id, estado, incluida, monto, pago_id
                FROM solicitudes_servicios
                WHERE cliente_id = :cliente_id
                  AND servicio = :servicio
                  AND fecha_solicitada = :fecha
                  AND estado IN ('SOLICITADA', 'PENDIENTE_PAGO', 'CONFIRMADA')
                ORDER BY id DESC
            ) WHERE ROWNUM = 1
        """, {
            "cliente_id": cliente[0],
            "servicio": servicio_limpio,
            "fecha": fecha,
        })
        existente = cursor.fetchone()
        if existente is not None:
            return {
                "ok": True,
                "duplicada": True,
                "solicitud_id": existente[0],
                "incluida": bool(existente[2]),
                "monto": float(existente[3]),
                "estado": existente[1],
                "pago_id": existente[4],
            }

        membresia = _obtener_membresia_para_fecha(cursor, correo_limpio, fecha)
        if membresia is None:
            return {"ok": False, "error": "Necesitas una membresía vigente para ese horario."}
        cliente_id, inscripcion_id, plan = membresia
        incluida = _servicio_incluido(
            cursor, inscripcion_id, str(plan).strip().lower(), servicio_limpio, fecha
        )
        monto = 0.0 if incluida else PRECIO_SESION_EXTRA
        estado = "SOLICITADA" if incluida else "PENDIENTE_PAGO"
        pago_estado = "NO_APLICA" if incluida else "PENDIENTE"
        venta_id = None
        pago_id = None

        if not incluida:
            venta_id_var = cursor.var(oracledb.DB_TYPE_NUMBER)
            cursor.execute("""
                INSERT INTO ventas
                    (cliente_id, inscripcion_id, fecha_venta, total, metodo_pago, estado)
                VALUES (:cliente_id, :inscripcion_id, SYSDATE, :total, :metodo, 'PENDIENTE')
                RETURNING id INTO :id
            """, {
                "cliente_id": cliente_id,
                "inscripcion_id": inscripcion_id,
                "total": monto,
                "metodo": metodo_limpio,
                "id": venta_id_var,
            })
            venta_id = int(venta_id_var.getvalue()[0])
            pago_id_var = cursor.var(oracledb.DB_TYPE_NUMBER)
            cursor.execute("""
                INSERT INTO pagos
                    (venta_id, cliente_id, monto, metodo_pago, fecha_pago, estado)
                VALUES (:venta_id, :cliente_id, :monto, :metodo, SYSDATE, 'PENDIENTE')
                RETURNING id INTO :id
            """, {
                "venta_id": venta_id,
                "cliente_id": cliente_id,
                "monto": monto,
                "metodo": metodo_limpio,
                "id": pago_id_var,
            })
            pago_id = int(pago_id_var.getvalue()[0])

        solicitud_id_var = cursor.var(oracledb.DB_TYPE_NUMBER)
        cursor.execute("""
            INSERT INTO solicitudes_servicios
                (cliente_id, inscripcion_id, servicio, actividad,
                 fecha_solicitada, estado, incluida, monto, pago_estado,
                 venta_id, pago_id, observaciones)
            VALUES
                (:cliente_id, :inscripcion_id, :servicio, :actividad,
                 :fecha, :estado, :incluida, :monto, :pago_estado,
                 :venta_id, :pago_id, :observaciones)
            RETURNING id INTO :id
        """, {
            "cliente_id": cliente_id,
            "inscripcion_id": inscripcion_id,
            "servicio": servicio_limpio,
            "actividad": actividad_limpia or None,
            "fecha": fecha,
            "estado": estado,
            "incluida": int(incluida),
            "monto": monto,
            "pago_estado": pago_estado,
            "venta_id": venta_id,
            "pago_id": pago_id,
            "observaciones": observaciones_limpias or None,
            "id": solicitud_id_var,
        })
        solicitud_id = int(solicitud_id_var.getvalue()[0])
        conn.commit()
        return {
            "ok": True,
            "solicitud_id": solicitud_id,
            "incluida": incluida,
            "monto": monto,
            "estado": estado,
            "pago_id": pago_id,
        }
    except Exception:
        if conn is not None:
            conn.rollback()
        return {"ok": False, "error": "No se pudo guardar la solicitud en Oracle."}
    finally:
        if conn is not None:
            conn.close()