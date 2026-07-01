"""templating.py — Configuration Jinja2 et helper de rendu (injecte le jeton CSRF)."""

import os

from fastapi.templating import Jinja2Templates

from auth import COOKIE_SECURE, NOM_COOKIE_CSRF, DUREE_SESSION, generer_csrf

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def rendre(request, nom_template, utilisateur=None, **contexte):
    """Rend un template en injectant `utilisateur` et `csrf_token`, et en
    posant (ou réutilisant) le cookie CSRF correspondant."""
    jeton_csrf = request.cookies.get(NOM_COOKIE_CSRF) or generer_csrf()

    donnees = {
        "request": request,
        "utilisateur": utilisateur,
        "csrf_token": jeton_csrf,
    }
    donnees.update(contexte)

    reponse = templates.TemplateResponse(request=request, name=nom_template,
                                         context=donnees)
    reponse.set_cookie(NOM_COOKIE_CSRF, jeton_csrf,
                       max_age=DUREE_SESSION, httponly=True,
                       samesite="lax", secure=COOKIE_SECURE)
    return reponse
