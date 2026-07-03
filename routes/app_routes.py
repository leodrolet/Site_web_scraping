"""
app_routes.py — Outil de prospection (connexion requise).

Réutilise recherche.rechercher_entreprise() et export.generer_excel().
Les clés API sont lues côté serveur depuis l'environnement (voir config.py) :
elles ne transitent jamais par la base, les routes ou le HTML. En cas d'échec
d'un service externe, l'utilisateur voit un message générique — jamais le nom
du service ni le détail de l'erreur.
"""

import base64
import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import (JSONResponse, RedirectResponse, Response,
                               StreamingResponse)
from sqlalchemy.orm import Session

import plans
from auth import exiger_connexion, valider_csrf
from database import HistoriqueRecherche, SessionLocal, Utilisateur, get_db
from export import COLONNES, generer_excel
from recherche import ErreurAPI, rechercher_entreprise
from templating import rendre

router = APIRouter()

DEPARTEMENTS = ["Marketing", "Ventes", "Les deux"]
REGIONS = ["Canada", "États-Unis", "Europe", "Toutes"]

# Bornes anti-abus pour l'import CSV (type, taille, nombre de lignes).
MAX_OCTETS_CSV = 1_000_000   # 1 Mo
MAX_LIGNES_CSV = 1000
# Nombre de recherches récentes affichées sur /app.
NB_HISTORIQUE = 8

# Message unique montré à l'utilisateur quand un service externe échoue.
# Aucun détail sur le service concerné ni la cause (clé, quota...).
MSG_SERVICE_INDISPO = ("Service temporairement indisponible. "
                       "Merci de réessayer dans quelques instants.")

_BASE = dict(colonnes=COLONNES, departements=DEPARTEMENTS, regions=REGIONS)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
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


def _nb_entreprises(contacts):
    """Nombre d'entreprises distinctes représentées dans une liste de contacts."""
    return len({(c.get("Entreprise") or "").strip()
                for c in contacts if (c.get("Entreprise") or "").strip()})


def _journaliser(db, utilisateur, entreprise, departement, region, contacts):
    db.add(HistoriqueRecherche(
        utilisateur_id=utilisateur.id,
        entreprise=(entreprise or "").strip(),
        departement=departement, region=region,
        nb_contacts_trouves=_nb_trouves(contacts)))


def _historique_recent(db, utilisateur, n=NB_HISTORIQUE):
    """Les n dernières recherches de l'utilisateur (récent -> ancien).

    Ne contient QUE les champs stockés dans `historique_recherches`
    (entreprise, departement, region, nb_contacts_trouves, date) : les contacts
    eux-mêmes ne sont pas conservés en base, donc pas affichables ici.
    """
    return (db.query(HistoriqueRecherche)
            .filter(HistoriqueRecherche.utilisateur_id == utilisateur.id)
            .order_by(HistoriqueRecherche.date.desc())
            .limit(n).all())


def _contexte_app(db, utilisateur, **extra):
    """Contexte commun de la page /app : colonnes, listes, quota, historique."""
    etat = plans.etat_quota(db, utilisateur)
    contexte = dict(_BASE)
    contexte.update(quota=etat, bloque_quota=etat["depasse"],
                    historique=_historique_recent(db, utilisateur))
    contexte.update(extra)
    return contexte


def _lignes_depuis_csv(fichier):
    """Lit et valide un CSV téléversé.

    Retourne (lignes, erreur) : `lignes` est une liste de dicts (clés en
    minuscules) ou None si erreur ; `erreur` est un message prêt à afficher.
    """
    if not (fichier.filename or "").lower().endswith(".csv"):
        return None, "Merci de téléverser un fichier .csv."

    brut = fichier.file.read(MAX_OCTETS_CSV + 1)
    if len(brut) > MAX_OCTETS_CSV:
        return None, "Fichier trop volumineux (max 1 Mo)."

    contenu = brut.decode("utf-8-sig", errors="replace")
    lecteur = csv.DictReader(io.StringIO(contenu))
    lignes = [{(k or "").strip().lower(): (v or "").strip()
               for k, v in row.items()} for row in lecteur]

    if len(lignes) > MAX_LIGNES_CSV:
        return None, f"Fichier trop long (max {MAX_LIGNES_CSV} lignes)."

    requises = {"entreprise", "departement", "region"}
    if not lignes or not requises.issubset(set(lignes[0].keys())):
        return None, ("Le CSV doit contenir les colonnes : "
                      "entreprise, departement, region.")
    return lignes, None


# ----------------------------------------------------------------------
# Page de l'outil
# ----------------------------------------------------------------------
@router.get("/app")
def page_app(request: Request,
            utilisateur: Utilisateur = Depends(exiger_connexion),
            db: Session = Depends(get_db)):
    return rendre(request, "app.html", utilisateur=utilisateur,
                  **_contexte_app(db, utilisateur,
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
                                      erreur="Session expirée, merci de réessayer."))

    # Blocage quota : le plan de l'utilisateur est épuisé pour ce mois.
    if plans.etat_quota(db, utilisateur)["depasse"]:
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur,
                                      departement=departement, region=region))

    try:
        res = rechercher_entreprise(entreprise, departement, region)
        contacts, erreur = res["contacts"], None
    except ErreurAPI as e:
        # Détail journalisé côté serveur (logs Vercel) ; message générique à l'écran.
        print(f"[/app/recherche] ErreurAPI : {e.message}", flush=True)
        contacts, erreur = [], MSG_SERVICE_INDISPO

    if contacts:
        _journaliser(db, utilisateur, entreprise, departement, region, contacts)
        db.commit()

    return rendre(request, "app.html", utilisateur=utilisateur,
                  **_contexte_app(db, utilisateur,
                                  resultats=contacts, erreur=erreur,
                                  charge=_encoder(contacts) if contacts else "",
                                  nb_contacts=_nb_trouves(contacts),
                                  nb_entreprises=_nb_entreprises(contacts),
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
                                      erreur="Session expirée, merci de réessayer."))

    # Blocage quota : plan épuisé pour ce mois -> on ne traite rien.
    etat = plans.etat_quota(db, utilisateur)
    if etat["depasse"]:
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur))

    lignes, erreur_csv = _lignes_depuis_csv(fichier)
    if erreur_csv:
        return rendre(request, "app.html", utilisateur=utilisateur,
                      **_contexte_app(db, utilisateur, erreur=erreur_csv))

    # Budget de recherches restant ce mois (None = illimité).
    budget = etat["restantes"]
    tous, erreur = [], None
    for ligne in lignes:
        if budget is not None and budget <= 0:
            erreur = ("Limite mensuelle atteinte : les entreprises restantes du "
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
            print(f"[/app/lot] ErreurAPI : {e.message}", flush=True)
            erreur = MSG_SERVICE_INDISPO  # on s'arrête, on garde l'acquis
            break
        tous.extend(res["contacts"])
        _journaliser(db, utilisateur, ent, dep, reg, res["contacts"])
        if budget is not None:
            budget -= 1
    db.commit()

    return rendre(request, "app.html", utilisateur=utilisateur,
                  **_contexte_app(db, utilisateur,
                                  resultats=tous, erreur=erreur,
                                  nb_contacts=_nb_trouves(tous),
                                  nb_entreprises=_nb_entreprises(tous),
                                  charge=_encoder(tous) if tous else ""))


# ----------------------------------------------------------------------
# Recherche en lot — flux de progression (NDJSON, ligne par ligne)
# ----------------------------------------------------------------------
# Choix technique : streaming (StreamingResponse) consommé côté client via
# fetch() + ReadableStream, plutôt que du polling avec identifiant de job.
# Raison : tout le traitement tient dans UNE requête, sans état partagé entre
# instances (le polling exigerait un store de job partagé, fragile en serverless
# multi-instances — même limite que le limiteur mémoire). Le flux émet une ligne
# JSON par entreprise traitée, puis une ligne finale « done » avec les résultats
# complets et la charge base64 pour le téléchargement Excel.
@router.post("/app/lot/flux")
def recherche_lot_flux(request: Request,
                       fichier: UploadFile = File(...),
                       csrf_token: str = Form(""),
                       utilisateur: Utilisateur = Depends(exiger_connexion),
                       db: Session = Depends(get_db)):
    if not valider_csrf(request, csrf_token):
        return JSONResponse({"erreur": "Session expirée, merci de réessayer."},
                            status_code=400)

    # Vérification du quota côté serveur (comme /app/lot) avant tout traitement.
    etat = plans.etat_quota(db, utilisateur)
    if etat["depasse"]:
        return JSONResponse(
            {"erreur": "Limite mensuelle atteinte : passez à un plan supérieur "
                       "pour lancer une recherche en lot."}, status_code=400)

    lignes, erreur_csv = _lignes_depuis_csv(fichier)
    if erreur_csv:
        return JSONResponse({"erreur": erreur_csv}, status_code=400)

    valides = [l for l in lignes if l.get("entreprise")]
    total = len(valides)
    uid = utilisateur.id
    budget_initial = etat["restantes"]  # None = illimité

    def flux():
        # Session dédiée : sa durée de vie est celle du flux (pas de la requête).
        db2 = SessionLocal()
        tous, erreur, budget, k = [], None, budget_initial, 0
        try:
            for ligne in valides:
                if budget is not None and budget <= 0:
                    erreur = ("Limite mensuelle atteinte : les entreprises "
                              "restantes du fichier n'ont pas été traitées. "
                              "Passez à un plan supérieur pour en faire plus.")
                    break
                ent = ligne.get("entreprise", "")
                dep = ligne.get("departement") or "Les deux"
                reg = ligne.get("region") or "Toutes"
                try:
                    res = rechercher_entreprise(ent, dep, reg)
                except ErreurAPI as e:
                    # Détail en logs serveur ; message générique côté client.
                    print(f"[/app/lot/flux] ErreurAPI : {e.message}", flush=True)
                    erreur = MSG_SERVICE_INDISPO
                    break
                contacts = res["contacts"]
                tous.extend(contacts)
                db2.add(HistoriqueRecherche(
                    utilisateur_id=uid, entreprise=(ent or "").strip(),
                    departement=dep, region=reg,
                    nb_contacts_trouves=_nb_trouves(contacts)))
                if budget is not None:
                    budget -= 1
                k += 1
                # Progression : jamais le nom d'un fournisseur, seulement l'état.
                # dep/reg permettent au « Voir plus » de recibler cette entreprise.
                yield json.dumps({
                    "type": "progress", "courante": k, "total": total,
                    "entreprise": ent, "trouve": _nb_trouves(contacts) > 0,
                    "dep": dep, "reg": reg,
                }, ensure_ascii=False) + "\n"
            db2.commit()
        finally:
            db2.close()
        yield json.dumps({
            "type": "done", "colonnes": COLONNES, "resultats": tous,
            "charge": _encoder(tous) if tous else "", "erreur": erreur,
            "nb_contacts": _nb_trouves(tous), "nb_entreprises": _nb_entreprises(tous),
        }, ensure_ascii=False) + "\n"

    return StreamingResponse(flux(), media_type="application/x-ndjson")


# ----------------------------------------------------------------------
# « Voir plus de contacts » pour une entreprise déjà cherchée
# ----------------------------------------------------------------------
# Enrichissement À LA DEMANDE : ne consomme PAS de quota (pas de journalisation),
# ne modifie pas plans.py. Renvoie la page suivante de contacts (offset) pour
# UNE entreprise précise, triés par pertinence.
@router.post("/app/plus-de-contacts")
def plus_de_contacts(request: Request,
                    entreprise: str = Form(...),
                    departement: str = Form("Les deux"),
                    region: str = Form("Toutes"),
                    deja: int = Form(0),
                    csrf_token: str = Form(""),
                    utilisateur: Utilisateur = Depends(exiger_connexion)):
    if not valider_csrf(request, csrf_token):
        return JSONResponse({"erreur": "Session expirée, merci de réessayer."},
                            status_code=400)

    # Rang de départ borné : le front n'envoie que « deja=5 », on plafonne par sûreté.
    try:
        offset = max(0, min(int(deja), 20))
    except (TypeError, ValueError):
        offset = 5

    try:
        res = rechercher_entreprise(entreprise, departement, region,
                                    limite=5, offset=offset)
        contacts = res["contacts"]
    except ErreurAPI as e:
        print(f"[/app/plus-de-contacts] ErreurAPI : {e.message}", flush=True)
        return JSONResponse({"erreur": MSG_SERVICE_INDISPO}, status_code=200)

    # Aucune journalisation, aucun décompte de quota : pur enrichissement.
    return JSONResponse({"contacts": contacts, "colonnes": COLONNES})


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
