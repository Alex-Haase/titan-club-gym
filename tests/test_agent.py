from src.gym import agent


def test_chatbot_uses_oracle_prices_and_live_memberships(monkeypatch):
    monkeypatch.setattr(
        agent,
        "obtener_precios_planes",
        lambda: {"cobre": 30000, "plata": 55000, "oro": 80000},
    )
    monkeypatch.setattr(
        agent,
        "obtener_membresias_activas_por_plan",
        lambda: {"cobre": 2, "plata": 1, "oro": 1},
    )

    plans = agent.consultar_planes.invoke({})
    oro = agent.detalle_plan.invoke({"plan": "oro"})

    assert "$30,000 CLP/mes" in plans
    assert "$55,000 CLP/mes" in plans
    assert "$80,000 CLP" in oro
    assert "9 de 10" in oro
    assert "dólar" not in plans.lower()
    assert "usd" not in oro.lower()


def test_chatbot_enrollment_charges_price_from_oracle(monkeypatch):
    enrollment = {}
    monkeypatch.setattr(
        agent,
        "obtener_precios_planes",
        lambda: {"cobre": 30000, "plata": 55000, "oro": 80000},
    )
    monkeypatch.setattr(agent, "obtener_membresias_activas_por_plan", lambda: {})
    monkeypatch.setattr(agent, "obtener_plan_vigente_cliente", lambda nombre: None)

    def save_enrollment(nombre, plan, monto, metodo):
        enrollment.update(nombre=nombre, plan=plan, monto=monto, metodo=metodo)
        return {"ok": True}

    monkeypatch.setattr(agent, "registrar_flujo_oracle", save_enrollment)
    monkeypatch.setattr(agent, "obtener_membresias_activas_por_plan", lambda: {})

    response = agent.inscribir_cliente.invoke({
        "nombre_cliente": "Cliente de prueba",
        "plan": "oro",
        "confirmacion": True,
    })

    assert enrollment["monto"] == 80000.0
    assert "$80,000 CLP" in response


def test_chatbot_does_not_enroll_when_oracle_price_is_missing(monkeypatch):
    monkeypatch.setattr(agent, "obtener_precios_planes", lambda: {})
    monkeypatch.setattr(
        agent,
        "registrar_flujo_oracle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not enroll")),
    )

    response = agent.inscribir_cliente.invoke({
        "nombre_cliente": "Cliente de prueba",
        "plan": "oro",
        "confirmacion": True,
    })

    assert "precio vigente" in response.lower()


def test_chatbot_does_not_enroll_when_stock_cannot_be_verified(monkeypatch):
    monkeypatch.setattr(
        agent,
        "obtener_precios_planes",
        lambda: {"cobre": 30000, "plata": 55000, "oro": 80000},
    )
    monkeypatch.setattr(
        agent,
        "obtener_membresias_activas_por_plan",
        lambda: (_ for _ in ()).throw(RuntimeError("Oracle unavailable")),
    )
    monkeypatch.setattr(
        agent,
        "registrar_flujo_oracle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not enroll")),
    )

    response = agent.inscribir_cliente.invoke({
        "nombre_cliente": "Cliente de prueba",
        "plan": "oro",
        "confirmacion": True,
    })

    assert "No puedo confirmar los cupos actuales" in response


def test_chatbot_requires_explicit_enrollment_confirmation(monkeypatch):
    monkeypatch.setattr(
        agent,
        "obtener_precios_planes",
        lambda: {"cobre": 30000, "plata": 55000, "oro": 80000},
    )
    monkeypatch.setattr(
        agent,
        "registrar_flujo_oracle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not enroll")),
    )

    response = agent.inscribir_cliente.invoke({
        "nombre_cliente": "Cliente de prueba",
        "plan": "oro",
    })

    assert "¿Confirmas que la envíe?" in response