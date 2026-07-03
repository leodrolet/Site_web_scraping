"""auth_routes.py — Connexion, inscription, déconnexion, confirmation d'email."""

import os
import time
from datetime import datetime, timedelta

import config
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import (creer_session, detruire_session, exiger_connexion_simple,
                 generer_jeton_confirmation, generer_jeton_reset,
                 hasher_mot_de_passe, utilisateur_actuel, valider_csrf,
                 verifier_jeton_confirmation, verifier_jeton_reset,
                 verifier_mot_de_passe)
from database import Utilisateur, get_db
from email_utils import envoyer_confirmation, envoyer_reinitialisation
from ratelimit import trop_de_tentatives
from templating import rendre

# Anti-bruteforce login (état en base) : 5 échecs -> verrou temporaire de 15 min.
MAX_TENTATIVES = 5
DUREE_VERROU = timedelta(minutes=15)
# Réinitialisation : un envoi toutes les 60 s par compte (horodatage en base).
DELAI_RESET = timedelta(seconds=60)
# Message générique unique côté connexion (ne révèle jamais la vraie cause).
MSG_LOGIN_GENERIQUE = "Courriel ou mot de passe incorrect."

router = APIRouter()

# Horodatage du dernier envoi de confirmation, par id d'utilisateur (mémoire).
# Sert à imposer un délai de 60 s entre deux envois (anti-spam).
_dernier_renvoi = {}
DELAI_RENVOI = 60  # secondes


def _lien_confirmation(request: Request, jeton: str) -> str:
    """URL absolue de confirmation, en HTTPS en production."""
    base = str(request.base_url).rstrip("/")
    if os.getenv("VERCEL") and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return f"{base}/confirmer-email?token={jeton}"


def _envoyer_confirmation(request: Request, utilisateur: Utilisateur):
    """Génère un jeton, journalise le lien (utile en dev) puis envoie le courriel.
    Lève une exception si l'envoi échoue. L'horodatage est posé sur CHAQUE
    tentative (avant l'envoi) : la limite de 60 s vaut aussi bien contre le spam
    d'envois réussis que contre le martèlement de l'endpoint."""
    _dernier_renvoi[utilisateur.id] = time.time()
    jeton = generer_jeton_confirmation(utilisateur.email)
    lien = _lien_confirmation(request, jeton)
    print(f"[confirmation] lien pour {utilisateur.email} : {lien}", flush=True)
    envoyer_confirmation(utilisateur.email, lien)   # lève en cas d'échec


def _secondes_restantes(uid) -> int:
    dernier = _dernier_renvoi.get(uid)
    if not dernier:
        return 0
    return max(0, int(DELAI_RENVOI - (time.time() - dernier)))


# ----------------------------------------------------------------------
# Connexion
# ----------------------------------------------------------------------
@router.get("/login")
def page_login(request: Request, db: Session = Depends(get_db)):
    if utilisateur_actuel(request, db):
        return RedirectResponse("/app", status_code=303)
    return rendre(request, "login.html")


@router.post("/login")
def soumettre_login(request: Request,
                   email: str = Form(...),
                   mot_de_passe: str = Form(...),
                   csrf_token: str = Form(""),
                   db: Session = Depends(get_db)):
    # NB : la protection anti-bruteforce du login est en BASE, par compte
    # (compteur + verrou 15 min), donc compatible serverless — voir plus bas.
    if not valider_csrf(request, csrf_token):
        return rendre(request, "login.html",
                      erreur="Session expirée, merci de réessayer.")

    email = email.strip().lower()
    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == email).first()

    def refus(raison):
        # Message TOUJOURS générique côté utilisateur ; vraie raison en logs.
        print(f"[login] refus ({raison}) pour {email}", flush=True)
        return rendre(request, "login.html", erreur=MSG_LOGIN_GENERIQUE, email=email)

    # Email inexistant : message générique, AUCUN comptage (pas d'oracle).
    if not utilisateur:
        return refus("email inconnu")

    # Compte verrouillé (anti-bruteforce) : refus même si le mot de passe est bon.
    if (utilisateur.verrouille_jusqu_a
            and utilisateur.verrouille_jusqu_a > datetime.utcnow()):
        return refus("compte verrouillé")

    # Mauvais mot de passe : incrémente le compteur, verrouille au seuil.
    if not verifier_mot_de_passe(mot_de_passe, utilisateur.mot_de_passe_hash):
        utilisateur.tentatives_echouees = (utilisateur.tentatives_echouees or 0) + 1
        if utilisateur.tentatives_echouees >= MAX_TENTATIVES:
            utilisateur.verrouille_jusqu_a = datetime.utcnow() + DUREE_VERROU
            utilisateur.tentatives_echouees = 0  # repart de zéro après le verrou
        db.commit()
        return refus("mot de passe incorrect")

    if not utilisateur.actif:
        return refus("compte désactivé")

    # Succès : on remet le compteur et le verrou à zéro.
    utilisateur.tentatives_echouees = 0
    utilisateur.verrouille_jusqu_a = None
    db.commit()

    reponse = RedirectResponse("/app", status_code=303)
    creer_session(reponse, utilisateur.id)
    return reponse


# ----------------------------------------------------------------------
# Inscription
# ----------------------------------------------------------------------
@router.get("/inscription")
def page_inscription(request: Request, db: Session = Depends(get_db)):
    if utilisateur_actuel(request, db):
        return RedirectResponse("/app", status_code=303)
    return rendre(request, "inscription.html")


@router.post("/inscription")
def soumettre_inscription(request: Request,
                         email: str = Form(...),
                         mot_de_passe: str = Form(...),
                         confirmation: str = Form(...),
                         nom: str = Form(""),
                         consentement: str = Form(""),
                         csrf_token: str = Form(""),
                         db: Session = Depends(get_db)):
    def echec(message):
        return rendre(request, "inscription.html", erreur=message,
                      nom=nom, email=email)

    # Anti-abus : 5 créations de compte / heure / IP (protège les quotas d'API).
    if trop_de_tentatives(request, "inscription", limite=5, fenetre_s=3600):
        return echec("Trop de tentatives. Réessayez plus tard.")

    if not valider_csrf(request, csrf_token):
        return echec("Session expirée, merci de réessayer.")

    # Consentement explicite (Loi 25) : requis pour créer le compte.
    if not consentement:
        return echec("Vous devez accepter la politique de confidentialité "
                     "pour créer un compte.")

    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return echec("Adresse courriel invalide.")
    if len(mot_de_passe) < 8:
        return echec("Le mot de passe doit contenir au moins 8 caractères.")
    if mot_de_passe != confirmation:
        return echec("Les deux mots de passe ne correspondent pas.")
    if db.query(Utilisateur).filter(Utilisateur.email == email).first():
        return echec("Un compte existe déjà avec ce courriel.")

    # Interrupteur : si la confirmation d'email n'est pas exigée, le compte est
    # confirmé d'emblée (accès immédiat) et AUCUN courriel n'est envoyé.
    exiger = config.EXIGER_CONFIRMATION_EMAIL
    utilisateur = Utilisateur(
        email=email,
        nom=(nom or "").strip() or None,
        mot_de_passe_hash=hasher_mot_de_passe(mot_de_passe),
        email_confirme=(not exiger),
    )
    db.add(utilisateur)
    db.commit()
    db.refresh(utilisateur)

    if not exiger:
        # Accès immédiat à l'outil (comportement d'avant la confirmation).
        reponse = RedirectResponse("/app", status_code=303)
        creer_session(reponse, utilisateur.id)
        return reponse

    # Confirmation exigée : on envoie le courriel. Un échec ne bloque PAS la
    # création — l'utilisateur pourra en redemander un depuis la page d'attente.
    envoi_ok = True
    try:
        _envoyer_confirmation(request, utilisateur)
    except Exception as exc:  # noqa: BLE001
        print(f"[inscription] envoi confirmation échoué : {exc}", flush=True)
        envoi_ok = False

    cible = "/confirmation-requise" + ("" if envoi_ok else "?envoi=echec")
    reponse = RedirectResponse(cible, status_code=303)
    creer_session(reponse, utilisateur.id)
    return reponse


# ----------------------------------------------------------------------
# Confirmation d'email
# ----------------------------------------------------------------------
@router.get("/confirmation-requise")
def page_confirmation_requise(request: Request,
                             envoi: str = "",
                             renvoi: str = "",
                             utilisateur: Utilisateur = Depends(exiger_connexion_simple),
                             db: Session = Depends(get_db)):
    if getattr(utilisateur, "email_confirme", True):
        return RedirectResponse("/app", status_code=303)
    return rendre(request, "confirmation-requise.html", utilisateur=utilisateur,
                  email=utilisateur.email,
                  cooldown=_secondes_restantes(utilisateur.id),
                  envoi_echec=(envoi == "echec"), renvoi=renvoi)


@router.get("/confirmer-email")
def confirmer_email(request: Request, token: str = "",
                   db: Session = Depends(get_db)):
    email = verifier_jeton_confirmation(token)
    if not email:
        # Jeton invalide ou expiré : on réaffiche la page d'attente avec l'erreur.
        utilisateur = utilisateur_actuel(request, db)
        return rendre(request, "confirmation-requise.html", utilisateur=utilisateur,
                      email=(utilisateur.email if utilisateur else ""),
                      cooldown=(_secondes_restantes(utilisateur.id) if utilisateur else 0),
                      envoi_echec=False, renvoi="",
                      erreur="Ce lien de confirmation est invalide ou expiré. "
                             "Demande un nouveau courriel ci-dessous.")

    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == email).first()
    if utilisateur and not utilisateur.email_confirme:
        utilisateur.email_confirme = True
        db.commit()
    # Succès : accès à l'outil.
    return RedirectResponse("/app", status_code=303)


@router.post("/renvoyer-confirmation")
def renvoyer_confirmation(request: Request,
                         csrf_token: str = Form(""),
                         utilisateur: Utilisateur = Depends(exiger_connexion_simple),
                         db: Session = Depends(get_db)):
    if getattr(utilisateur, "email_confirme", True):
        return RedirectResponse("/app", status_code=303)
    if not valider_csrf(request, csrf_token):
        return RedirectResponse("/confirmation-requise", status_code=303)
    # Anti-spam : un envoi toutes les 60 s par compte.
    if _secondes_restantes(utilisateur.id) > 0:
        return RedirectResponse("/confirmation-requise?renvoi=trop-tot", status_code=303)
    try:
        _envoyer_confirmation(request, utilisateur)
        return RedirectResponse("/confirmation-requise?renvoi=ok", status_code=303)
    except Exception as exc:  # noqa: BLE001
        print(f"[renvoyer] échec : {exc}", flush=True)
        return RedirectResponse("/confirmation-requise?renvoi=echec", status_code=303)


# ----------------------------------------------------------------------
# Mot de passe oublié / réinitialisation
# ----------------------------------------------------------------------
def _lien_reset(request: Request, jeton: str) -> str:
    base = str(request.base_url).rstrip("/")
    if os.getenv("VERCEL") and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return f"{base}/reinitialiser-mot-de-passe?token={jeton}"


@router.get("/mot-de-passe-oublie")
def page_mdp_oublie(request: Request):
    return rendre(request, "mot-de-passe-oublie.html")


@router.post("/mot-de-passe-oublie")
def demander_reset(request: Request,
                  email: str = Form(...),
                  csrf_token: str = Form(""),
                  db: Session = Depends(get_db)):
    # Message TOUJOURS identique : ne révèle jamais si le compte existe ni si la
    # limite d'envoi est atteinte.
    generique = "Si ce compte existe, un courriel de réinitialisation a été envoyé."
    if not valider_csrf(request, csrf_token):
        return rendre(request, "mot-de-passe-oublie.html",
                      erreur="Session expirée, merci de réessayer.")

    email = email.strip().lower()
    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == email).first()
    if utilisateur:
        # Limite 60 s en BASE (compatible serverless), sans révéler la limite.
        recent = (utilisateur.dernier_envoi_reset is not None and
                  utilisateur.dernier_envoi_reset > datetime.utcnow() - DELAI_RESET)
        if not recent:
            utilisateur.dernier_envoi_reset = datetime.utcnow()
            db.commit()
            lien = _lien_reset(request, generer_jeton_reset(utilisateur.email))
            print(f"[reset] lien pour {utilisateur.email} : {lien}", flush=True)
            try:
                envoyer_reinitialisation(utilisateur.email, lien)
            except Exception as exc:  # noqa: BLE001
                print(f"[reset] envoi échoué : {exc}", flush=True)
    return rendre(request, "mot-de-passe-oublie.html", message=generique)


@router.get("/reinitialiser-mot-de-passe")
def page_reset(request: Request, token: str = ""):
    email = verifier_jeton_reset(token)
    if not email:
        return rendre(request, "reinitialiser-mot-de-passe.html", invalide=True)
    return rendre(request, "reinitialiser-mot-de-passe.html", token=token, email=email)


@router.post("/reinitialiser-mot-de-passe")
def soumettre_reset(request: Request,
                   token: str = Form(""),
                   nouveau: str = Form(...),
                   confirmation: str = Form(...),
                   csrf_token: str = Form(""),
                   db: Session = Depends(get_db)):
    email = verifier_jeton_reset(token)

    def echec(message):
        return rendre(request, "reinitialiser-mot-de-passe.html",
                      token=token, email=email or "", erreur=message)

    if not valider_csrf(request, csrf_token):
        return echec("Session expirée, merci de réessayer.")
    if not email:
        return rendre(request, "reinitialiser-mot-de-passe.html", invalide=True)
    if len(nouveau) < 8:
        return echec("Le mot de passe doit contenir au moins 8 caractères.")
    if nouveau != confirmation:
        return echec("Les deux mots de passe ne correspondent pas.")

    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == email).first()
    if not utilisateur:
        return rendre(request, "reinitialiser-mot-de-passe.html", invalide=True)

    utilisateur.mot_de_passe_hash = hasher_mot_de_passe(nouveau)
    # Un reset réussi lève aussi un éventuel verrou anti-bruteforce.
    utilisateur.tentatives_echouees = 0
    utilisateur.verrouille_jusqu_a = None
    db.commit()

    # Reconnexion automatique.
    reponse = RedirectResponse("/app", status_code=303)
    creer_session(reponse, utilisateur.id)
    return reponse


# ----------------------------------------------------------------------
# Déconnexion
# ----------------------------------------------------------------------
@router.get("/logout")
def logout():
    reponse = RedirectResponse("/", status_code=303)
    detruire_session(reponse)
    return reponse
