"""
auth.py — Sécurité : hashage des mots de passe (bcrypt), sessions signées
(itsdangerous), chiffrement des clés API (Fernet), protection CSRF, et
dépendances de contrôle d'accès.
"""

import base64
import hashlib
import os
import secrets

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from database import Utilisateur, get_db

# ----------------------------------------------------------------------
# Clé secrète (sessions + dérivation de la clé de chiffrement)
# ----------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("⚠️  SECRET_KEY absente du .env : une clé temporaire a été générée. "
          "Les sessions et les clés API chiffrées seront invalidées au "
          "redémarrage. Ajoute une SECRET_KEY dans .env (voir README).")

DUREE_SESSION = 7 * 24 * 3600  # 7 jours, en secondes
NOM_COOKIE_SESSION = "session"
NOM_COOKIE_CSRF = "csrf_token"

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session-utilisateur")

# Clé Fernet déterministe dérivée de SECRET_KEY (32 octets -> base64 urlsafe).
_fernet = Fernet(base64.urlsafe_b64encode(
    hashlib.sha256(SECRET_KEY.encode()).digest()))


# ----------------------------------------------------------------------
# Mots de passe
# ----------------------------------------------------------------------
def hasher_mot_de_passe(mot_de_passe: str) -> str:
    return bcrypt.hashpw(mot_de_passe.encode("utf-8"),
                         bcrypt.gensalt()).decode("utf-8")


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    try:
        return bcrypt.checkpw(mot_de_passe.encode("utf-8"),
                              hash_stocke.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------------
# Chiffrement des clés API
# ----------------------------------------------------------------------
def chiffrer(valeur: str) -> str:
    valeur = (valeur or "").strip()
    if not valeur:
        return ""
    return _fernet.encrypt(valeur.encode("utf-8")).decode("utf-8")


def dechiffrer(jeton: str) -> str:
    if not jeton:
        return ""
    try:
        return _fernet.decrypt(jeton.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


# ----------------------------------------------------------------------
# Sessions (cookie signé)
# ----------------------------------------------------------------------
def creer_session(response, utilisateur_id: int):
    jeton = _serializer.dumps(utilisateur_id)
    response.set_cookie(
        NOM_COOKIE_SESSION, jeton,
        max_age=DUREE_SESSION, httponly=True, samesite="lax", secure=False,
    )


def detruire_session(response):
    response.delete_cookie(NOM_COOKIE_SESSION)


def utilisateur_actuel(request: Request, db: Session = Depends(get_db)):
    """Retourne l'utilisateur connecté, ou None. Utilisable comme dépendance."""
    jeton = request.cookies.get(NOM_COOKIE_SESSION)
    if not jeton:
        return None
    try:
        uid = _serializer.loads(jeton, max_age=DUREE_SESSION)
    except (BadSignature, SignatureExpired):
        return None
    utilisateur = db.query(Utilisateur).filter(Utilisateur.id == uid).first()
    if utilisateur is None or not utilisateur.actif:
        return None
    return utilisateur


class RedirectionConnexion(Exception):
    """Levée par exiger_connexion quand l'utilisateur n'est pas connecté."""


def exiger_connexion(request: Request,
                    db: Session = Depends(get_db)) -> Utilisateur:
    """Dépendance : impose la connexion, sinon redirige vers /login."""
    utilisateur = utilisateur_actuel(request, db)
    if utilisateur is None:
        raise RedirectionConnexion()
    return utilisateur


# ----------------------------------------------------------------------
# CSRF (motif « double-submit cookie »)
# ----------------------------------------------------------------------
def generer_csrf() -> str:
    return secrets.token_urlsafe(32)


def valider_csrf(request: Request, jeton_formulaire: str) -> bool:
    jeton_cookie = request.cookies.get(NOM_COOKIE_CSRF, "")
    if not jeton_cookie or not jeton_formulaire:
        return False
    return secrets.compare_digest(jeton_cookie, jeton_formulaire)
