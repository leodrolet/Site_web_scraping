"""public.py — Pages publiques (pas de connexion requise)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import utilisateur_actuel
from database import get_db
from templating import rendre

router = APIRouter()


@router.get("/")
def accueil(request: Request, db: Session = Depends(get_db)):
    utilisateur = utilisateur_actuel(request, db)
    # Vérification de session NON bloquante : un visiteur connecté est envoyé
    # directement vers l'outil (comme /login et /inscription) ; un visiteur
    # anonyme voit la page de présentation.
    if utilisateur is not None:
        return RedirectResponse("/app", status_code=303)
    return rendre(request, "accueil.html", utilisateur=utilisateur)


@router.get("/tarifs")
def tarifs():
    # Les plans ne sont plus affichés : l'ancienne page renvoie vers l'accueil.
    # 302 (et non 301) : la cible pourra redevenir une vraie page de tarifs
    # sans être coincée dans le cache navigateur.
    return RedirectResponse("/", status_code=302)


@router.get("/confidentialite")
def confidentialite(request: Request, db: Session = Depends(get_db)):
    utilisateur = utilisateur_actuel(request, db)
    return rendre(request, "confidentialite.html", utilisateur=utilisateur)


@router.get("/mentions-legales")
def mentions_legales(request: Request, db: Session = Depends(get_db)):
    utilisateur = utilisateur_actuel(request, db)
    return rendre(request, "mentions-legales.html", utilisateur=utilisateur)
