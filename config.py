"""
config.py — Clés API du service, lues UNIQUEMENT depuis l'environnement (.env).

Nouvelle architecture : les clés Hunter.io / Apollo.io / SerpAPI appartiennent
au SERVEUR, pas aux utilisateurs. Elles ne transitent jamais par la base de
données, les routes, le HTML ou le JavaScript. `recherche.py` lit
`config.HUNTER_API_KEY` / `APOLLO_API_KEY` / `SERPAPI_KEY` au moment de l'appel ;
ces attributs sont résolus dynamiquement depuis os.getenv() via __getattr__.
"""

import os

# Délai maximal (en secondes) par requête réseau — utilisé par recherche.py.
TIMEOUT = 10

# Interrupteur : exiger la confirmation d'email avant l'accès à l'outil.
# Désactivé par défaut. À passer à « true » UNIQUEMENT une fois un domaine
# vérifié chez Resend (sinon les vrais utilisateurs ne reçoivent pas leur
# courriel et restent bloqués). Voir .env.example.
EXIGER_CONFIRMATION_EMAIL = (
    os.getenv("EXIGER_CONFIRMATION_EMAIL", "false").strip().lower() == "true")

_NOMS_CLES = ("HUNTER_API_KEY", "APOLLO_API_KEY", "SERPAPI_KEY",
              "RESEND_API_KEY", "RESEND_FROM_EMAIL")


def statut_apis():
    """Retourne {service: bool} selon la présence de chaque clé dans l'environnement.

    Réservé à l'usage serveur / panneau admin — jamais exposé aux utilisateurs.
    """
    return {
        "Hunter.io": bool((os.getenv("HUNTER_API_KEY") or "").strip()),
        "Apollo.io": bool((os.getenv("APOLLO_API_KEY") or "").strip()),
        "SerpAPI": bool((os.getenv("SERPAPI_KEY") or "").strip()),
        "Resend (courriels)": bool((os.getenv("RESEND_API_KEY") or "").strip()
                                   and (os.getenv("RESEND_FROM_EMAIL") or "").strip()),
    }


def __getattr__(name):
    # Appelé uniquement pour les attributs NON définis comme globaux du module.
    if name in _NOMS_CLES:
        return (os.getenv(name) or "").strip()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
