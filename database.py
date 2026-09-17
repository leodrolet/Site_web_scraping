"""database.py — Modèles SQLAlchemy + connexion (Neon Postgres, repli SQLite)."""

import os
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String, Text, LargeBinary,
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
    # Adresse courriel confirmée. server_default TRUE : les comptes déjà en base
    # restent utilisables sans re-confirmation. L'inscription force False (voir
    # auth_routes) pour n'imposer la confirmation qu'aux nouveaux comptes.
    email_confirme = Column(Boolean, nullable=False, default=True,
                            server_default=text("true"))
    # Réinitialisation de mot de passe : horodatage du dernier envoi (limite 60s).
    dernier_envoi_reset = Column(DateTime, nullable=True)
    # Anti-bruteforce login (état en BASE, compatible serverless).
    tentatives_echouees = Column(Integer, nullable=False, default=0,
                                 server_default="0")
    verrouille_jusqu_a = Column(DateTime, nullable=True)

    historique = relationship("HistoriqueRecherche", back_populates="utilisateur",
                             cascade="all, delete-orphan")
    dossiers = relationship("DossierRecherche", back_populates="utilisateur",
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


class DossierRecherche(Base):
    __tablename__ = "dossiers_recherche"

    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False, index=True)
    nom = Column(String(160), nullable=False)
    debut = Column(DateTime, default=datetime.utcnow, nullable=False)
    fin = Column(DateTime, nullable=True)
    temps_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    budget_minutes = Column(Integer, nullable=False, default=480, server_default="480")
    utilisateur = relationship("Utilisateur", back_populates="dossiers")
    entreprises = relationship("EntrepriseDossier", back_populates="dossier",
                               cascade="all, delete-orphan")
    imports = relationship("ImportMandat", back_populates="dossier",
                           cascade="all, delete-orphan")
    documents = relationship("DocumentMandat", back_populates="dossier",
                             cascade="all, delete-orphan")


class EntrepriseDossier(Base):
    __tablename__ = "entreprises_dossier"

    id = Column(Integer, primary_key=True)
    dossier_id = Column(Integer, ForeignKey("dossiers_recherche.id"), nullable=False, index=True)
    nom = Column(String(255), nullable=False)
    cle = Column(String(255), nullable=False)
    secteur = Column(String(160), default="")
    region = Column(String(160), default="")
    pays = Column(String(160), default="", server_default="")
    prix = Column(Text, default="", server_default="")
    sources = Column(Text, default="", server_default="")
    taille = Column(String(20), default="inconnue", server_default="inconnue")
    durabilite = Column(Text, default="", server_default="")
    donnees_import_json = Column(Text, default="[]", server_default="[]")
    pistes_json = Column(Text, default="[]", server_default="[]")
    revision = Column(Integer, nullable=False, default=0, server_default="0")
    site = Column(String(500), default="")
    statut = Column(String(20), default="a_faire")
    note = Column(Text, default="")
    contacts_json = Column(Text, default="[]")
    mise_a_jour = Column(DateTime, nullable=True)
    dossier = relationship("DossierRecherche", back_populates="entreprises")


class DocumentMandat(Base):
    __tablename__ = "documents_mandat"
    id = Column(String(40), primary_key=True)
    dossier_id = Column(Integer, ForeignKey("dossiers_recherche.id"), nullable=False, index=True)
    fichier = Column(String(255), nullable=False)
    genre = Column(String(20), nullable=False)
    original = Column(LargeBinary, nullable=False)
    propositions_json = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    cree_le = Column(DateTime, default=datetime.utcnow, nullable=False)
    dossier = relationship("DossierRecherche", back_populates="documents")


class ImportMandat(Base):
    __tablename__ = "imports_mandat"
    id = Column(String(40), primary_key=True)
    dossier_id = Column(Integer, ForeignKey("dossiers_recherche.id"), nullable=False, index=True)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    cree_le = Column(DateTime, default=datetime.utcnow, nullable=False)
    fichier = Column(String(255), nullable=False)
    donnees_json = Column(Text, nullable=False)
    mapping_json = Column(Text, default="{}", nullable=False)
    consomme = Column(Boolean, default=False, nullable=False)
    dossier = relationship("DossierRecherche", back_populates="imports")


# Colonnes ajoutées après la première mise en production : (nom -> définition SQL).
# `create_all` ne modifie pas une table déjà créée, on les ajoute donc à la main.
_COLONNES_AJOUTEES = {
    "plan": "VARCHAR DEFAULT 'gratuit'",
    "admin": "BOOLEAN DEFAULT 0",
    # TRUE par défaut : les comptes existants ne sont pas bloqués au déploiement.
    # « TRUE » (et non « 1 ») pour être valide à la fois sur PostgreSQL et SQLite.
    "email_confirme": "BOOLEAN DEFAULT TRUE",
    # Réinitialisation de mot de passe + anti-bruteforce (état en base).
    "dernier_envoi_reset": "TIMESTAMP",
    "tentatives_echouees": "INTEGER DEFAULT 0",
    "verrouille_jusqu_a": "TIMESTAMP",
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


def _assurer_colonnes_mandats():
    """Migration additive et idempotente : conserve comptes, historique et anciens dossiers."""
    ajouts = {
        "dossiers_recherche": {"temps_minutes": "INTEGER NOT NULL DEFAULT 0",
                               "budget_minutes": "INTEGER NOT NULL DEFAULT 480"},
        "entreprises_dossier": {
            "pays": "VARCHAR(160) DEFAULT ''", "prix": "TEXT DEFAULT ''",
            "sources": "TEXT DEFAULT ''", "taille": "VARCHAR(20) DEFAULT 'inconnue'",
            "durabilite": "TEXT DEFAULT ''", "donnees_import_json": "TEXT DEFAULT '[]'",
            "pistes_json": "TEXT DEFAULT '[]'", "revision": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    with engine.begin() as conn:
        # Évite deux ALTER simultanés pendant les démarrages Vercel/Postgres.
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(72816409)"))
        for table, definitions in ajouts.items():
            existantes = {c["name"] for c in inspect(conn).get_columns(table)}
            for nom, definition in definitions.items():
                if nom not in existantes:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {nom} {definition}"))


def init_db():
    """Crée les tables si besoin. Résilient : ne fait pas planter l'import."""
    try:
        Base.metadata.create_all(bind=engine)
        _assurer_colonnes_utilisateurs()
        _assurer_colonnes_mandats()
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
