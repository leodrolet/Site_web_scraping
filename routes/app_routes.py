"""
app_routes.py — Outil de prospection (connexion requise).

Réutilise tel quel recherche.rechercher_entreprise() et export.generer_excel().
Les clés API de l'utilisateur connecté sont injectées dans `config` (ContextVar)
juste avant chaque recherche. Les résultats sont sérialisés dans un champ caché
afin que le téléchargement Excel ne reconsomme pas de quota API.
"""

import base64
import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

import config
import plans
from auth import dechiffrer, exiger_connexion, valider_csrf
from database import ClesAPI, HistoriqueRecherche, Utilisateur, get_db
from export import COLONNES, generer_excel
from recherche import ErreurAPI, rechercher_entreprise
from templating import rendre

router = APIRouter()

DEPARTEMENTS = ["Marketing", "Ventes", "Les deux"]
REGIONS = ["Canada", "États-Unis", "Europe", "Toutes"]

_BASE = dict(colonnes=COLONNES, departements=DEPARTEMENTS, regions=REGIONS)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _cles_utilisateur(db, utilisateur):
    cles = db.query(ClesAPI).filter(
        ClesAPI.utilisateur_id == utilisateur.id).first()
    if cles is None:
        return "", "", ""
    return (dechiffrer(cles.hunter_key), dechiffrer(cles.apollo_key),
            dechiffrer(cles.serpapi_key))


def _activer_cles(db, utilisateur) -> bool:
    """Dépose les clés de l'utilisateur dans config. Retourne True si au moins une."""
    hunter, apollo, serpapi = _cles_utilisateur(db, utilisateur)
    config.definir_cles(hunter=hunter, apollo=apollo, serpapi=serpapi)
    return any([hunter, apollo, serpapi])


def _encoder(resultats):
    return base64.urlsafe_b64encode(
        json.dumps(resultats).encode("utf-8")).decode("ascii")


def _decoder(charge):
    try:
        return json.loads(
            base64.urlsafe_b64decode(charge.encode("ascii")).decode("utf-8"))
    except Exception:
        return []


def _nb_trouves(contacts):
    return sum(1 for c in contacts if c.get("Prénom") or c.get("Courriel"))


def _journaliser(db, utilisateur, entreprise, departement, region, contacts):
    db.add(HistoriqueRecherche(
        utilisateur_id=utilisateur.id,
        entreprise=(entreprise or "").strip(),
        departement=departement, region=region,
        nb_contacts_trouves=_nb_trouves(contacts)))


def _contexte_app(db, utilisateur, **extra):
    """Contexte commun de la page /app : colonnes, listes, et état du quota."""
    etat = plans.etat_quota(db, utilisateur)
    contexte = dict(_BASE)
    contexte.update(quota=etat, bloque_quota=etat["depasse"])
    contexte.update(extra)
    return contexte


# ----------------------------------------------------------------------
# Page de l'outil
# ----------------------------------------------------------------------
@router.get("/app")
def page_app(request: Request,
            utilisateur: Utilisateur = Depends(exiger_connexion),
            db: Session = Depends(get_db)):
    hunter, apollo, serpapi = _cles_utilisateur(db, utilisateur)
    return rendre(request, "app.html", utilisateur=utilisateur,
                  **_contexte_app(db, utilisateur,
                                  cles_configurees=any([hunter, apollo, serpapi]),
                                  departement="Les deux", region="Canada"))


# ----------------------------------------------------------------------
# Recherche simple
# ----------------------------------------------------------------------
@router.post("/app/recherche")
def recherche_simple(request: Request,
                    entreprise: str = Form(...),
                    departement: str = Form("Les deux"),
                    region: str = Form("Toutes"),
                    csrf_token: str = Form(""),
                    utilisateur: Utilisateur = Depends(exiger_connexion),
                    db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur,
                                      cles_configurees=_activer_cles(db, utilisateur),
                                      erreur="Session expirée, merci de réessayer."))

    if not _activer_cles(db, utilisateur):
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur, cles_configurees=False,
                                      departement=departement, region=region))

    # Blocage quota : le plan de l'utilisateur est épuisé pour ce mois.
    if plans.etat_quota(db, utilisateur)["depasse"]:
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur, cles_configurees=True,
                                      departement=departement, region=region))

    try:
        res = rechercher_entreprise(entreprise, departement, region)
        contacts, avertissements, erreur = res["contacts"], res["avertissements"], None
    except ErreurAPI as e:
        contacts, avertissements, erreur = [], [], e.message

    if contacts:
        _journaliser(db, utilisateur, entreprise, departement, region, contacts)
        db.commit()

    return rendre(request, "app.html", utilisateur=utilisateur,
                  **_contexte_app(db, utilisateur, cles_configurees=True,
                                  resultats=contacts, avertissements=avertissements,
                                  erreur=erreur,
                                  charge=_encoder(contacts) if contacts else "",
                                  entreprise=entreprise, departement=departement,
                                  region=region))


# ----------------------------------------------------------------------
# Recherche en lot (CSV)
# ----------------------------------------------------------------------
@router.post("/app/lot")
def recherche_lot(request: Request,
                 fichier: UploadFile = File(...),
                 csrf_token: str = Form(""),
                 utilisateur: Utilisateur = Depends(exiger_connexion),
                 db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur,
                                      cles_configurees=_activer_cles(db, utilisateur),
                                      erreur="Session expirée, merci de réessayer."))

    if not _activer_cles(db, utilisateur):
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur, cles_configurees=False))

    # Blocage quota : plan épuisé pour ce mois -> on ne traite rien.
    etat = plans.etat_quota(db, utilisateur)
    if etat["depasse"]:
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur, cles_configurees=True))

    contenu = fichier.file.read().decode("utf-8-sig", errors="replace")
    lecteur = csv.DictReader(io.StringIO(contenu))
    lignes = [{(k or "").strip().lower(): (v or "").strip()
               for k, v in row.items()} for row in lecteur]

    requises = {"entreprise", "departement", "region"}
    if not lignes or not requises.issubset(set(lignes[0].keys())):
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur, cles_configurees=True,
                                      erreur="Le CSV doit contenir les colonnes : "
                                             "entreprise, departement, region."))

    # Budget de recherches restant ce mois (None = illimité).
    budget = etat["restantes"]
    tous, avertissements, erreur = [], [], None
    for ligne in lignes:
        if budget is not None and budget <= 0:
            avertissements.append(
                "Limite mensuelle atteinte : les entreprises restantes du "
                "fichier n'ont pas été traitées. Passez à un plan supérieur "
                "pour en faire plus.")
            break
        ent = ligne.get("entreprise", "")
        if not ent:
            continue
        dep = ligne.get("departement") or "Les deux"
        reg = ligne.get("region") or "Toutes"
        try:
            res = rechercher_entreprise(ent, dep, reg)
        except ErreurAPI as e:
            erreur = e.message  # quota/clé épuisé : on s'arrête, on garde l'acquis
            break
        tous.extend(res["contacts"])
        avertissements.extend(res["avertissements"])
        _journaliser(db, utilisateur, ent, dep, reg, res["contacts"])
        if budget is not None:
            budget -= 1
    db.commit()

    return rendre(request, "app.html", utilisateur=utilisateur,
                  **_contexte_app(db, utilisateur, cles_configurees=True,
                                  resultats=tous, avertissements=avertissements,
                                  erreur=erreur,
                                  charge=_encoder(tous) if tous else ""))


# ----------------------------------------------------------------------
# Téléchargement Excel (réutilise les résultats déjà obtenus)
# ----------------------------------------------------------------------
@router.post("/app/telecharger")
def telecharger(request: Request,
               charge: str = Form(...),
               csrf_token: str = Form(""),
               utilisateur: Utilisateur = Depends(exiger_connexion)):
    if not valider_csrf(request, csrf_token):
        return RedirectResponse("/app", status_code=303)

    contacts = _decoder(charge)
    if not contacts:
        return RedirectResponse("/app", status_code=303)

    octets = generer_excel(contacts)
    nom = f"prospection_{datetime.now().strftime('%Y-%m-%d_%H%M')}.xlsx"
    return Response(
        content=octets,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )
