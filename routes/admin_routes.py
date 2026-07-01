"""
admin_routes.py — Panneau d'administration (réservé aux comptes admin=True).

Fournit :
  GET  /admin                          -> tableau de bord (stats + liste des comptes)
  POST /admin/utilisateur/{id}/actif   -> activer / désactiver un compte
  POST /admin/utilisateur/{id}/plan    -> changer le plan d'un compte

Accès protégé par la dépendance `exiger_admin` (redirige les non-admins).
Toutes les actions POST valident le jeton CSRF.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import config
import plans
from auth import exiger_admin, valider_csrf
from database import HistoriqueRecherche, Utilisateur, get_db
from templating import rendre

router = APIRouter()


def _stats(db: Session) -> dict:
    """Chiffres clés pour l'en-tête du tableau de bord."""
    total = db.query(Utilisateur).count()
    actifs = db.query(Utilisateur).filter(Utilisateur.actif.is_(True)).count()
    recherches = db.query(HistoriqueRecherche).count()
    par_plan = {cle: 0 for cle in plans.PLANS}
    for (plan_cle,) in db.query(Utilisateur.plan).all():
        cle = (plan_cle or plans.PLAN_DEFAUT).lower()
        par_plan[cle] = par_plan.get(cle, 0) + 1
    return {"total": total, "actifs": actifs, "inactifs": total - actifs,
            "recherches": recherches, "par_plan": par_plan}


def _lignes_utilisateurs(db: Session) -> list:
    """Liste des comptes enrichie du nombre de recherches faites ce mois-ci."""
    lignes = []
    for u in db.query(Utilisateur).order_by(Utilisateur.date_creation.desc()).all():
        lignes.append({
            "u": u,
            "utilisees_mois": plans.recherches_ce_mois(db, u.id),
            "plan_infos": plans.infos_plan(u.plan),
        })
    return lignes


@router.get("/admin")
def page_admin(request: Request,
              admin: Utilisateur = Depends(exiger_admin),
              db: Session = Depends(get_db)):
    return rendre(request, "admin.html", utilisateur=admin,
                  stats=_stats(db),
                  utilisateurs=_lignes_utilisateurs(db),
                  plans=plans.liste_plans(),
                  apis=config.statut_apis(),
                  moi=admin.id)


@router.post("/admin/utilisateur/{uid}/actif")
def basculer_actif(uid: int, request: Request,
                  csrf_token: str = Form(""),
                  admin: Utilisateur = Depends(exiger_admin),
                  db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return RedirectResponse("/admin", status_code=303)

    cible = db.query(Utilisateur).filter(Utilisateur.id == uid).first()
    # Sécurité : un admin ne peut pas se désactiver lui-même (risque de lock-out).
    if cible and cible.id != admin.id:
        cible.actif = not cible.actif
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/utilisateur/{uid}/plan")
def changer_plan(uid: int, request: Request,
                plan: str = Form(...),
                csrf_token: str = Form(""),
                admin: Utilisateur = Depends(exiger_admin),
                db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return RedirectResponse("/admin", status_code=303)

    # N'accepte qu'une clé de plan connue (gratuit / pro / business).
    if plan not in plans.PLANS:
        return RedirectResponse("/admin", status_code=303)

    cible = db.query(Utilisateur).filter(Utilisateur.id == uid).first()
    if cible:
        cible.plan = plan
        db.commit()
    return RedirectResponse("/admin", status_code=303)
