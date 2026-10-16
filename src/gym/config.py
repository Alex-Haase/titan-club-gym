import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google.colab import userdata  # type: ignore
    api_key = userdata.get("GROQ_API_KEY")
    if api_key:
        os.environ.setdefault("GROQ_API_KEY", api_key)
except Exception:
    pass

MODELO = "openai/gpt-oss-20b"

if not os.getenv("GROQ_API_KEY"):
    raise SystemExit(
        "Falta GROQ_API_KEY. Configúrala como variable de entorno o en un archivo .env."
    )
