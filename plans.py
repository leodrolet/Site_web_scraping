"""
plans.py — Définition des plans d'abonnement et calcul de l'usage mensuel.

Source unique de vérité pour les 3 plans (Gratuit / Pro / Business).
Le décompte des recherches se base sur la table `historique_recherches`
(une ligne = une entreprise recherchée), remis à zéro chaque mois calendaire.

Modèle actuel : PAS de paiement en ligne. Le champ `utilisateur.plan` est
assigné en base (voir README, section « Changer le plan d'un utilisateur »).
"""

from datetime import datetime

from database import HistoriqueRecherche

# Ordre d'affichage = ordre d'insertion. `limite=None` -> illimité.
PLANS = {
    "gratuit": {
        "cle": "gratuit", "nom": "Gratuit", "prix": 0, "limite": 25,
        "fonctions": [
            "25 recherches / mois",
            "Recherche simple",
            "Export Excel",
            "Vos propres clés API",
        ],
    },
    "pro": {
        "cle": "pro", "nom": "Pro", "prix": 29, "limite": 500,
        "populaire": True,
        "fonctions": [
            "500 recherches / mois",
            "Recherche simple et en lot (CSV)",
            "Export Excel",
            "Vos propres clés API",
        ],
    },
    "business": {
        "cle": "business", "nom": "Business", "prix": 79, "limite": None,
        "fonctions": [
            "Recherches illimitées",
            "Recherche simple et en lot (CSV)",
            "Export Excel",
            "Support prioritaire",
        ],
    },
}

PLAN_DEFAUT = "gratuit"


def liste_plans():
    """Retourne les plans dans l'ordre, pour l'affichage."""
    return list(PLANS.values())


def infos_plan(cle):
    """Infos d'un plan ; retombe sur le plan par défaut si la clé est inconnue."""
    return PLANS.get((cle or "").lower(), PLANS[PLAN_DEFAUT])


def _debut_du_mois():
    maintenant = datetime.utcnow()
    return datetime(maintenant.year, maintenant.month, 1)


def recherches_ce_mois(db, utilisateur_id):
    """Nombre de recherches (entreprises) faites ce mois-ci par l'utilisateur."""
    return db.query(HistoriqueRecherche).filter(
        HistoriqueRecherche.utilisateur_id == utilisateur_id,
        HistoriqueRecherche.date >= _debut_du_mois(),
    ).count()


def etat_quota(db, utilisateur):
    """
    État du quota du mois pour un utilisateur.

    Retourne un dict prêt pour l'affichage et l'application des limites :
    { plan, utilisees, limite, restantes, depasse, illimite, pourcentage }.
    """
    infos = infos_plan(getattr(utilisateur, "plan", None))
    limite = infos["limite"]
    utilisees = recherches_ce_mois(db, utilisateur.id)

    if limite is None:  # illimité
        return {
            "plan": infos, "utilisees": utilisees, "limite": None,
            "restantes": None, "depasse": False, "illimite": True,
            "pourcentage": 0,
        }

    restantes = max(0, limite - utilisees)
    pourcentage = min(100, round(utilisees * 100 / limite)) if limite else 100
    return {
        "plan": infos, "utilisees": utilisees, "limite": limite,
        "restantes": restantes, "depasse": utilisees >= limite,
        "illimite": False, "pourcentage": pourcentage,
    }
