"""settings_routes.py — Page « Paramètres » : clés API de l'utilisateur."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import chiffrer, exiger_connexion, valider_csrf
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
    # On n'envoie JAMAIS la clé déchiffrée au navigateur : seulement l'info
    # « une clé est enregistrée ou non » (booléen). Les champs restent vides.
    return rendre(request, "parametres.html", utilisateur=utilisateur,
                  hunter=bool(cles.hunter_key),
                  apollo=bool(cles.apollo_key),
                  serpapi=bool(cles.serpapi_key),
                  bienvenue=bool(bienvenue), sauvegarde=bool(sauvegarde))


@router.post("/parametres")
def sauver_parametres(request: Request,
                     hunter: str = Form(""),
                     apollo: str = Form(""),
                     serpapi: str = Form(""),
                     csrf_token: str = Form(""),
                     utilisateur: Utilisateur = Depends(exiger_connexion),
                     db: Session = Depends(get_db)):
    cles = _obtenir_cles(db, utilisateur)

    if not valider_csrf(request, csrf_token):
        return rendre(request, "parametres.html", utilisateur=utilisateur,
                      hunter=bool(cles.hunter_key), apollo=bool(cles.apollo_key),
                      serpapi=bool(cles.serpapi_key),
                      erreur="Session expirée, merci de réessayer.")

    # Un champ laissé vide conserve la clé déjà enregistrée (évite d'effacer
    # une clé par mégarde). Seuls les champs renseignés sont mis à jour.
    if hunter.strip():
        cles.hunter_key = chiffrer(hunter)
    if apollo.strip():
        cles.apollo_key = chiffrer(apollo)
    if serpapi.strip():
        cles.serpapi_key = chiffrer(serpapi)
    db.commit()

    return RedirectResponse("/parametres?sauvegarde=1", status_code=303)
