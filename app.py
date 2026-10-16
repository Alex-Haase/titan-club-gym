import os
from datetime import date, datetime, timedelta

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from src.gym.auth import iniciar_sesion, registrar_usuario
from src.gym.admin import (
    actualizar_cliente_admin,
    calcular_metricas_admin,
    cambiar_estado_cliente_admin,
    crear_cliente_admin,
    eliminar_cliente_admin,
    eliminar_plan_admin,
    eliminar_usuario_admin,
    guardar_plan_admin,
    guardar_usuario_admin,
    listar_clientes_admin,
    listar_pagos_admin,
    listar_planes_admin,
    listar_solicitudes_servicios_admin,
    listar_usuarios_admin,
    gestionar_solicitud_servicio_admin,
    marcar_pago_pagado,
    obtener_datos_graficos_admin,
    obtener_ingresos_mes_admin,
    registrar_renovacion_admin,
)
from src.gym.chat_history import cargar_historial_chat, guardar_intercambio_chat
from src.gym.database import inicializar_esquema_oracle, obtener_precios_planes
from src.gym.feedback import (
    cambiar_estado_sugerencia_admin,
    enviar_sugerencia,
    listar_sugerencias_admin,
)
from src.gym.member import (
    cotizar_solicitud_miembro,
    obtener_portal_miembro,
    solicitar_servicio_miembro,
)

load_dotenv()

st.set_page_config(page_title="Titan Club", page_icon="🏋️", layout="wide")
st.markdown("""
<style>
    :root {
        --titan-ink: #11182a;
        --titan-midnight: #10172a;
        --titan-green: #168567;
        --titan-red: #c84c55;
        --titan-violet: #49305f;
        --titan-paper: #f2f4f2;
        --titan-line: #d8dedf;
    }
    .stApp { background: var(--titan-paper); color: var(--titan-ink); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stMainBlockContainer"] { max-width: 1180px; padding-top: 1.5rem; }
    .brand-mark {
        color: var(--titan-green); font-size: .78rem; font-weight: 800;
        text-transform: uppercase; margin-bottom: .5rem;
    }
    .brand-title { color: var(--titan-ink); font-family: Georgia, serif; font-size: 2.25rem; font-weight: 700; margin: 0; }
    .brand-copy { color: #5c6962; margin: .25rem 0 1.75rem; }
    [data-testid="stForm"] {
        border: 1px solid var(--titan-line); border-radius: 6px;
        background: #fff; padding: 1.25rem;
    }
    [data-testid="stBaseButton-primary"] {
        background: var(--titan-green); border-color: var(--titan-green);
    }
    [data-testid="stBaseButton-primary"] p { color: white; font-weight: 700; }
    [data-testid="stTabs"] button[role="tab"] { color: var(--titan-ink); }
    [data-testid="stSidebar"] { background: #e9eee7; }
    [data-testid="stMetric"] {
        background: #fff; border: 1px solid var(--titan-line);
        border-top: 3px solid var(--titan-green); border-radius: 5px; padding: .75rem;
    }
    .login-hero {
        position: relative; min-height: 430px; overflow: hidden;
        border-radius: 6px; background: var(--titan-midnight); color: #fff;
    }
    .login-hero img {
        display: block; width: 100%; height: 430px; object-fit: cover;
        object-position: center 48%; filter: brightness(.58) saturate(.82);
    }
    .login-hero-overlay {
        position: absolute; inset: 0; display: flex; align-items: flex-end;
        padding: 2rem; background: linear-gradient(90deg, rgba(16,23,42,.82), rgba(16,23,42,.12));
    }
    .login-hero-copy { max-width: 520px; }
    .login-hero h1 {
        margin: .6rem 0; color: white; font-family: Georgia, serif;
        font-size: 2.8rem; line-height: 1.06;
    }
    .login-hero p { color: #eef2f4; font-size: 1.02rem; }
    .login-kicker { color: #8ee0bd; font-size: .78rem; font-weight: 800; text-transform: uppercase; }
    .login-accent { width: 72px; height: 5px; margin: 1.2rem 0; background: var(--titan-red); }
    .login-tags { color: #d8d0e2; font-size: .9rem; }
    .login-section { padding: 2rem 0; border-bottom: 1px solid var(--titan-line); }
    .login-section h2 { color: var(--titan-midnight); font-family: Georgia, serif; }
    .plan-card {
        min-height: 44px; margin-bottom: .25rem; padding: .55rem .65rem;
        border-top: 4px solid var(--titan-green); background: #e4ece8;
    }
    .plan-card.cobre { border-color: var(--titan-green); background: #e2f0e8; }
    .plan-card.plata { border-color: var(--titan-red); background: #f8e7e9; }
    .plan-card.oro { border-color: var(--titan-violet); background: #eee7f3; }
    .section-kicker { color: var(--titan-green); font-size: .75rem; font-weight: 800; text-transform: uppercase; }
    .login-section h3 { padding-left: .65rem; border-left: 3px solid var(--titan-red); }
    .login-footer {
        margin-top: 1.5rem; padding: 1rem 1.25rem; color: #e7ebf2;
        background: var(--titan-midnight); border-left: 5px solid var(--titan-violet);
        border-radius: 4px; font-size: .82rem;
    }
    @media (max-width: 700px) {
        .login-hero, .login-hero img { min-height: 310px; height: 310px; }
        .login-hero h1 { font-size: 2rem; }
        .login-hero-overlay { padding: 1.2rem; }
    }
</style>
""", unsafe_allow_html=True)


def _abrir_sesion(usuario: dict) -> None:
    st.session_state.usuario = usuario
    resultado_historial = cargar_historial_chat(usuario["id"])
    st.session_state.mensajes = resultado_historial.get("mensajes", [])
    st.session_state.error_historial = not resultado_historial["ok"]


if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

if st.session_state.usuario is None:
    hero_col, access_col = st.columns([1.15, 0.85], gap="large", vertical_alignment="center")
    with hero_col:
        st.markdown("""
            <section class="login-hero">
              <img src="https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1600&q=85" alt="Interior de un gimnasio Titan Club">
              <div class="login-hero-overlay"><div class="login-hero-copy">
                <div class="login-kicker">Titan Club · Entrena a tu manera</div>
                <h1>Fuerza para cada etapa.</h1>
                <div class="login-accent"></div>
                <p>Un espacio para moverte, aprender y construir hábitos que duren.</p>
                <div class="login-tags">FUERZA &nbsp; / &nbsp; COMUNIDAD &nbsp; / &nbsp; BIENESTAR</div>
              </div></div>
            </section>
        """, unsafe_allow_html=True)
    with access_col:
        st.markdown('<div class="brand-mark">Titan Club / Acceso de miembros</div>', unsafe_allow_html=True)
        st.markdown('<h1 class="brand-title">Tu siguiente paso.</h1>', unsafe_allow_html=True)
        st.markdown('<p class="brand-copy">Inicia sesión o crea tu cuenta para entrar a tu espacio.</p>', unsafe_allow_html=True)
        login_tab, register_tab = st.tabs(["Iniciar sesión", "Crear cuenta"])

        with login_tab:
            with st.form("login_form"):
                login_email = st.text_input("Correo", placeholder="tu@correo.com")
                login_password = st.text_input("Contraseña", type="password")
                login_submitted = st.form_submit_button("Entrar", type="primary", width="stretch")

            if login_submitted:
                result = iniciar_sesion(login_email, login_password)
                if result["ok"]:
                    _abrir_sesion(result["usuario"])
                    st.rerun()
                st.error(result["error"])

        with register_tab:
            with st.form("register_form"):
                register_name = st.text_input("Nombre completo")
                register_email = st.text_input("Correo", placeholder="tu@correo.com")
                register_password = st.text_input("Contraseña", type="password", help="Mínimo 8 caracteres.")
                register_confirmation = st.text_input("Confirmar contraseña", type="password")
                register_submitted = st.form_submit_button("Crear cuenta", type="primary", width="stretch")

            if register_submitted:
                if register_password != register_confirmation:
                    st.error("Las contraseñas no coinciden.")
                else:
                    result = registrar_usuario(register_name, register_email, register_password)
                    if result["ok"]:
                        _abrir_sesion(result["usuario"])
                        st.rerun()
                    st.error(result["error"])

    st.markdown('<section class="login-section">', unsafe_allow_html=True)
    mission_col, vision_col = st.columns(2, gap="large")
    with mission_col:
        st.markdown('<div class="section-kicker">Nuestra misión</div>', unsafe_allow_html=True)
        st.subheader("Hacer del movimiento un hábito sostenible.")
        st.write("Acompañamos a cada persona con entrenamiento, orientación y un espacio donde progresar a su propio ritmo.")
    with vision_col:
        st.markdown('<div class="section-kicker">Nuestra visión</div>', unsafe_allow_html=True)
        st.subheader("Una comunidad más fuerte y saludable.")
        st.write("Queremos que Titan Club sea un lugar cercano, inclusivo y preparado para cada objetivo.")
    st.markdown('</section>', unsafe_allow_html=True)

    st.markdown('<section class="login-section"><div class="section-kicker">Encuentra tu ritmo</div><h2>Categorías y beneficios</h2></section>', unsafe_allow_html=True)
    beneficios_planes = {
        "cobre": ("Base", ["Cardio y pesas libres", "Lockers generales", "Duchas estándar"]),
        "plata": ("Progreso", ["Clases grupales incluidas", "Evaluación física mensual", "Lockers privados"]),
        "oro": ("Total", ["Acceso 24/7 y zona VIP", "Entrenador personal semanal", "Primera consulta nutricional incluida"]),
    }
    try:
        precios_publicos = obtener_precios_planes()
    except Exception:
        precios_publicos = {}
    plan_columns = st.columns(3, gap="large")
    for plan_column, (nombre_plan, (categoria, beneficios)) in zip(plan_columns, beneficios_planes.items()):
        with plan_column:
            st.markdown(f'<div class="plan-card {nombre_plan}"><div class="section-kicker">{categoria}</div></div>', unsafe_allow_html=True)
            st.subheader(nombre_plan.title())
            precio = precios_publicos.get(nombre_plan)
            st.markdown(
                f"### ${precio:,.0f} CLP / mes" if precio is not None else "### Precio en consulta"
            )
            for beneficio in beneficios:
                st.markdown(f"- {beneficio}")

    st.markdown('<section class="login-section">', unsafe_allow_html=True)
    about_col, contact_col = st.columns([1, 1.2], gap="large")
    with about_col:
        st.markdown('<div class="section-kicker">Acerca de nosotros</div>', unsafe_allow_html=True)
        st.subheader("Entrenamiento con propósito.")
        st.write("Titan Club combina equipamiento, acompañamiento profesional y una comunidad que celebra el progreso cotidiano.")
        st.caption("Contacto: recepción Titan Club o deja una sugerencia al equipo.")
    with contact_col:
        st.markdown('<div class="section-kicker">Contacto / sugerencias</div>', unsafe_allow_html=True)
        with st.form("public_feedback_form"):
            feedback_name = st.text_input("Nombre (opcional)", key="public_feedback_name")
            feedback_email = st.text_input("Correo para responder (opcional)", key="public_feedback_email")
            feedback_message = st.text_area("Tu sugerencia", max_chars=1000, key="public_feedback_message")
            feedback_submitted = st.form_submit_button("Enviar sugerencia", type="primary")
        if feedback_submitted:
            feedback_result = enviar_sugerencia(feedback_name, feedback_email, feedback_message)
            if feedback_result["ok"]:
                st.success("Sugerencia recibida. Gracias por ayudarnos a mejorar.")
            else:
                st.error(feedback_result["error"])
    st.markdown('</section>', unsafe_allow_html=True)
    st.markdown(
        '<footer class="login-footer">TITAN CLUB &nbsp; · &nbsp; FUERZA, EQUILIBRIO Y COMUNIDAD</footer>',
        unsafe_allow_html=True,
    )
    st.stop()

with st.sidebar:
    st.markdown("### Titan Club")
    st.write(st.session_state.usuario["nombre"])
    st.caption(st.session_state.usuario["correo"])
    st.caption("Administrador" if st.session_state.usuario.get("rol") == "ADMIN" else "Miembro")
    if st.button("Cerrar sesión", width="stretch"):
        st.session_state.usuario = None
        st.session_state.mensajes = []
        st.session_state.error_historial = False
        st.session_state.pop("solicitud_confirmacion", None)
        st.session_state["solicitud_form_version"] = 0
        st.rerun()


def _render_chat() -> None:
    st.title("Asistente Titan Club")
    st.caption("Consulta planes, horarios y beneficios de membresía.")
    if st.session_state.get("error_historial"):
        st.warning("No se pudo cargar el historial guardado. Esta conversación podría no persistir.")
    if not os.getenv("GROQ_API_KEY"):
        st.error("El asistente no está configurado. Falta GROQ_API_KEY en el entorno.")
        return

    try:
        from langchain_core.messages import AIMessage, HumanMessage
        from src.gym.agent import agente_gym
    except Exception as exc:
        st.error(f"No se pudo iniciar el asistente: {exc}")
        return

    for message in st.session_state.mensajes:
        role = "user" if isinstance(message, HumanMessage) else "assistant"
        avatar = "🧑‍💻" if role == "user" else "🤖"
        with st.chat_message(role, avatar=avatar):
            st.markdown(message.content)

    if prompt := st.chat_input("Escribe tu consulta..."):
        st.session_state.mensajes.append(HumanMessage(content=prompt))
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("TitanBot está escribiendo..."):
                try:
                    response = agente_gym.invoke({
                        "input": prompt,
                        "chat_history": st.session_state.mensajes[-41:-1],
                    })["output"]
                except Exception as exc:
                    response = f"No pude procesar la consulta. Inténtalo nuevamente. ({exc})"
                st.markdown(response)

        st.session_state.mensajes.append(AIMessage(content=response))
        resultado_guardado = guardar_intercambio_chat(
            st.session_state.usuario["id"], prompt, response
        )
        if not resultado_guardado["ok"]:
            st.warning("No se pudo guardar este intercambio en tu historial.")


def _render_admin() -> None:
    st.title("Panel de administración")
    if not inicializar_esquema_oracle():
        st.error("No se pudo preparar el esquema de Oracle.")
        return

    try:
        clientes = listar_clientes_admin()
        todos_los_clientes = listar_clientes_admin(incluir_inactivos=True)
        pagos = listar_pagos_admin()
        planes = listar_planes_admin()
        usuarios = listar_usuarios_admin()
        solicitudes_servicios = listar_solicitudes_servicios_admin()
        sugerencias = listar_sugerencias_admin()
        graficos = obtener_datos_graficos_admin()
        metricas = calcular_metricas_admin(
            clientes, pagos, ingresos_mes_override=obtener_ingresos_mes_admin()
        )
    except Exception:
        st.error("No se pudieron cargar los datos administrativos desde Oracle.")
        return
    planes_activos = [plan for plan in planes if plan["activo"]]
    resumen_tab, clientes_tab, usuarios_tab, planes_tab, solicitudes_tab, pagos_tab, sugerencias_tab, asistente_tab = st.tabs(
        ["Resumen", "Clientes", "Usuarios", "Planes", "Solicitudes", "Pagos", "Sugerencias", "Asistente"]
    )

    with resumen_tab:
        total_col, activos_col, vencen_col, ingresos_col = st.columns(4)
        total_col.metric("Clientes", metricas["clientes"])
        activos_col.metric("Membresías activas", metricas["membresias_activas"])
        vencen_col.metric("Vencen en 7 días", metricas["por_vencer"])
        ingresos_col.metric("Ingresos del mes", f"${metricas['ingresos_mes']:,.0f}")

        vencimientos = [
            cliente for cliente in clientes
            if cliente["estado"] == "ACTIVA"
            and cliente["fecha_vencimiento"] is not None
            and 0 <= (cliente["fecha_vencimiento"] - date.today()).days <= 7
        ]
        st.subheader("Próximos vencimientos")
        st.dataframe(
            [{key: cliente[key] for key in ("nombre", "plan", "fecha_vencimiento")}
             for cliente in vencimientos],
            hide_index=True,
            width="stretch",
        )
        chart_ingresos, chart_planes = st.columns(2)
        with chart_ingresos:
            st.subheader("Ingresos por mes")
            ingresos_df = pd.DataFrame(graficos["ingresos"]).set_index("mes")
            st.bar_chart(ingresos_df, color="#14866D")
        with chart_planes:
            st.subheader("Membresías activas por plan")
            if graficos["membresias_por_plan"]:
                planes_df = pd.DataFrame(graficos["membresias_por_plan"]).set_index("plan")
                st.bar_chart(planes_df, color="#D88932")
            else:
                st.info("Aún no hay membresías activas para graficar.")

    with clientes_tab:
        filtro = st.text_input("Buscar cliente", key="admin_busqueda")
        clientes_filtrados = [
            cliente for cliente in todos_los_clientes
            if filtro.strip().lower() in cliente["nombre"].lower()
        ]
        st.dataframe(
            [{key: cliente[key] for key in (
                "id", "nombre", "correo", "telefono", "plan", "estado",
                "fecha_registro", "fecha_vencimiento"
            )} for cliente in clientes_filtrados],
            hide_index=True,
            width="stretch",
        )

        with st.expander("Agregar cliente"):
            with st.form("admin_cliente_crear_form"):
                nombre_nuevo_cliente = st.text_input("Nombre", key="nuevo_cliente_nombre")
                correo_nuevo_cliente = st.text_input("Correo", key="nuevo_cliente_correo")
                telefono_nuevo_cliente = st.text_input("Teléfono", key="nuevo_cliente_telefono")
                crear_cliente = st.form_submit_button("Crear cliente", type="primary")
            if crear_cliente:
                resultado = crear_cliente_admin(
                    nombre_nuevo_cliente, correo_nuevo_cliente, telefono_nuevo_cliente
                )
                if resultado["ok"]:
                    st.success("Cliente creado.")
                    st.rerun()
                st.error(resultado["error"])

        cliente_por_id = {cliente["id"]: cliente for cliente in clientes_filtrados}
        seleccion_cliente_editar = st.selectbox(
            "Cliente para editar sus datos",
            [None, *cliente_por_id],
            format_func=lambda value: (
                "Selecciona un cliente" if value is None
                else f"{cliente_por_id[value]['nombre']} · #{value}"
            ),
            key="admin_cliente_editar_id",
        )
        cliente_editar = cliente_por_id.get(seleccion_cliente_editar)
        cliente_key = seleccion_cliente_editar if seleccion_cliente_editar is not None else "ninguno"
        if cliente_editar:
            with st.form("admin_cliente_editar_form"):
                nombre_cliente_editado = st.text_input(
                    "Nombre",
                    value=cliente_editar["nombre"],
                    key=f"editar_cliente_nombre_{cliente_key}",
                )
                correo_cliente_editado = st.text_input(
                    "Correo",
                    value=cliente_editar["correo"],
                    key=f"editar_cliente_correo_{cliente_key}",
                )
                telefono_cliente_editado = st.text_input(
                    "Teléfono",
                    value=cliente_editar["telefono"],
                    key=f"editar_cliente_telefono_{cliente_key}",
                )
                guardar_datos_cliente = st.form_submit_button("Guardar datos del cliente")

            if guardar_datos_cliente:
                resultado = actualizar_cliente_admin(
                    seleccion_cliente_editar,
                    nombre_cliente_editado,
                    correo_cliente_editado,
                    telefono_cliente_editado,
                )
                if resultado["ok"]:
                    st.success("Datos del cliente actualizados.")
                    st.rerun()
                st.error(resultado["error"])

            if cliente_editar["activo"]:
                with st.form("admin_cliente_baja_form"):
                    confirmar_baja_cliente = st.checkbox(
                        "Confirmo dar de baja este cliente. Si tiene historial, se conservará."
                    )
                    dar_baja_cliente = st.form_submit_button("Eliminar / dar de baja")
                if dar_baja_cliente:
                    if not confirmar_baja_cliente:
                        st.error("Confirma la baja para continuar.")
                    else:
                        resultado = eliminar_cliente_admin(seleccion_cliente_editar)
                        if resultado["ok"]:
                            st.success(f"Cliente {resultado['accion']}.")
                            st.rerun()
                        st.error(resultado["error"])
            else:
                if st.button("Reactivar cliente", key=f"reactivar_cliente_{cliente_key}"):
                    resultado = cambiar_estado_cliente_admin(seleccion_cliente_editar, True)
                    if resultado["ok"]:
                        st.success("Cliente reactivado.")
                        st.rerun()
                    st.error(resultado["error"])

        clientes_activos_filtrados = [
            cliente for cliente in clientes_filtrados if cliente["activo"]
        ]
        if clientes_activos_filtrados and planes_activos:
            cliente_por_id = {
                cliente["id"]: cliente for cliente in clientes_activos_filtrados
            }
            plan_por_id = {plan["id"]: plan for plan in planes_activos}
            with st.form("renovar_membresia_form"):
                cliente_id = st.selectbox(
                    "Cliente",
                    list(cliente_por_id),
                    format_func=lambda value: f"{cliente_por_id[value]['nombre']} · #{value}",
                )
                plan_id = st.selectbox(
                    "Plan",
                    list(plan_por_id),
                    format_func=lambda value: (
                        f"{plan_por_id[value]['nombre']} · ${plan_por_id[value]['precio']:,.0f}"
                    ),
                )
                metodo = st.selectbox(
                    "Método de pago",
                    ["transferencia", "efectivo", "tarjeta presencial"],
                )
                estado_pago = st.selectbox("Estado del pago", ["PENDIENTE", "PAGADO"])
                renovar = st.form_submit_button("Renovar / cambiar plan", type="primary")

            if renovar:
                resultado = registrar_renovacion_admin(
                    cliente_id, plan_id, metodo, estado_pago
                )
                if resultado["ok"]:
                    st.success(
                        f"Renovación registrada desde {resultado['fecha_inicio']:%d/%m/%Y}. "
                        f"Monto: ${resultado['monto']:,.0f}."
                    )
                else:
                    st.error(resultado["error"])
        elif not planes_activos:
            st.info("No hay planes activos en Oracle para asignar.")

    with usuarios_tab:
        st.subheader("Cuentas de acceso")
        st.dataframe(
            [{key: usuario[key] for key in ("id", "nombre", "correo", "rol", "fecha_registro")}
             for usuario in usuarios],
            hide_index=True,
            width="stretch",
        )
        usuario_por_id = {usuario["id"]: usuario for usuario in usuarios}
        seleccion_usuario = st.selectbox(
            "Cuenta para editar",
            [None, *usuario_por_id],
            format_func=lambda value: (
                "Crear cuenta" if value is None
                else f"{usuario_por_id[value]['nombre']} · {usuario_por_id[value]['correo']}"
            ),
            key="admin_usuario_seleccion",
        )
        usuario_actual = usuario_por_id.get(seleccion_usuario)
        usuario_key = seleccion_usuario if seleccion_usuario is not None else "nuevo"
        with st.form("admin_usuario_form"):
            usuario_nombre = st.text_input(
                "Nombre",
                value=usuario_actual["nombre"] if usuario_actual else "",
                key=f"admin_usuario_nombre_{usuario_key}",
            )
            usuario_correo = st.text_input(
                "Correo",
                value=usuario_actual["correo"] if usuario_actual else "",
                key=f"admin_usuario_correo_{usuario_key}",
            )
            roles = ["MIEMBRO", "ADMIN"]
            usuario_rol = st.selectbox(
                "Rol",
                roles,
                index=roles.index(usuario_actual["rol"]) if usuario_actual else 0,
                key=f"admin_usuario_rol_{usuario_key}",
            )
            usuario_password = st.text_input(
                "Contraseña inicial / nueva contraseña",
                type="password",
                help="Obligatoria al crear una cuenta; déjala vacía para conservarla al editar.",
                key=f"admin_usuario_password_{usuario_key}",
            )
            guardar_usuario = st.form_submit_button("Guardar usuario", type="primary")

        if guardar_usuario:
            resultado = guardar_usuario_admin(
                seleccion_usuario,
                usuario_nombre,
                usuario_correo,
                usuario_rol,
                usuario_password,
                st.session_state.usuario["id"],
            )
            if resultado["ok"]:
                st.success("Usuario guardado.")
                st.rerun()
            st.error(resultado["error"])

        usuarios_eliminables = [
            usuario for usuario in usuarios
            if usuario["id"] != st.session_state.usuario["id"]
        ]
        if usuarios_eliminables:
            usuario_para_borrar = st.selectbox(
                "Cuenta para eliminar",
                [usuario["id"] for usuario in usuarios_eliminables],
                format_func=lambda value: (
                    f"{usuario_por_id[value]['nombre']} · {usuario_por_id[value]['correo']}"
                ),
                key="admin_usuario_borrar_id",
            )
            with st.form("admin_usuario_borrar_form"):
                confirmar_borrado_usuario = st.checkbox(
                    "Confirmo eliminar la cuenta y su historial de chat."
                )
                borrar_usuario = st.form_submit_button("Eliminar usuario")
            if borrar_usuario:
                if not confirmar_borrado_usuario:
                    st.error("Confirma la eliminación para continuar.")
                else:
                    resultado = eliminar_usuario_admin(
                        usuario_para_borrar, st.session_state.usuario["id"]
                    )
                    if resultado["ok"]:
                        st.success("Usuario eliminado.")
                        st.rerun()
                    st.error(resultado["error"])

    with planes_tab:
        st.subheader("Catálogo de planes")
        st.dataframe(
            [{key: plan[key] for key in ("id", "nombre", "precio", "duracion", "activo")}
             for plan in planes],
            hide_index=True,
            width="stretch",
        )
        plan_por_id = {plan["id"]: plan for plan in planes}
        seleccion_plan = st.selectbox(
            "Plan para editar",
            [None, *plan_por_id],
            format_func=lambda value: (
                "Crear plan" if value is None
                else f"{plan_por_id[value]['nombre']} · ${plan_por_id[value]['precio']:,.0f}"
            ),
            key="admin_plan_seleccion",
        )
        plan_actual = plan_por_id.get(seleccion_plan)
        plan_key = seleccion_plan if seleccion_plan is not None else "nuevo"
        with st.form("admin_plan_form"):
            plan_nombre = st.text_input(
                "Nombre del plan",
                value=plan_actual["nombre"] if plan_actual else "",
                key=f"admin_plan_nombre_{plan_key}",
            )
            plan_precio = st.number_input(
                "Precio mensual (CLP)",
                min_value=0.0,
                value=plan_actual["precio"] if plan_actual else 1000.0,
                step=1000.0,
                key=f"admin_plan_precio_{plan_key}",
            )
            plan_duracion = st.number_input(
                "Duración (días)",
                min_value=1,
                max_value=3650,
                value=plan_actual["duracion"] if plan_actual else 30,
                step=1,
                key=f"admin_plan_duracion_{plan_key}",
            )
            plan_activo = st.checkbox(
                "Disponible para nuevas inscripciones",
                value=plan_actual["activo"] if plan_actual else True,
                key=f"admin_plan_activo_{plan_key}",
            )
            guardar_plan = st.form_submit_button("Guardar plan", type="primary")

        if guardar_plan:
            resultado = guardar_plan_admin(
                seleccion_plan, plan_nombre, plan_precio, plan_duracion, plan_activo
            )
            if resultado["ok"]:
                st.success("Plan guardado.")
                st.rerun()
            st.error(resultado["error"])

        if planes:
            with st.form("admin_plan_borrar_form"):
                plan_para_borrar = st.selectbox(
                    "Plan para eliminar o desactivar",
                    list(plan_por_id),
                    format_func=lambda value: plan_por_id[value]["nombre"],
                )
                confirmar_borrado_plan = st.checkbox(
                    "Confirmo eliminarlo o desactivarlo si tiene inscripciones."
                )
                borrar_plan = st.form_submit_button("Eliminar / desactivar plan")
            if borrar_plan:
                if not confirmar_borrado_plan:
                    st.error("Confirma la acción para continuar.")
                else:
                    resultado = eliminar_plan_admin(plan_para_borrar)
                    if resultado["ok"]:
                        st.success(f"Plan {resultado['accion']}.")
                        st.rerun()
                    st.error(resultado["error"])

    with solicitudes_tab:
        st.subheader("Solicitudes de clases y sesiones")
        st.dataframe(
            [{
                "ID": solicitud["id"],
                "Cliente": solicitud["cliente"],
                "Servicio": solicitud["servicio"].replace("_", " ").title(),
                "Actividad": solicitud["actividad"],
                "Fecha solicitada": solicitud["fecha"],
                "Estado": solicitud["estado"].replace("_", " ").title(),
                "Incluida": "Sí" if solicitud["incluida"] else "No",
                "Monto": solicitud["monto"],
                "Pago": solicitud["pago_estado"],
                "Método": solicitud["metodo"],
                "Observaciones": solicitud["observaciones"],
            } for solicitud in solicitudes_servicios],
            hide_index=True,
            width="stretch",
        )
        pendientes_servicio = [
            solicitud for solicitud in solicitudes_servicios
            if solicitud["estado"] in {"SOLICITADA", "PENDIENTE_PAGO"}
        ]
        if pendientes_servicio:
            solicitud_por_id = {item["id"]: item for item in pendientes_servicio}
            solicitud_id = st.selectbox(
                "Solicitud para procesar",
                list(solicitud_por_id),
                format_func=lambda value: (
                    f"#{value} · {solicitud_por_id[value]['cliente']} · "
                    f"{solicitud_por_id[value]['servicio'].replace('_', ' ').title()}"
                ),
            )
            solicitud_actual = solicitud_por_id[solicitud_id]
            if solicitud_actual["incluida"]:
                if st.button("Confirmar sesión incluida", key=f"confirmar_sesion_{solicitud_id}"):
                    resultado = gestionar_solicitud_servicio_admin(solicitud_id, "CONFIRMAR")
                    if resultado["ok"]:
                        st.success("Sesión confirmada.")
                        st.rerun()
                    st.error(resultado["error"])
            else:
                st.info("Confirma primero que recibiste el pago de $15.000 CLP.")
                if st.button("Confirmar pago y agendar", key=f"confirmar_pago_sesion_{solicitud_id}"):
                    resultado = gestionar_solicitud_servicio_admin(
                        solicitud_id, "CONFIRMAR_PAGO"
                    )
                    if resultado["ok"]:
                        st.success("Pago confirmado y sesión agendada.")
                        st.rerun()
                    st.error(resultado["error"])
            if st.button("Rechazar solicitud", key=f"rechazar_sesion_{solicitud_id}"):
                resultado = gestionar_solicitud_servicio_admin(solicitud_id, "RECHAZAR")
                if resultado["ok"]:
                    st.success("Solicitud rechazada.")
                    st.rerun()
                st.error(resultado["error"])

    with pagos_tab:
        st.caption("Este panel registra pagos manuales; no realiza cargos a tarjetas.")
        st.dataframe(
            [{key: pago[key] for key in ("id", "cliente", "monto", "metodo", "fecha", "estado")}
             for pago in pagos],
            hide_index=True,
            width="stretch",
        )
        pendientes = [pago for pago in pagos if pago["estado"] == "PENDIENTE"]
        if pendientes:
            pago_por_id = {pago["id"]: pago for pago in pendientes}
            with st.form("confirmar_pago_form"):
                pago_id = st.selectbox(
                    "Pago pendiente",
                    list(pago_por_id),
                    format_func=lambda value: (
                        f"#{value} · {pago_por_id[value]['cliente']} · "
                        f"${pago_por_id[value]['monto']:,.0f}"
                    ),
                )
                confirmar_pago = st.form_submit_button("Confirmar como pagado")
            if confirmar_pago:
                resultado = marcar_pago_pagado(pago_id)
                if resultado["ok"]:
                    st.success("Pago actualizado.")
                else:
                    st.error(resultado["error"])

    with sugerencias_tab:
        st.subheader("Comentarios de la comunidad")
        st.dataframe(
            [{
                "ID": item["id"],
                "Fecha": item["fecha"],
                "Nombre": item["nombre"],
                "Correo": item["correo"],
                "Sugerencia": item["mensaje"],
                "Estado": item["estado"],
            } for item in sugerencias],
            hide_index=True,
            width="stretch",
        )
        sugerencias_pendientes = [item for item in sugerencias if item["estado"] != "RESPONDIDA"]
        if sugerencias_pendientes:
            sugerencia_por_id = {item["id"]: item for item in sugerencias_pendientes}
            sugerencia_id = st.selectbox(
                "Sugerencia para actualizar",
                list(sugerencia_por_id),
                format_func=lambda value: (
                    f"#{value} · {sugerencia_por_id[value]['nombre']} · "
                    f"{sugerencia_por_id[value]['mensaje'][:60]}"
                ),
            )
            estado_sugerencia = st.selectbox(
                "Estado",
                ["NUEVA", "REVISADA", "RESPONDIDA"],
                key="admin_sugerencia_estado",
            )
            if st.button("Actualizar sugerencia", key="guardar_estado_sugerencia"):
                resultado = cambiar_estado_sugerencia_admin(sugerencia_id, estado_sugerencia)
                if resultado["ok"]:
                    st.success("Estado de sugerencia actualizado.")
                    st.rerun()
                st.error(resultado["error"])
        elif not sugerencias:
            st.info("Todavía no hay sugerencias recibidas.")

    with asistente_tab:
        _render_chat()


def _render_member() -> None:
    usuario = st.session_state.usuario
    st.session_state.setdefault("solicitud_form_version", 0)
    st.markdown('<div class="brand-mark">Titan Club / Mi cuenta</div>', unsafe_allow_html=True)
    st.title(f"Hola, {usuario['nombre']}")
    st.caption("Tu membresía, pagos y asistencia en un solo lugar.")

    if not inicializar_esquema_oracle():
        st.error("No se pudo conectar con Oracle para cargar tu cuenta.")
        return

    resultado = obtener_portal_miembro(usuario["correo"])
    if not resultado["ok"]:
        st.error(resultado["error"])
        return

    resumen_tab, membresia_tab, pagos_tab, agendar_tab, solicitudes_tab, asistente_tab = st.tabs(
        ["Resumen", "Mi membresía", "Pagos", "Agendar", "Mis solicitudes", "Asistente"]
    )
    cliente = resultado["cliente"]
    membresia = resultado["membresia"]

    with resumen_tab:
        if cliente is None:
            st.info(
                "Tu cuenta todavía no está vinculada a una ficha de cliente. "
                "Pide a administración que agregue este correo a tu ficha."
            )
            st.metric("Estado", "Sin ficha vinculada")
        else:
            estado = resultado["estado"]
            plan_nombre = membresia["plan"] if membresia else (cliente["plan_actual"] or "Sin plan")
            vencimiento = membresia["vencimiento"] if membresia else None
            dias_restantes = (
                max(0, (vencimiento - date.today()).days)
                if vencimiento and estado == "ACTIVA"
                else None
            )
            estado_col, plan_col, vencimiento_col, dias_col = st.columns(4)
            estado_col.metric("Estado", estado.title())
            plan_col.metric("Plan", plan_nombre.title())
            vencimiento_col.metric(
                "Vencimiento",
                vencimiento.strftime("%d/%m/%Y") if vencimiento else "—",
            )
            dias_col.metric("Días restantes", dias_restantes if dias_restantes is not None else "—")

            if not cliente["activo"]:
                st.warning("Tu ficha figura como dada de baja. Contacta a administración.")
            elif estado == "VENCIDA":
                st.warning("Tu membresía está vencida. Contacta a administración para renovarla.")
            elif estado == "PENDIENTE":
                st.info("Tu renovación está pendiente de confirmación de pago.")

            perfil_col, actividad_col = st.columns(2)
            with perfil_col:
                st.subheader("Mi perfil")
                st.write(f"**Nombre:** {cliente['nombre']}")
                st.write(f"**Correo:** {cliente['correo'] or usuario['correo']}")
                st.write(f"**Teléfono:** {cliente['telefono'] or 'No registrado'}")
            with actividad_col:
                st.subheader("Actividad")
                st.write(f"**Cliente desde:** {cliente['fecha_registro']:%d/%m/%Y}" if cliente["fecha_registro"] else "**Cliente desde:** —")
                st.write(f"**Membresías registradas:** {len(resultado['inscripciones'])}")
                st.write(f"**Pagos registrados:** {len(resultado['pagos'])}")

    with membresia_tab:
        if cliente is None:
            st.info("La información aparecerá cuando administración vincule tu ficha.")
        elif resultado["inscripciones"]:
            st.dataframe(
                [{
                    "Plan": item["plan"],
                    "Estado": item["estado"].title(),
                    "Inicio": item["inicio"],
                    "Vence": item["vencimiento"],
                    "Monto": item["monto"],
                } for item in resultado["inscripciones"]],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Aún no hay membresías asociadas a tu ficha.")

    with pagos_tab:
        if cliente is None:
            st.info("La información aparecerá cuando administración vincule tu ficha.")
        elif resultado["pagos"]:
            st.dataframe(
                [{
                    "Fecha": pago["fecha"],
                    "Monto": pago["monto"],
                    "Método": pago["metodo"],
                    "Estado": pago["estado"].title(),
                } for pago in resultado["pagos"]],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Aún no hay pagos asociados a tu ficha.")

    with agendar_tab:
        confirmacion = st.session_state.get("solicitud_confirmacion")
        if confirmacion:
            st.success(confirmacion["mensaje"])
            if st.button("Ocultar confirmación", key="ocultar_confirmacion_solicitud"):
                st.session_state.pop("solicitud_confirmacion", None)
                st.rerun()

        if cliente is None:
            st.info("Pide a administración que vincule tu ficha para solicitar sesiones.")
        elif not cliente["activo"]:
            st.warning("Tu ficha está inactiva. Contacta a administración para agendar.")
        else:
            nombres_servicios = {
                "NUTRICIONISTA": "Nutricionista",
                "CLASE_GRUPAL": "Clase grupal",
                "ENTRENADOR_PERSONAL": "Entrenador personal",
                "EVALUACION_FISICA": "Evaluación física",
            }
            form_version = st.session_state["solicitud_form_version"]
            servicio = st.selectbox(
                "Tipo de sesión",
                list(nombres_servicios),
                format_func=lambda value: nombres_servicios[value],
                key=f"miembro_servicio_tipo_{form_version}",
            )
            fecha_servicio = st.date_input(
                "Fecha preferida",
                value=date.today() + timedelta(days=1),
                min_value=date.today(),
                key=f"miembro_servicio_fecha_{form_version}",
            )
            hora_servicio = st.time_input(
                "Hora preferida", key=f"miembro_servicio_hora_{form_version}"
            )
            actividad = st.text_input(
                "Clase o especialidad (opcional)",
                placeholder="Yoga, spinning, alimentación deportiva...",
                key=f"miembro_servicio_actividad_{form_version}",
            )
            observaciones = st.text_area(
                "Comentario para el profesional (opcional)",
                max_chars=500,
                key=f"miembro_servicio_observaciones_{form_version}",
            )
            metodo_pago_sesion = st.selectbox(
                "Método para pagar extras",
                ["transferencia", "efectivo", "tarjeta presencial"],
                key=f"miembro_servicio_metodo_pago_{form_version}",
            )
            fecha_hora = datetime.combine(fecha_servicio, hora_servicio)
            cotizacion = cotizar_solicitud_miembro(
                usuario["correo"], servicio, fecha_hora
            )
            if cotizacion["ok"]:
                if cotizacion["incluida"]:
                    st.success(
                        f"Incluida en tu plan {cotizacion['plan'].title()}: $0 CLP. "
                        "Administración confirmará el horario."
                    )
                else:
                    st.info(
                        f"Sesión adicional: $15.000 CLP. Se agenda cuando se confirme el pago."
                    )
            else:
                st.warning(cotizacion["error"])

            if st.button(
                "Solicitar sesión",
                type="primary",
                key=f"enviar_solicitud_servicio_{form_version}",
            ):
                resultado = solicitar_servicio_miembro(
                    usuario["correo"],
                    servicio,
                    fecha_hora,
                    actividad,
                    observaciones,
                    metodo_pago_sesion,
                )
                if resultado["ok"]:
                    if resultado.get("duplicada"):
                        mensaje = (
                            f"Esta solicitud ya estaba enviada (#{resultado['solicitud_id']}). "
                            "No se creó otra solicitud ni otro cobro."
                        )
                    elif resultado["incluida"]:
                        mensaje = (
                            f"Solicitud #{resultado['solicitud_id']} enviada. "
                            "Administración confirmará el horario."
                        )
                    else:
                        mensaje = (
                            f"Solicitud #{resultado['solicitud_id']} enviada por "
                            f"${resultado['monto']:,.0f} CLP. Quedará agendada al confirmar el pago."
                        )
                    st.session_state["solicitud_confirmacion"] = {"mensaje": mensaje}
                    st.session_state["solicitud_form_version"] = form_version + 1
                    st.rerun()
                st.error(resultado["error"])

    with solicitudes_tab:
        solicitudes = resultado.get("solicitudes", [])
        if cliente is None:
            st.info("Vincula tu ficha de cliente para ver tus solicitudes.")
        elif solicitudes:
            st.dataframe(
                [{
                    "Servicio": item["servicio"].replace("_", " ").title(),
                    "Actividad": item["actividad"],
                    "Fecha solicitada": item["fecha"],
                    "Estado": item["estado"].replace("_", " ").title(),
                    "Incluida": "Sí" if item["incluida"] else "No",
                    "Monto": item["monto"],
                    "Pago": item["pago_estado"],
                } for item in solicitudes],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Aún no has solicitado clases o sesiones.")

    with asistente_tab:
        _render_chat()


if st.session_state.usuario.get("rol") == "ADMIN":
    _render_admin()
else:
    _render_member()