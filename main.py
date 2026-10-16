import os

from src.gym.agent import agente_gym

try:
    from google.colab import userdata  # type: ignore

    api_key = userdata.get("GROQ_API_KEY")
    if api_key:
        os.environ.setdefault("GROQ_API_KEY", api_key)
except Exception:
    pass

__all__ = ["agente_gym"]

if __name__ == "__main__":
    from langchain_core.messages import HumanMessage, AIMessage

    historial_conversacion = []
    print("=" * 65)
    print("🏋️  ¡Bienvenido al Asistente Virtual de Gimnasio Titan Club!  🏋️")
    print("Puedes consultar precios, máquinas, promociones o inscribirte.")
    print("Escribe 'salir' o 'terminar' para finalizar la sesión de chat.")
    print("=" * 65)

    while True:
        try:
            user_input = input("\n🧑 Tú: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["salir", "exit", "terminar", "chao", "adios"]:
                print("\n🤖 TitanBot: ¡Muchas gracias por tu visita! Te esperamos pronto en Titan Club para entrenar. 💪")
                break

            respuesta = agente_gym.invoke({
                "input": user_input,
                "chat_history": historial_conversacion,
            })["output"]

            historial_conversacion.append(HumanMessage(content=user_input))
            historial_conversacion.append(AIMessage(content=respuesta))

            print(f"\n🤖 TitanBot: {respuesta}")

        except KeyboardInterrupt:
            print("\n\nSesión detenida.")
            break
        except Exception as exc:
            print(f"\n⚠️ Ocurrió un error inesperado: {exc}")