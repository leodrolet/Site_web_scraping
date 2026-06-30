"""database.py — Modèles SQLAlchemy et initialisation de la base SQLite."""

from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

CHEMIN_DB = "sqlite:///./prospection.db"

engine = create_engine(CHEMIN_DB, connect_args={"check_same_thread": False})
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

    cles = relationship("ClesAPI", back_populates="utilisateur",
                        uselist=False, cascade="all, delete-orphan")
    historique = relationship("HistoriqueRecherche", back_populates="utilisateur",
                             cascade="all, delete-orphan")


class ClesAPI(Base):
    __tablename__ = "cles_api"

    id = Column(Integer, primary_key=True)
    utilisateur_id = Column(Integer, ForeignKey("utilisateurs.id"), unique=True)
    # Valeurs CHIFFRÉES (Fernet) — jamais stockées en clair.
    hunter_key = Column(String, default="")
    apollo_key = Column(String, default="")
    serpapi_key = Column(String, default="")
    date_modification = Column(DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)

    utilisateur = relationship("Utilisateur", back_populates="cles")


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


def init_db():
    """Crée les tables si elles n'existent pas encore."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dépendance FastAPI : fournit une session puis la referme."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
