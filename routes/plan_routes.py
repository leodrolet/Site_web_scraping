"""plan_routes.py — Page « Mon abonnement » : plan actuel, usage du mois, plans."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import plans
from auth import exiger_connexion
from database import Utilisateur, get_db
from templating import rendre

router = APIRouter()


@router.get("/abonnement")
def page_abonnement(request: Request,
                    utilisateur: Utilisateur = Depends(exiger_connexion),
                    db: Session = Depends(get_db)):
    etat = plans.etat_quota(db, utilisateur)
    return rendre(request, "abonnement.html", utilisateur=utilisateur,
                  quota=etat, plans=plans.liste_plans(),
                  plan_actuel=etat["plan"]["cle"])
