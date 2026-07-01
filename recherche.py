"""
recherche.py — Logique de recherche de contacts B2B.

Ordre des tentatives (avec repli automatique si rien n'est trouvé) :
    Étapes A/B — Hunter.io : Domain Search + filtrage des contacts par département
    Étape  C   — Apollo.io : recherche de personnes par entreprise + titre
    Étape  D   — SerpAPI    : repli Google (renvoie une piste LinkedIn manuelle)

La fonction publique est `rechercher_entreprise(...)`. Elle ne lève jamais
d'exception pour une entreprise donnée, SAUF une `ErreurAPI` bloquante
(clé invalide ou quota épuisé) que l'interface se charge d'afficher.
"""

from datetime import datetime

import requests

import config

# Mots-clés de titres recherchés (français + anglais), marketing et ventes.
MOTS_CLES_TITRES = [
    "marketing", "sales", "vente", "ventes", "directeur", "director",
    "manager", "gérant", "gerant", "vice-président", "vice president",
    "vp", "chief", "head", "responsable", "cmo", "cso", "growth", "brand",
]

# Correspondance « département cible » -> filtres Hunter & titres Apollo.
FILTRES_DEPARTEMENT = {
    "Marketing": {
        "hunter": {"marketing", "communication"},
        "titres": ["marketing", "cmo", "communication", "growth", "brand",
                   "directeur marketing", "directrice marketing"],
    },
    "Ventes": {
        "hunter": {"sales"},
        "titres": ["sales", "vente", "ventes", "gérant des ventes", "cso",
                   "business development", "account executive",
                   "directeur des ventes", "directrice des ventes"],
    },
    "Les deux": {
        "hunter": {"marketing", "communication", "sales"},
        "titres": ["marketing", "sales", "vente", "ventes", "cmo", "cso",
                   "growth", "business development", "directeur", "directrice"],
    },
}

# Correspondance « région » -> pays (utilisée par Apollo pour filtrer).
PAYS_PAR_REGION = {
    "Canada": ["Canada"],
    "États-Unis": ["United States"],
    "Europe": ["France", "Belgium", "Switzerland", "United Kingdom",
               "Germany", "Spain", "Italy", "Netherlands"],
    "Toutes": [],
}


class ErreurAPI(Exception):
    """Erreur connue renvoyée par un service (clé invalide, quota épuisé...)."""

    def __init__(self, message, service=None):
        super().__init__(message)
        self.message = message
        self.service = service


def _aujourd_hui():
    return datetime.now().strftime("%Y-%m-%d")


def _fiche_vide(entreprise, statut, source=""):
    """Construit une ligne « non trouvé » propre pour le fichier Excel."""
    return {
        "Entreprise": entreprise,
        "Prénom": "",
        "Nom": "",
        "Titre": statut,
        "Département": "",
        "Courriel": "",
        "Confiance (%)": "",
        "Ville": "",
        "Province/État": "",
        "Pays": "",
        "Source": source,
        "Date de recherche": _aujourd_hui(),
    }


def _departement_lisible(valeur):
    correspondances = {
        "marketing": "Marketing",
        "communication": "Marketing",
        "sales": "Ventes",
    }
    return correspondances.get((valeur or "").lower(), valeur or "")


def _titre_pertinent(titre, departement):
    if not titre:
        return False
    titre_bas = titre.lower()
    return any(mot in titre_bas for mot in FILTRES_DEPARTEMENT[departement]["titres"])


# ----------------------------------------------------------------------
# Étapes A / B — Hunter.io
# ----------------------------------------------------------------------
def _hunter_domain_search(entreprise, departement, region):
    """Domain Search Hunter : domaine + modèle de courriel + contacts filtrés."""
    if not config.HUNTER_API_KEY:
        return [], ["Hunter.io : clé API absente — étape ignorée."]

    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "company": entreprise,
        "api_key": config.HUNTER_API_KEY,
        "limit": 50,
    }
    try:
        rep = requests.get(url, params=params, timeout=config.TIMEOUT)
    except requests.exceptions.Timeout:
        return [], ["Hunter.io : délai dépassé (10 s)."]
    except requests.exceptions.RequestException as e:
        return [], [f"Hunter.io : erreur réseau ({e})."]

    if rep.status_code == 401:
        raise ErreurAPI("Hunter.io : clé API invalide ou manquante.", "Hunter.io")
    if rep.status_code == 429:
        raise ErreurAPI("Hunter.io : quota mensuel dépassé.", "Hunter.io")
    if rep.status_code != 200:
        return [], [f"Hunter.io : réponse inattendue (code {rep.status_code})."]

    data = (rep.json() or {}).get("data", {}) or {}
    domaine = data.get("domain")
    modele = data.get("pattern")          # ex : {first}.{last}
    pays = data.get("country") or ""
    etat = data.get("state") or ""
    ville = data.get("city") or ""

    cibles_hunter = FILTRES_DEPARTEMENT[departement]["hunter"]
    contacts = []
    for courriel in data.get("emails", []) or []:
        dep = (courriel.get("department") or "").lower()
        poste = courriel.get("position") or ""
        if not (dep in cibles_hunter or _titre_pertinent(poste, departement)):
            continue
        confiance = courriel.get("confidence")
        contacts.append({
            "Entreprise": entreprise,
            "Prénom": courriel.get("first_name") or "",
            "Nom": courriel.get("last_name") or "",
            "Titre": poste,
            "Département": _departement_lisible(dep) or departement,
            "Courriel": courriel.get("value") or "",
            "Confiance (%)": confiance if confiance is not None else "",
            "Ville": ville,
            "Province/État": etat,
            "Pays": pays,
            "Source": f"Hunter.io ({domaine})" if domaine else "Hunter.io",
            "Date de recherche": _aujourd_hui(),
        })

    avertissements = []
    if domaine and not contacts:
        note = f"domaine trouvé ({domaine})"
        if modele:
            note += f", modèle de courriel : {modele}@{domaine}"
        avertissements.append(
            f"Hunter.io : aucun contact « {departement} » identifié — {note}."
        )
    return contacts, avertissements


# ----------------------------------------------------------------------
# Étape C — Apollo.io
# ----------------------------------------------------------------------
def _apollo_search(entreprise, departement, region):
    if not config.APOLLO_API_KEY:
        return [], ["Apollo.io : clé API absente — étape ignorée."]

    url = "https://api.apollo.io/api/v1/mixed_people/search"
    entetes = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": config.APOLLO_API_KEY,
    }
    corps = {
        "q_organization_name": entreprise,
        "person_titles": FILTRES_DEPARTEMENT[departement]["titres"],
        "page": 1,
        "per_page": 25,
    }
    pays = PAYS_PAR_REGION.get(region, [])
    if pays:
        corps["person_locations"] = pays

    try:
        rep = requests.post(url, headers=entetes, json=corps, timeout=config.TIMEOUT)
    except requests.exceptions.Timeout:
        return [], ["Apollo.io : délai dépassé (10 s)."]
    except requests.exceptions.RequestException as e:
        return [], [f"Apollo.io : erreur réseau ({e})."]

    if rep.status_code in (401, 403):
        raise ErreurAPI("Apollo.io : clé API invalide ou accès refusé.", "Apollo.io")
    if rep.status_code == 429:
        raise ErreurAPI("Apollo.io : quota d'appels dépassé.", "Apollo.io")
    if rep.status_code != 200:
        return [], [f"Apollo.io : réponse inattendue (code {rep.status_code})."]

    personnes = (rep.json() or {}).get("people", []) or []
    contacts = []
    for p in personnes:
        org = p.get("organization") or {}
        courriel = p.get("email") or ""
        if courriel.startswith("email_not_unlocked"):
            courriel = ""  # courriel verrouillé sur le plan gratuit Apollo
        contacts.append({
            "Entreprise": entreprise,
            "Prénom": p.get("first_name") or "",
            "Nom": p.get("last_name") or "",
            "Titre": p.get("title") or "",
            "Département": departement,
            "Courriel": courriel,
            "Confiance (%)": "",
            "Ville": org.get("city") or p.get("city") or "",
            "Province/État": org.get("state") or p.get("state") or "",
            "Pays": org.get("country") or p.get("country") or "",
            "Source": "Apollo.io",
            "Date de recherche": _aujourd_hui(),
        })

    avertissements = []
    if not contacts:
        avertissements.append("Apollo.io : aucun contact correspondant.")
    elif all(not c["Courriel"] for c in contacts):
        avertissements.append(
            "Apollo.io : contacts trouvés, mais courriels verrouillés "
            "(plan gratuit). Débloquez-les dans Apollo au besoin."
        )
    return contacts, avertissements


# ----------------------------------------------------------------------
# Étape D — SerpAPI (repli Google)
# ----------------------------------------------------------------------
def _serpapi_fallback(entreprise, departement):
    """Retourne (lien_linkedin, note). lien=None si rien trouvé."""
    if not config.SERPAPI_KEY:
        return None, "SerpAPI : clé absente — pas de repli Google."

    requete = (
        f'site:linkedin.com "{entreprise}" '
        '("Marketing Director" OR "Sales Manager" OR "Directeur Marketing" '
        'OR "Directeur des ventes")'
    )
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": requete,
        "api_key": config.SERPAPI_KEY,
        "num": 5,
    }
    try:
        rep = requests.get(url, params=params, timeout=config.TIMEOUT)
    except requests.exceptions.Timeout:
        return None, "SerpAPI : délai dépassé (10 s)."
    except requests.exceptions.RequestException as e:
        return None, f"SerpAPI : erreur réseau ({e})."

    if rep.status_code == 401:
        raise ErreurAPI("SerpAPI : clé API invalide.", "SerpAPI")
    if rep.status_code == 429:
        raise ErreurAPI("SerpAPI : quota de recherches dépassé.", "SerpAPI")
    if rep.status_code != 200:
        return None, f"SerpAPI : réponse inattendue (code {rep.status_code})."

    for r in (rep.json() or {}).get("organic_results", []) or []:
        lien = r.get("link", "")
        if "linkedin.com" in lien:
            return lien, None
    return None, "SerpAPI : aucune piste LinkedIn trouvée."


# ----------------------------------------------------------------------
# Fonction publique
# ----------------------------------------------------------------------
def rechercher_entreprise(entreprise, departement="Les deux", region="Toutes"):
    """
    Recherche les contacts d'une entreprise.

    Retourne un dict : {"contacts": [...], "avertissements": [...]}.
    `contacts` contient toujours au moins une ligne (une fiche « non trouvé »
    si aucune piste).

    Résilience : si un fournisseur échoue (clé invalide, quota épuisé...), on
    journalise le détail côté serveur (visible dans les logs Vercel) et on passe
    au fournisseur suivant. `ErreurAPI` n'est levée QUE si **tous** les
    fournisseurs tentés échouent (aucun n'a pu répondre) — dans ce cas seulement
    l'utilisateur voit le message générique « Service temporairement indisponible ».
    """
    entreprise = (entreprise or "").strip()
    if not entreprise:
        return {"contacts": [], "avertissements": ["Nom d'entreprise vide."]}

    if departement not in FILTRES_DEPARTEMENT:
        departement = "Les deux"
    if region not in PAYS_PAR_REGION:
        region = "Toutes"

    avertissements = []
    erreurs = []          # ErreurAPI attrapées, par fournisseur
    un_fournisseur_a_repondu = False  # au moins un appel sans erreur bloquante

    # Étapes A / B — Hunter.io
    try:
        contacts, av = _hunter_domain_search(entreprise, departement, region)
        un_fournisseur_a_repondu = True
        avertissements += av
        if contacts:
            return {"contacts": contacts, "avertissements": avertissements}
    except ErreurAPI as e:
        print(f"[recherche] Hunter.io indisponible : {e.message}", flush=True)
        erreurs.append(e)

    # Étape C — Apollo.io
    try:
        contacts, av = _apollo_search(entreprise, departement, region)
        un_fournisseur_a_repondu = True
        avertissements += av
        if contacts:
            return {"contacts": contacts, "avertissements": avertissements}
    except ErreurAPI as e:
        print(f"[recherche] Apollo.io indisponible : {e.message}", flush=True)
        erreurs.append(e)

    # Étape D — SerpAPI (repli Google)
    try:
        lien, note = _serpapi_fallback(entreprise, departement)
        un_fournisseur_a_repondu = True
        if note:
            avertissements.append(note)
        if lien:
            fiche = _fiche_vide(
                entreprise,
                "Piste LinkedIn — vérification manuelle requise",
                source=lien,
            )
            return {"contacts": [fiche], "avertissements": avertissements}
    except ErreurAPI as e:
        print(f"[recherche] SerpAPI indisponible : {e.message}", flush=True)
        erreurs.append(e)

    # Tous les fournisseurs tentés ont échoué en erreur bloquante : on remonte.
    if erreurs and not un_fournisseur_a_repondu:
        raise ErreurAPI(
            "Tous les fournisseurs de données sont indisponibles : "
            + " | ".join(e.message for e in erreurs))

    # Aucune piste (mais au moins un fournisseur a répondu normalement).
    fiche = _fiche_vide(entreprise, "Non trouvé — vérification manuelle requise")
    return {"contacts": [fiche], "avertissements": avertissements}
