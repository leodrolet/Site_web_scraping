"""public.py — Pages publiques (pas de connexion requise)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import plans
from auth import utilisateur_actuel
from database import get_db
from templating import rendre

router = APIRouter()


@router.get("/")
def accueil(request: Request, db: Session = Depends(get_db)):
    utilisateur = utilisateur_actuel(request, db)
    return rendre(request, "accueil.html", utilisateur=utilisateur,
                  plans=plans.liste_plans())


@router.get("/confidentialite")
def confidentialite(request: Request, db: Session = Depends(get_db)):
    utilisateur = utilisateur_actuel(request, db)
    return rendre(request, "confidentialite.html", utilisateur=utilisateur)
