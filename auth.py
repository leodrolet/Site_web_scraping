"""
auth.py — Sécurité : hashage des mots de passe (bcrypt), sessions signées
(itsdangerous), protection CSRF, et dépendances de contrôle d'accès.
"""

import os
import secrets

import bcrypt
from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from database import Utilisateur, get_db

# ----------------------------------------------------------------------
# Clé secrète (signature des sessions)
# ----------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    # En production (Vercel ou COOKIE_SECURE), on refuse de démarrer sans clé :
    # une clé aléatoire par instance/redémarrage casserait les sessions (et,
    # en serverless multi-instances, empêcherait toute connexion stable).
    _en_prod = bool(os.getenv("VERCEL")) or (
        os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes", "on"))
    if _en_prod:
        raise RuntimeError(
            "SECRET_KEY manquante en production. Définis SECRET_KEY dans les "
            "variables d'environnement (voir README) avant de déployer.")
    SECRET_KEY = secrets.token_hex(32)
    print("⚠️  SECRET_KEY absente du .env : une clé temporaire a été générée "
          "(développement uniquement). Les sessions seront invalidées au "
          "redémarrage. Ajoute une SECRET_KEY dans .env (voir README).")

DUREE_SESSION = 7 * 24 * 3600  # 7 jours, en secondes
NOM_COOKIE_SESSION = "session"
NOM_COOKIE_CSRF = "csrf_token"

# Cookies « secure » (transmis uniquement en HTTPS) : activés en production.
# Vrai si COOKIE_SECURE=1 (ou true/yes/on) OU si l'app tourne sur Vercel (HTTPS).
# En local (HTTP), faux par défaut — sinon le navigateur refuserait le cookie.
COOKIE_SECURE = (
    os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes", "on")
    or bool(os.getenv("VERCEL"))
)

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="session-utilisateur")

# Jetons de confirmation d'email : même SECRET_KEY, mais un SALT DIFFÉRENT de
# celui des sessions -> un jeton de confirmation ne peut jamais servir de session
# (et inversement). Ne contient QUE l'email, expire après 48h.
DUREE_CONFIRMATION = 48 * 3600
_serializer_confirmation = URLSafeTimedSerializer(SECRET_KEY, salt="confirmation-email")


def generer_jeton_confirmation(email: str) -> str:
    return _serializer_confirmation.dumps(email)


def verifier_jeton_confirmation(jeton: str, max_age: int = DUREE_CONFIRMATION):
    """Retourne l'email si le jeton est valide et non expiré, sinon None."""
    try:
        return _serializer_confirmation.loads(jeton, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


# Jetons de réinitialisation de mot de passe : SALT encore différent (jamais
# interchangeable avec session ni confirmation) et expiration COURTE (1h), car
# plus sensible.
DUREE_RESET = 3600
_serializer_reset = URLSafeTimedSerializer(SECRET_KEY, salt="reset-mot-de-passe")


def generer_jeton_reset(email: str) -> str:
    return _serializer_reset.dumps(email)


def verifier_jeton_reset(jeton: str, max_age: int = DUREE_RESET):
    try:
        return _serializer_reset.loads(jeton, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


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
# Sessions (cookie signé)
# ----------------------------------------------------------------------
def creer_session(response, utilisateur_id: int):
    jeton = _serializer.dumps(utilisateur_id)
    response.set_cookie(
        NOM_COOKIE_SESSION, jeton,
        max_age=DUREE_SESSION, httponly=True, samesite="lax", secure=COOKIE_SECURE,
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
    """Levée quand l'utilisateur n'est pas connecté (-> /login)."""


class RedirectionConfirmation(Exception):
    """Levée quand l'utilisateur est connecté mais n'a pas confirmé son email
    (-> /confirmation-requise)."""


def _confirmation_requise() -> bool:
    """Interrupteur (env) : la confirmation d'email bloque-t-elle l'accès ?
    Lu à chaque appel pour refléter la config sans redémarrage forcé."""
    return os.getenv("EXIGER_CONFIRMATION_EMAIL", "false").strip().lower() == "true"


def exiger_connexion_simple(request: Request,
                           db: Session = Depends(get_db)) -> Utilisateur:
    """Impose seulement d'être connecté (SANS exiger l'email confirmé).

    Utilisée par les pages de confirmation elles-mêmes (/confirmation-requise,
    /renvoyer-confirmation), où l'utilisateur est justement non confirmé.
    """
    utilisateur = utilisateur_actuel(request, db)
    if utilisateur is None:
        raise RedirectionConnexion()
    return utilisateur


def exiger_connexion(request: Request,
                    db: Session = Depends(get_db)) -> Utilisateur:
    """Dépendance : connexion + email confirmé.

    Non connecté            -> /login.
    Connecté, email NON confirmé -> /confirmation-requise.
    `getattr(..., True)` : si la colonne manque, on ne bloque pas (sécurité des
    comptes existants).
    """
    utilisateur = exiger_connexion_simple(request, db)
    if _confirmation_requise() and not getattr(utilisateur, "email_confirme", True):
        raise RedirectionConfirmation()
    return utilisateur


def exiger_admin(request: Request,
                db: Session = Depends(get_db)) -> Utilisateur:
    """Dépendance : impose un compte administrateur (admin=True), email confirmé.

    Non connecté -> /login ; email non confirmé -> /confirmation-requise ;
    connecté non-admin -> /app.
    """
    utilisateur = utilisateur_actuel(request, db)
    if utilisateur is None:
        raise RedirectionConnexion()
    if _confirmation_requise() and not getattr(utilisateur, "email_confirme", True):
        raise RedirectionConfirmation()
    if not getattr(utilisateur, "admin", False):
        raise RedirectionNonAutorise()
    return utilisateur


class RedirectionNonAutorise(Exception):
    """Levée par exiger_admin quand l'utilisateur n'est pas administrateur."""


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
