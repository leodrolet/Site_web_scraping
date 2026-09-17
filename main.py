"""
main.py — Serveur FastAPI : charge la configuration, assemble les routes,
les fichiers statiques et la base de données.

Lancer avec :  uvicorn main:app --reload
"""

import os

from dotenv import load_dotenv

load_dotenv()  # IMPORTANT : charge SECRET_KEY avant l'import de `auth`.

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from fastapi.exception_handlers import http_exception_handler  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from auth import (RedirectionConfirmation, RedirectionConnexion,  # noqa: E402
                  RedirectionNonAutorise, utilisateur_actuel)
from database import SessionLocal, init_db  # noqa: E402
from routes import (admin_routes, app_routes, auth_routes,  # noqa: E402
                    mandat_routes, plan_routes, public)
from templating import rendre  # noqa: E402
from routes import mandat_documents_routes  # noqa: E402,F401 enregistre les routes du même routeur protégé

app = FastAPI(title="Outil de prospection B2B")

# En production (HTTPS : Vercel ou COOKIE_SECURE), on ajoute HSTS.
_EN_PROD = bool(os.getenv("VERCEL")) or (
    os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes", "on"))

# Politique de sécurité du contenu : autorise nos propres assets, les polices
# Google (CSS + fichiers), le style inline (attributs style=") et les images
# data: (flèche des <select>). Aucun script externe ni inline n'est autorisé.
_CSP = (
    "default-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
    "font-src https://fonts.gstatic.com; "
    "script-src 'self'; "
    "img-src 'self' data:; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
)


@app.middleware("http")
async def entetes_securite(request, call_next):
    """Ajoute les en-têtes de sécurité à chaque réponse."""
    reponse = await call_next(request)
    reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
    reponse.headers.setdefault("X-Frame-Options", "DENY")
    reponse.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    reponse.headers.setdefault("Permissions-Policy",
                               "geolocation=(), microphone=(), camera=()")
    reponse.headers.setdefault("Content-Security-Policy", _CSP)
    if _EN_PROD:
        reponse.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return reponse


# Crée les tables SQLite au démarrage (idempotent).
init_db()

app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
          name="static")


@app.exception_handler(RedirectionConnexion)
async def _rediriger_vers_login(request, exc):
    """Quand une route protégée est appelée sans session -> redirection login."""
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(RedirectionNonAutorise)
async def _rediriger_vers_app(request, exc):
    """Quand un non-admin appelle une route /admin -> retour à l'outil."""
    return RedirectResponse("/app", status_code=303)


@app.exception_handler(RedirectionConfirmation)
async def _rediriger_vers_confirmation(request, exc):
    """Utilisateur connecté mais email non confirmé -> page d'attente."""
    return RedirectResponse("/confirmation-requise", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def _page_introuvable(request, exc):
    """404 : page stylée cohérente avec le site, au lieu du JSON FastAPI
    ({"detail": "Not Found"}) qui expose le backend. Les autres codes gardent
    le comportement FastAPI par défaut."""
    if exc.status_code != 404:
        return await http_exception_handler(request, exc)
    # `utilisateur` sert uniquement à afficher la bonne barre de navigation.
    db = SessionLocal()
    try:
        utilisateur = utilisateur_actuel(request, db)
    except Exception:
        utilisateur = None
    finally:
        db.close()
    reponse = rendre(request, "404.html", utilisateur=utilisateur)
    reponse.status_code = 404
    return reponse


app.include_router(public.router)
app.include_router(auth_routes.router)
app.include_router(app_routes.router)
app.include_router(mandat_routes.router)
app.include_router(mandat_routes.legacy_router)
app.include_router(plan_routes.router)
app.include_router(admin_routes.router)
