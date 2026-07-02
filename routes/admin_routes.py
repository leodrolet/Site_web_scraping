"""
admin_routes.py — Panneau d'administration (réservé aux comptes admin=True).

Vue d'ensemble :
  GET  /admin                              -> tableau de bord (stats + comptes)
  GET  /admin/utilisateur/{id}             -> fiche détaillée d'un compte
  POST /admin/utilisateur/{id}/actif       -> activer / désactiver
  POST /admin/utilisateur/{id}/plan        -> changer le plan
  POST /admin/utilisateur/{id}/admin       -> promouvoir / rétrograder admin
  POST /admin/utilisateur/{id}/profil      -> modifier nom / courriel
  POST /admin/utilisateur/{id}/motdepasse  -> réinitialiser le mot de passe
  POST /admin/utilisateur/{id}/supprimer   -> supprimer le compte

Accès protégé par `exiger_admin`. Toutes les actions POST valident le CSRF.
Garde-fous anti-verrouillage : un admin ne peut ni se désactiver, ni se
rétrograder, ni se supprimer lui-même.
"""

import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import config
import plans
from auth import exiger_admin, hasher_mot_de_passe, valider_csrf
from database import HistoriqueRecherche, Utilisateur, get_db
from templating import rendre

router = APIRouter()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
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


def _cible(db: Session, uid: int):
    return db.query(Utilisateur).filter(Utilisateur.id == uid).first()


def _redir(uid: int, retour: str) -> RedirectResponse:
    """Redirection interne : vers la fiche si `retour == 'detail'`, sinon la liste."""
    if retour == "detail":
        return RedirectResponse(f"/admin/utilisateur/{uid}", status_code=303)
    return RedirectResponse("/admin", status_code=303)


def _contexte_detail(db: Session, admin: Utilisateur, cible: Utilisateur, **extra) -> dict:
    """Contexte de la fiche détaillée d'un compte."""
    historique = (db.query(HistoriqueRecherche)
                  .filter(HistoriqueRecherche.utilisateur_id == cible.id)
                  .order_by(HistoriqueRecherche.date.desc()).limit(15).all())
    ctx = dict(
        cible=cible,
        plans=plans.liste_plans(),
        plan_infos=plans.infos_plan(cible.plan),
        usage=plans.etat_quota(db, cible),
        recherches_total=db.query(HistoriqueRecherche)
            .filter(HistoriqueRecherche.utilisateur_id == cible.id).count(),
        historique=historique,
        moi=admin.id,
    )
    ctx.update(extra)
    return ctx


# ----------------------------------------------------------------------
# Tableau de bord
# ----------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# Fiche détaillée d'un compte
# ----------------------------------------------------------------------
@router.get("/admin/utilisateur/{uid}")
def page_utilisateur(uid: int, request: Request,
                    admin: Utilisateur = Depends(exiger_admin),
                    db: Session = Depends(get_db)):
    cible = _cible(db, uid)
    if not cible:
        return RedirectResponse("/admin", status_code=303)
    return rendre(request, "admin_utilisateur.html", utilisateur=admin,
                  **_contexte_detail(db, admin, cible))


# ----------------------------------------------------------------------
# Actions
# ----------------------------------------------------------------------
@router.post("/admin/utilisateur/{uid}/actif")
def basculer_actif(uid: int, request: Request,
                  csrf_token: str = Form(""),
                  retour: str = Form(""),
                  admin: Utilisateur = Depends(exiger_admin),
                  db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return _redir(uid, retour)
    cible = _cible(db, uid)
    # Sécurité : un admin ne peut pas se désactiver lui-même (risque de lock-out).
    if cible and cible.id != admin.id:
        cible.actif = not cible.actif
        db.commit()
    return _redir(uid, retour)


@router.post("/admin/utilisateur/{uid}/plan")
def changer_plan(uid: int, request: Request,
                plan: str = Form(...),
                csrf_token: str = Form(""),
                retour: str = Form(""),
                admin: Utilisateur = Depends(exiger_admin),
                db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return _redir(uid, retour)
    # N'accepte qu'une clé de plan connue (gratuit / pro / business).
    if plan not in plans.PLANS:
        return _redir(uid, retour)
    cible = _cible(db, uid)
    if cible:
        cible.plan = plan
        db.commit()
    return _redir(uid, retour)


@router.post("/admin/utilisateur/{uid}/admin")
def basculer_admin(uid: int, request: Request,
                  csrf_token: str = Form(""),
                  retour: str = Form(""),
                  admin: Utilisateur = Depends(exiger_admin),
                  db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return _redir(uid, retour)
    cible = _cible(db, uid)
    # Sécurité : un admin ne peut pas se rétrograder lui-même (risque de lock-out).
    if cible and cible.id != admin.id:
        cible.admin = not cible.admin
        db.commit()
    return _redir(uid, retour)


@router.post("/admin/utilisateur/{uid}/profil")
def modifier_profil(uid: int, request: Request,
                   nom: str = Form(""),
                   email: str = Form(...),
                   csrf_token: str = Form(""),
                   admin: Utilisateur = Depends(exiger_admin),
                   db: Session = Depends(get_db)):
    cible = _cible(db, uid)
    if not cible:
        return RedirectResponse("/admin", status_code=303)

    def echec(message):
        return rendre(request, "admin_utilisateur.html", utilisateur=admin,
                      **_contexte_detail(db, admin, cible, erreur=message))

    if not valider_csrf(request, csrf_token):
        return echec("Session expirée, merci de réessayer.")

    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return echec("Adresse courriel invalide.")
    # Unicité du courriel (hors compte courant).
    existant = (db.query(Utilisateur)
                .filter(Utilisateur.email == email, Utilisateur.id != uid).first())
    if existant:
        return echec("Un autre compte utilise déjà ce courriel.")

    cible.email = email
    cible.nom = (nom or "").strip() or None
    db.commit()
    db.refresh(cible)
    return rendre(request, "admin_utilisateur.html", utilisateur=admin,
                  **_contexte_detail(db, admin, cible,
                                     succes="Profil mis à jour."))


@router.post("/admin/utilisateur/{uid}/motdepasse")
def reinitialiser_mot_de_passe(uid: int, request: Request,
                              csrf_token: str = Form(""),
                              admin: Utilisateur = Depends(exiger_admin),
                              db: Session = Depends(get_db)):
    cible = _cible(db, uid)
    if not cible:
        return RedirectResponse("/admin", status_code=303)
    if not valider_csrf(request, csrf_token):
        return rendre(request, "admin_utilisateur.html", utilisateur=admin,
                      **_contexte_detail(db, admin, cible,
                                         erreur="Session expirée, merci de réessayer."))

    # Mot de passe temporaire aléatoire, affiché UNE fois (jamais stocké en clair).
    temporaire = secrets.token_urlsafe(9)
    cible.mot_de_passe_hash = hasher_mot_de_passe(temporaire)
    db.commit()
    return rendre(request, "admin_utilisateur.html", utilisateur=admin,
                  **_contexte_detail(db, admin, cible,
                                     mot_de_passe_temporaire=temporaire))


@router.post("/admin/utilisateur/{uid}/supprimer")
def supprimer_utilisateur(uid: int, request: Request,
                         csrf_token: str = Form(""),
                         admin: Utilisateur = Depends(exiger_admin),
                         db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return RedirectResponse("/admin", status_code=303)
    cible = _cible(db, uid)
    # Sécurité : pas d'auto-suppression. La cascade retire aussi son historique.
    if cible and cible.id != admin.id:
        db.delete(cible)
        db.commit()
    return RedirectResponse("/admin", status_code=303)
