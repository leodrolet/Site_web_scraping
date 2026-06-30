"""settings_routes.py — Page « Paramètres » : clés API de l'utilisateur."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import chiffrer, dechiffrer, exiger_connexion, valider_csrf
from database import ClesAPI, Utilisateur, get_db
from templating import rendre

router = APIRouter()


def _obtenir_cles(db: Session, utilisateur: Utilisateur) -> ClesAPI:
    cles = db.query(ClesAPI).filter(
        ClesAPI.utilisateur_id == utilisateur.id).first()
    if cles is None:
        cles = ClesAPI(utilisateur_id=utilisateur.id)
        db.add(cles)
        db.commit()
        db.refresh(cles)
    return cles


@router.get("/parametres")
def page_parametres(request: Request, bienvenue: int = 0, sauvegarde: int = 0,
                   utilisateur: Utilisateur = Depends(exiger_connexion),
                   db: Session = Depends(get_db)):
    cles = _obtenir_cles(db, utilisateur)
    return rendre(request, "parametres.html", utilisateur=utilisateur,
                  hunter=dechiffrer(cles.hunter_key),
                  apollo=dechiffrer(cles.apollo_key),
                  serpapi=dechiffrer(cles.serpapi_key),
                  bienvenue=bool(bienvenue), sauvegarde=bool(sauvegarde))


@router.post("/parametres")
def sauver_parametres(request: Request,
                     hunter: str = Form(""),
                     apollo: str = Form(""),
                     serpapi: str = Form(""),
                     csrf_token: str = Form(""),
                     utilisateur: Utilisateur = Depends(exiger_connexion),
                     db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return rendre(request, "parametres.html", utilisateur=utilisateur,
                      hunter=hunter, apollo=apollo, serpapi=serpapi,
                      erreur="Session expirée, merci de réessayer.")

    cles = _obtenir_cles(db, utilisateur)
    cles.hunter_key = chiffrer(hunter)
    cles.apollo_key = chiffrer(apollo)
    cles.serpapi_key = chiffrer(serpapi)
    db.commit()

    return RedirectResponse("/parametres?sauvegarde=1", status_code=303)
