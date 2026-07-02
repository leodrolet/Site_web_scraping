"""auth_routes.py — Connexion, inscription, déconnexion."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import (creer_session, detruire_session, hasher_mot_de_passe,
                 utilisateur_actuel, valider_csrf, verifier_mot_de_passe)
from database import Utilisateur, get_db
from ratelimit import trop_de_tentatives
from templating import rendre

router = APIRouter()


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
    # Anti-bruteforce : 5 tentatives / minute / IP.
    if trop_de_tentatives(request, "login", limite=5, fenetre_s=60):
        return rendre(request, "login.html", email=email.strip().lower(),
                      erreur="Trop de tentatives. Réessayez dans une minute.")

    if not valider_csrf(request, csrf_token):
        return rendre(request, "login.html",
                      erreur="Session expirée, merci de réessayer.")

    email = email.strip().lower()
    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == email).first()
    if not utilisateur or not verifier_mot_de_passe(mot_de_passe,
                                                    utilisateur.mot_de_passe_hash):
        return rendre(request, "login.html",
                      erreur="Courriel ou mot de passe incorrect.", email=email)
    if not utilisateur.actif:
        return rendre(request, "login.html", erreur="Ce compte est désactivé.")

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

    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return echec("Adresse courriel invalide.")
    if len(mot_de_passe) < 8:
        return echec("Le mot de passe doit contenir au moins 8 caractères.")
    if mot_de_passe != confirmation:
        return echec("Les deux mots de passe ne correspondent pas.")
    if db.query(Utilisateur).filter(Utilisateur.email == email).first():
        return echec("Un compte existe déjà avec ce courriel.")

    utilisateur = Utilisateur(
        email=email,
        nom=(nom or "").strip() or None,
        mot_de_passe_hash=hasher_mot_de_passe(mot_de_passe),
    )
    db.add(utilisateur)
    db.commit()
    db.refresh(utilisateur)

    # L'outil fonctionne directement : redirige vers /app.
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
