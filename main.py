"""
main.py — Serveur FastAPI : charge la configuration, assemble les routes,
les fichiers statiques et la base de données.

Lancer avec :  uvicorn main:app --reload
"""

from dotenv import load_dotenv

load_dotenv()  # IMPORTANT : charge SECRET_KEY avant l'import de `auth`.

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from auth import RedirectionConnexion  # noqa: E402
from database import init_db  # noqa: E402
from routes import app_routes, auth_routes, public, settings_routes  # noqa: E402

app = FastAPI(title="Outil de prospection B2B")

# Crée les tables SQLite au démarrage (idempotent).
init_db()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(RedirectionConnexion)
async def _rediriger_vers_login(request, exc):
    """Quand une route protégée est appelée sans session -> redirection login."""
    return RedirectResponse("/login", status_code=303)


app.include_router(public.router)
app.include_router(auth_routes.router)
app.include_router(app_routes.router)
app.include_router(settings_routes.router)
