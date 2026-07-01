"""
api/index.py — Point d'entrée serverless pour Vercel.

Vercel détecte la variable `app` (application ASGI) et la sert. Toutes les
requêtes du site sont redirigées ici par vercel.json.
"""

import os
import sys

# Rendre les modules du dépôt (main, auth, database, ...) importables.
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from main import app  # noqa: E402  (exposé pour Vercel)
