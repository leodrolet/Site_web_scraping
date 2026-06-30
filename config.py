"""
config.py — Fournit les clés API au module recherche.py (inchangé).

recherche.py lit config.HUNTER_API_KEY / APOLLO_API_KEY / SERPAPI_KEY AU MOMENT
de l'appel. Dans la version site web, ces clés appartiennent à l'utilisateur
connecté : on les dépose dans un ContextVar (isolé par requête) via
definir_cles() juste avant chaque recherche. L'accès `config.XXX_KEY` est
résolu dynamiquement par __getattr__ (PEP 562), sans variable globale partagée.
"""

import contextvars

# Délai maximal (en secondes) par requête réseau — utilisé par recherche.py.
TIMEOUT = 10

_NOMS_CLES = ("HUNTER_API_KEY", "APOLLO_API_KEY", "SERPAPI_KEY")

# Valeur par requête (None tant que definir_cles n'a pas été appelé).
_cles_courantes = contextvars.ContextVar("cles_api", default=None)


def definir_cles(hunter="", apollo="", serpapi=""):
    """Dépose les clés de l'utilisateur courant pour la requête en cours."""
    _cles_courantes.set({
        "HUNTER_API_KEY": (hunter or "").strip(),
        "APOLLO_API_KEY": (apollo or "").strip(),
        "SERPAPI_KEY": (serpapi or "").strip(),
    })


def reinitialiser_cles():
    _cles_courantes.set(None)


def statut_apis():
    """Retourne {service: bool} selon la présence de chaque clé (requête en cours)."""
    cles = _cles_courantes.get() or {}
    return {
        "Hunter.io": bool(cles.get("HUNTER_API_KEY")),
        "Apollo.io": bool(cles.get("APOLLO_API_KEY")),
        "SerpAPI": bool(cles.get("SERPAPI_KEY")),
    }


def __getattr__(name):
    # Appelé uniquement pour les attributs NON définis comme globaux du module.
    if name in _NOMS_CLES:
        cles = _cles_courantes.get() or {}
        return cles.get(name, "")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
