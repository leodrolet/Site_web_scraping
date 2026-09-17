"""
plan_routes.py — Page « Mon compte » (/abonnement).

Regroupe : identité du compte, usage du mois (avec date de réinitialisation),
relevé d'activité paginé, et changement de mot de passe (utilisateur déjà
connecté — pas d'envoi d'email). Les plans ne sont plus affichés sur le site ;
ils servent uniquement de quotas côté serveur (voir plans.py).
"""

import json
from datetime import datetime, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import plans
from auth import (exiger_connexion, hasher_mot_de_passe, valider_csrf,
                 verifier_mot_de_passe)
from database import DossierRecherche, HistoriqueRecherche, Utilisateur, get_db
from templating import rendre

router = APIRouter()

HISTORIQUE_PAR_PAGE = 10
HISTORIQUE_JOURS = 90  # relevé d'activité : ~3 derniers mois

_MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre"]


def _mois_annee_fr(d):
    return f"{_MOIS_FR[d.month - 1]} {d.year}"


def _jour_mois_fr(d):
    return f"{d.day} {_MOIS_FR[d.month - 1]} {d.year}"


def _debut_mois_suivant():
    n = datetime.utcnow()
    return datetime(n.year + 1, 1, 1) if n.month == 12 else datetime(n.year, n.month + 1, 1)


def _contexte_abonnement(db, utilisateur, page=1, **extra):
    """Contexte complet de la page « Mon compte »."""
    etat = plans.etat_quota(db, utilisateur)

    depuis = datetime.utcnow() - timedelta(days=HISTORIQUE_JOURS)
    base = (db.query(HistoriqueRecherche)
            .filter(HistoriqueRecherche.utilisateur_id == utilisateur.id,
                    HistoriqueRecherche.date >= depuis)
            .order_by(HistoriqueRecherche.date.desc()))
    total = base.count()
    nb_pages = max(1, ceil(total / HISTORIQUE_PAR_PAGE))
    page = max(1, min(page, nb_pages))
    lignes = base.offset((page - 1) * HISTORIQUE_PAR_PAGE).limit(HISTORIQUE_PAR_PAGE).all()

    ctx = dict(
        quota=etat,
        membre_depuis=_mois_annee_fr(utilisateur.date_creation) if utilisateur.date_creation else "—",
        date_reset=_jour_mois_fr(_debut_mois_suivant()),
        historique=lignes,
        hist_total=total,
        hist_page=page,
        hist_pages=nb_pages,
    )
    ctx.update(extra)
    return ctx


@router.get("/abonnement")
def page_abonnement(request: Request,
                    page: int = 1,
                    utilisateur: Utilisateur = Depends(exiger_connexion),
                    db: Session = Depends(get_db)):
    return rendre(request, "abonnement.html", utilisateur=utilisateur,
                  **_contexte_abonnement(db, utilisateur, page=page))


@router.get("/mes-donnees")
def exporter_mes_donnees(request: Request,
                        utilisateur: Utilisateur = Depends(exiger_connexion),
                        db: Session = Depends(get_db)):
    """Droit d'accès + portabilité (Loi 25) : export JSON structuré des
    renseignements personnels de l'utilisateur (profil + historique)."""
    historique = (db.query(HistoriqueRecherche)
                  .filter(HistoriqueRecherche.utilisateur_id == utilisateur.id)
                  .order_by(HistoriqueRecherche.date.desc()).all())
    dossiers = (db.query(DossierRecherche)
                .filter(DossierRecherche.utilisateur_id == utilisateur.id)
                .order_by(DossierRecherche.debut.desc()).all())
    donnees = {
        "export_le": datetime.utcnow().isoformat() + "Z",
        "compte": {
            "courriel": utilisateur.email,
            "nom": utilisateur.nom,
            "membre_depuis": (utilisateur.date_creation.isoformat()
                              if utilisateur.date_creation else None),
            "plan": utilisateur.plan,
            "email_confirme": bool(getattr(utilisateur, "email_confirme", True)),
        },
        "recherches": [
            {
                "entreprise": h.entreprise,
                "departement": h.departement,
                "region": h.region,
                "nb_contacts_trouves": h.nb_contacts_trouves,
                "date": h.date.isoformat() if h.date else None,
            }
            for h in historique
        ],
        "dossiers": [
            {
                "nom": d.nom,
                "debut": d.debut.isoformat() if d.debut else None,
                "fin": d.fin.isoformat() if d.fin else None,
                "temps_minutes": d.temps_minutes,
                "budget_minutes": d.budget_minutes,
                "entreprises": [
                    {
                        "nom": e.nom, "secteur": e.secteur, "region": e.region,
                        "site": e.site, "statut": e.statut, "note": e.note,
                        "pays": e.pays, "prix": e.prix, "sources": e.sources,
                        "taille": e.taille, "durabilite": e.durabilite,
                        "donnees_importees": json.loads(e.donnees_import_json or "[]"),
                        "pistes": json.loads(e.pistes_json or "[]"),
                        "contacts": json.loads(e.contacts_json or "[]"),
                    }
                    for e in d.entreprises
                ],
            }
            for d in dossiers
        ],
    }
    nom = f"mes-donnees-prospectb2b_{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    return JSONResponse(
        donnees,
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.post("/abonnement/mot-de-passe")
def changer_mot_de_passe(request: Request,
                        mot_de_passe_actuel: str = Form(...),
                        nouveau: str = Form(...),
                        confirmation: str = Form(...),
                        csrf_token: str = Form(""),
                        utilisateur: Utilisateur = Depends(exiger_connexion),
                        db: Session = Depends(get_db)):
    """Changement de mot de passe pour un utilisateur connecté (bcrypt, pas d'email)."""

    def echec(message):
        return rendre(request, "abonnement.html", utilisateur=utilisateur,
                      **_contexte_abonnement(db, utilisateur, mdp_erreur=message))

    if not valider_csrf(request, csrf_token):
        return echec("Session expirée, merci de réessayer.")
    if not verifier_mot_de_passe(mot_de_passe_actuel, utilisateur.mot_de_passe_hash):
        return echec("Mot de passe actuel incorrect.")
    if len(nouveau) < 8:
        return echec("Le nouveau mot de passe doit contenir au moins 8 caractères.")
    if nouveau != confirmation:
        return echec("Les deux nouveaux mots de passe ne correspondent pas.")
    if verifier_mot_de_passe(nouveau, utilisateur.mot_de_passe_hash):
        return echec("Le nouveau mot de passe doit être différent de l'actuel.")

    utilisateur.mot_de_passe_hash = hasher_mot_de_passe(nouveau)
    db.commit()
    return rendre(request, "abonnement.html", utilisateur=utilisateur,
                  **_contexte_abonnement(db, utilisateur,
                                         mdp_succes="Mot de passe mis à jour."))
