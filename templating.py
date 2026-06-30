"""templating.py — Configuration Jinja2 et helper de rendu (injecte le jeton CSRF)."""

from fastapi.templating import Jinja2Templates

from auth import NOM_COOKIE_CSRF, DUREE_SESSION, generer_csrf

templates = Jinja2Templates(directory="templates")


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
                       samesite="lax", secure=False)
    return reponse
