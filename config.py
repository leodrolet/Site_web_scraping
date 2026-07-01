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

_NOMS_CLES = ("HUNTER_API_KEY", "APOLLO_API_KEY", "SERPAPI_KEY")


def statut_apis():
    """Retourne {service: bool} selon la présence de chaque clé dans l'environnement.

    Réservé à l'usage serveur / panneau admin — jamais exposé aux utilisateurs.
    """
    return {
        "Hunter.io": bool((os.getenv("HUNTER_API_KEY") or "").strip()),
        "Apollo.io": bool((os.getenv("APOLLO_API_KEY") or "").strip()),
        "SerpAPI": bool((os.getenv("SERPAPI_KEY") or "").strip()),
    }


def __getattr__(name):
    # Appelé uniquement pour les attributs NON définis comme globaux du module.
    if name in _NOMS_CLES:
        return (os.getenv(name) or "").strip()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
