"""
ratelimit.py — Limiteur de débit en mémoire (fenêtre glissante), par IP + clé.

Objectif : freiner le bruteforce de mots de passe et l'abus de création de
comptes (qui consommerait les quotas d'API du service).

Limite connue : la mémoire n'est PAS partagée entre instances serverless
(Vercel lance plusieurs lambdas). Ce limiteur protège donc chaque instance et
stoppe le bruteforce basique ; pour une garantie stricte à l'échelle, adosser
un store partagé (Redis / Upstash). Voir l'audit, recommandations d'architecture.
"""

import time
from collections import defaultdict, deque

from fastapi import Request

# { "clé:ip" : deque[timestamps] }
_tentatives = defaultdict(deque)


def _ip_client(request: Request) -> str:
    """IP réelle du client (première valeur de X-Forwarded-For derrière un proxy)."""
    transmis = request.headers.get("x-forwarded-for", "")
    if transmis:
        return transmis.split(",")[0].strip()
    return request.client.host if request.client else "inconnue"


def trop_de_tentatives(request: Request, cle: str,
                       limite: int, fenetre_s: int) -> bool:
    """
    Enregistre une tentative et indique si la limite est dépassée.

    Retourne True (bloquer) si (ip, cle) a déjà atteint `limite` tentatives
    dans les `fenetre_s` dernières secondes ; sinon enregistre l'appel et
    retourne False.
    """
    maintenant = time.time()
    identifiant = f"{cle}:{_ip_client(request)}"
    file = _tentatives[identifiant]

    # Purge les entrées hors de la fenêtre.
    while file and (maintenant - file[0]) > fenetre_s:
        file.popleft()

    if len(file) >= limite:
        return True

    file.append(maintenant)
    return False
