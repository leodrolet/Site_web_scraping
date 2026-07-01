"""
setup.py — Initialisation du projet et création du compte administrateur.

À lancer une fois, après avoir renseigné le fichier .env (au minimum SECRET_KEY,
et DATABASE_URL si tu utilises Neon/PostgreSQL) :

    python3 setup.py

Le script :
  1. charge le .env,
  2. crée / met à jour les tables (idempotent),
  3. demande courriel + mot de passe dans le terminal,
  4. crée le compte administrateur (plan « business », illimité), ou met à
     jour un compte existant (promotion admin + réinitialisation du mot de passe).

Relancer le script est sans danger : il ne crée jamais de doublon.
"""

import getpass
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # doit précéder l'import de `auth` (lecture de SECRET_KEY).


def _abandon(message):
    print(f"\n[X] {message}")
    sys.exit(1)


def _demander_courriel():
    email = input("Courriel de l'administrateur : ").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        _abandon("Adresse courriel invalide.")
    return email


def _demander_mot_de_passe():
    mdp = getpass.getpass("Mot de passe (8 caractères min.) : ")
    if len(mdp) < 8:
        _abandon("Le mot de passe doit contenir au moins 8 caractères.")
    if mdp != getpass.getpass("Confirme le mot de passe : "):
        _abandon("Les deux mots de passe ne correspondent pas.")
    return mdp


def main():
    print("=" * 55)
    print("  Initialisation — Outil de prospection B2B")
    print("=" * 55)

    if not os.getenv("SECRET_KEY", "").strip():
        print("\n[!] Aucune SECRET_KEY dans .env : une clé temporaire sera "
              "utilisee. Ajoute une SECRET_KEY avant la mise en production "
              "(sinon sessions et cles API chiffrees seront invalidees).")

    url = (os.getenv("DATABASE_URL") or "").strip()
    print(f"\n>> Base de donnees : "
          f"{'PostgreSQL (DATABASE_URL detectee)' if url else 'SQLite locale (pas de DATABASE_URL)'}")

    # Imports tardifs : après load_dotenv, pour que la config lise le .env.
    from auth import hasher_mot_de_passe
    from database import ClesAPI, SessionLocal, Utilisateur, init_db

    print(">> Creation / mise a jour des tables...")
    init_db()

    print("\n--- Compte administrateur ---")
    email = _demander_courriel()

    db = SessionLocal()
    try:
        existant = db.query(Utilisateur).filter(Utilisateur.email == email).first()
        if existant:
            print(f"\n[!] Un compte existe deja avec « {email} ».")
            reponse = input("    Le promouvoir admin et reinitialiser son mot "
                            "de passe ? [o/N] ").strip().lower()
            if reponse not in ("o", "oui", "y", "yes"):
                _abandon("Operation annulee. Aucune modification.")
            mdp = _demander_mot_de_passe()
            existant.mot_de_passe_hash = hasher_mot_de_passe(mdp)
            existant.admin = True
            existant.actif = True
            existant.plan = "business"
            db.commit()
            print(f"\n[OK] Compte « {email} » mis a jour (admin, plan business).")
            return

        mdp = _demander_mot_de_passe()
        nom = input("Nom (optionnel) : ").strip() or None

        admin = Utilisateur(
            email=email,
            nom=nom,
            mot_de_passe_hash=hasher_mot_de_passe(mdp),
            admin=True,
            actif=True,
            plan="business",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        db.add(ClesAPI(utilisateur_id=admin.id))
        db.commit()
        print(f"\n[OK] Compte administrateur cree : « {email} » (plan business).")
        print("     Connecte-toi sur /login, puis ajoute tes cles API dans /parametres.")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrompu.")
        sys.exit(130)
