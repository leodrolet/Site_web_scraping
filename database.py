"""database.py — Modèles SQLAlchemy + connexion (Neon Postgres, repli SQLite)."""

import os
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        create_engine, inspect, text)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.pool import NullPool


def _construire_engine():
    """Choisit la base : Neon/Postgres si DATABASE_URL est défini, sinon SQLite.

    Sur Vercel, le système de fichiers est en lecture seule (sauf /tmp) : le
    repli SQLite pointe donc vers /tmp pour que l'app démarre même sans
    DATABASE_URL, au lieu de crasher (FUNCTION_INVOCATION_FAILED).
    """
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        # Normalise le préfixe pour SQLAlchemy + psycopg2.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        if "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        # NullPool : en serverless, chaque invocation gère sa propre connexion.
        # À combiner avec la chaîne « -pooler » de Neon (pgbouncer).
        return create_engine(url, poolclass=NullPool, pool_pre_ping=True)

    chemin = "/tmp/prospection.db" if os.getenv("VERCEL") else "./prospection.db"
    return create_engine(f"sqlite:///{chemin}",
                         connect_args={"check_same_thread": False})


engine = _construire_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    mot_de_passe_hash = Column(String, nullable=False)
    nom = Column(String, nullable=True)
    date_creation = Column(DateTime, default=datetime.utcnow)
    actif = Column(Boolean, default=True)
    # Compte administrateur/propriétaire (créé par setup.py).
    admin = Column(Boolean, nullable=False, default=False,
                   server_default="0")
    # Plan d'abonnement : "gratuit" | "pro" | "business" (voir plans.py).
    plan = Column(String, nullable=False, default="gratuit",
                  server_default="gratuit")

    historique = relationship("HistoriqueRecherche", back_populates="utilisateur",
                             cascade="all, delete-orphan")


class HistoriqueRecherche(Base):
    __tablename__ = "historique_recherches"

    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id"))
    entreprise = Column(String)
    departement = Column(String)
    region = Column(String)
    nb_contacts_trouves = Column(Integer, default=0)
    date = Column(DateTime, default=datetime.utcnow)

    utilisateur = relationship("Utilisateur", back_populates="historique")


# Colonnes ajoutées après la première mise en production : (nom -> définition SQL).
# `create_all` ne modifie pas une table déjà créée, on les ajoute donc à la main.
_COLONNES_AJOUTEES = {
    "plan": "VARCHAR DEFAULT 'gratuit'",
    "admin": "BOOLEAN DEFAULT 0",
}


def _assurer_colonnes_utilisateurs():
    """Ajoute les colonnes manquantes aux bases existantes (SQLite et Postgres).

    Idempotent : ne fait rien pour une colonne déjà présente.
    """
    try:
        colonnes = [c["name"] for c in inspect(engine).get_columns("utilisateurs")]
    except Exception:
        return  # table pas encore créée : create_all s'en chargera avec les colonnes
    for nom, definition in _COLONNES_AJOUTEES.items():
        if nom not in colonnes:
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE utilisateurs ADD COLUMN {nom} {definition}"))


def _supprimer_table_cles_api():
    """Supprime l'ancienne table `cles_api` (clés API désormais côté serveur).

    Idempotent : ne fait rien si la table n'existe pas.
    """
    try:
        if inspect(engine).has_table("cles_api"):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE cles_api"))
    except Exception:
        pass  # non bloquant


def init_db():
    """Crée les tables si besoin. Résilient : ne fait pas planter l'import."""
    try:
        Base.metadata.create_all(bind=engine)
        _assurer_colonnes_utilisateurs()
        _supprimer_table_cles_api()
    except Exception as exc:  # pragma: no cover
        print(f"[init_db] Impossible de créer/mettre à jour les tables : {exc}")


def get_db():
    """Dépendance FastAPI : fournit une session puis la referme."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
