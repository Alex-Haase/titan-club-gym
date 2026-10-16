# Titan Club

Asistente y portal de miembros para el gimnasio Titan Club. La aplicación usa Streamlit y Oracle Database.

## Ejecutar localmente

1. Crea un entorno virtual e instala dependencias:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copia `.env.example` a `.env` y completa las credenciales localmente. No subas `.env` a GitHub.

3. Inicia la aplicación:

   ```powershell
   streamlit run app.py
   ```

## Publicar el código en GitHub

Usa un repositorio **privado**. El archivo `.gitignore` excluye `.env`, las credenciales de Streamlit, los entornos virtuales y las cachés.

Para publicar la aplicación en un servicio de hosting, configura allí estas variables como secretos: `GROQ_API_KEY`, `GYM_ADMIN_EMAILS`, `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`, `ORACLE_USER` y `ORACLE_PASSWORD`. El servidor de hosting también debe tener acceso de red a Oracle.

GitHub guarda el código, pero no ejecuta la aplicación. Para usarla desde otros dispositivos con tu computadora apagada, necesitas desplegarla en un servicio de hosting.