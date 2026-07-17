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


# Pagination des fournisseurs. Plafond de sécurité : sans lui, une seule
# entreprise très fournie pourrait vider le pool de crédits du mois.
#   Hunter : 1 requête Domain Search = 1 crédit, renvoie jusqu'à `limit`
#            courriels. ATTENTION : le plan gratuit PLAFONNE `limit` à 10 —
#            limit=100 provoque un HTTP 400 (pagination_error) sur CHAQUE appel
#            et le moteur ne retourne alors jamais rien. On demande donc 10 par
#            page (valable sur tous les plans) et on pagine via `offset`,
#            chaque page = 1 crédit.
#   Apollo : People Search paginé via `page`/`per_page` (max 100). Les crédits
#            e-mail se consomment au déverrouillage, pas à la recherche.
# 5 pages × 10 = jusqu'à 50 contacts Hunter par entreprise, assez pour couvrir
# le besoin maximal du site (offset 20 + limite 25 = 45).
_HUNTER_LIMITE = 10
_HUNTER_MAX_PAGES = 5
_APOLLO_LIMITE = 100
_APOLLO_MAX_PAGES = 5


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


# Rang de séniorité déduit du poste : plus le rôle est décisionnel, plus le rang
# est élevé. Sert au tri de pertinence (un CMO passe avant un coordinateur).
_RANGS_TITRE = [
    (("chief", "cmo", "cso", "c-level", "cxo"), 5),
    (("vp", "vice-président", "vice president", "vice-president", "svp"), 5),
    (("director", "directeur", "directrice", "head of", "head,", "head ", "chef"), 4),
    (("responsable", "manager", "gérant", "gerant", "lead", "principal"), 3),
    (("marketing", "sales", "vente", "ventes", "growth", "brand",
      "business development", "account"), 2),
]


def _rang_titre(titre):
    t = (titre or "").lower()
    for mots, rang in _RANGS_TITRE:
        if any(m in t for m in mots):
            return rang
    return 1


def _confiance_num(contact):
    c = contact.get("Confiance (%)")
    return c if isinstance(c, (int, float)) else 0


def _trier_pertinence(contacts):
    """Trie une liste de contacts du plus au moins pertinent.

    Critère principal : séniorité du poste (rôle décisionnel d'abord) ; départage
    par le score de confiance natif du fournisseur (Hunter) quand il existe.
    """
    return sorted(
        contacts,
        key=lambda c: (_rang_titre(c.get("Titre")), _confiance_num(c)),
        reverse=True,
    )


# ----------------------------------------------------------------------
# Étapes A / B — Hunter.io
# ----------------------------------------------------------------------
def _hunter_domain_search(entreprise, departement, region, besoin=5):
    """Domain Search Hunter : contacts filtrés (marketing/ventes).

    Récupère au moins `besoin` contacts pertinents en paginant via `offset`
    (jusqu'à `_HUNTER_MAX_PAGES` pages), puis s'arrête. Chaque page = 1 crédit
    Hunter ; comme une page couvre déjà 100 courriels, `besoin` petit = 1 seul
    appel dans l'immense majorité des cas. Les erreurs bloquantes (401/429) sur
    la PREMIÈRE page se comportent comme avant ; sur une page suivante, on garde
    les contacts déjà obtenus au lieu de tout perdre.
    """
    if not config.HUNTER_API_KEY:
        return [], ["Hunter.io : clé API absente — étape ignorée."]

    url = "https://api.hunter.io/v2/domain-search"
    cibles_hunter = FILTRES_DEPARTEMENT[departement]["hunter"]
    contacts = []
    domaine = modele = None
    pays = etat = ville = ""

    for page in range(_HUNTER_MAX_PAGES):
        params = {
            "company": entreprise,
            "api_key": config.HUNTER_API_KEY,
            "limit": _HUNTER_LIMITE,
            "offset": page * _HUNTER_LIMITE,
        }
        try:
            rep = requests.get(url, params=params, timeout=config.TIMEOUT)
        except requests.exceptions.Timeout:
            if page == 0:
                return [], ["Hunter.io : délai dépassé (10 s)."]
            break
        except requests.exceptions.RequestException as e:
            if page == 0:
                return [], [f"Hunter.io : erreur réseau ({e})."]
            break

        if rep.status_code == 401:
            if page == 0:
                raise ErreurAPI("Hunter.io : clé API invalide ou manquante.", "Hunter.io")
            break
        if rep.status_code == 429:
            if page == 0:
                raise ErreurAPI("Hunter.io : quota mensuel dépassé.", "Hunter.io")
            break
        if rep.status_code != 200:
            if page == 0:
                return [], [f"Hunter.io : réponse inattendue (code {rep.status_code})."]
            break

        data = (rep.json() or {}).get("data", {}) or {}
        if page == 0:
            domaine = data.get("domain")
            modele = data.get("pattern")          # ex : {first}.{last}
            pays = data.get("country") or ""
            etat = data.get("state") or ""
            ville = data.get("city") or ""

        emails = data.get("emails", []) or []
        for courriel in emails:
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

        # Assez de contacts pour la tranche demandée, ou page incomplète.
        if len(contacts) >= besoin or len(emails) < _HUNTER_LIMITE:
            break

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
def _apollo_search(entreprise, departement, region, besoin=5):
    """People Search Apollo : contacts pertinents, paginé (jusqu'à besoin, max 5 pages)."""
    if not config.APOLLO_API_KEY:
        return [], ["Apollo.io : clé API absente — étape ignorée."]

    url = "https://api.apollo.io/api/v1/mixed_people/search"
    entetes = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": config.APOLLO_API_KEY,
    }
    pays = PAYS_PAR_REGION.get(region, [])
    contacts = []

    for page in range(1, _APOLLO_MAX_PAGES + 1):
        corps = {
            "q_organization_name": entreprise,
            "person_titles": FILTRES_DEPARTEMENT[departement]["titres"],
            "page": page,
            "per_page": _APOLLO_LIMITE,
        }
        if pays:
            corps["person_locations"] = pays

        try:
            rep = requests.post(url, headers=entetes, json=corps, timeout=config.TIMEOUT)
        except requests.exceptions.Timeout:
            if page == 1:
                return [], ["Apollo.io : délai dépassé (10 s)."]
            break
        except requests.exceptions.RequestException as e:
            if page == 1:
                return [], [f"Apollo.io : erreur réseau ({e})."]
            break

        if rep.status_code in (401, 403):
            if page == 1:
                raise ErreurAPI("Apollo.io : clé API invalide ou accès refusé.", "Apollo.io")
            break
        if rep.status_code == 429:
            if page == 1:
                raise ErreurAPI("Apollo.io : quota d'appels dépassé.", "Apollo.io")
            break
        if rep.status_code != 200:
            if page == 1:
                return [], [f"Apollo.io : réponse inattendue (code {rep.status_code})."]
            break

        charge = rep.json() or {}
        personnes = charge.get("people", []) or []
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

        # Fin de pagination : assez de contacts, page incomplète, ou dernière page.
        pagination = charge.get("pagination") or {}
        total_pages = pagination.get("total_pages")
        if len(contacts) >= besoin or len(personnes) < _APOLLO_LIMITE:
            break
        if total_pages and page >= total_pages:
            break

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
def rechercher_entreprise(entreprise, departement="Les deux", region="Toutes",
                         limite=5, offset=0):
    """
    Recherche les contacts d'une entreprise, triés par pertinence.

    `limite` : nombre max de contacts renvoyés (5 par défaut).
    `offset` : rang de départ dans la liste triée — sert au « Voir plus »
               (offset=5 renvoie les contacts 6 à 10, du MÊME fournisseur, la
               chaîne de repli étant déterministe).

    Retourne {"contacts": [...], "avertissements": [...]}. Pour offset=0, la
    liste contient toujours au moins une ligne (fiche « non trouvé » sinon) ;
    pour offset>0, elle peut être vide (plus rien à montrer).

    Résilience et repli (Hunter -> Apollo -> SerpAPI) et gestion d'erreurs
    bloquantes : identiques à avant. `ErreurAPI` n'est levée que si TOUS les
    fournisseurs tentés échouent.
    """
    resultat = _rechercher(entreprise, departement, region, limite, offset)
    # Trace serveur (logs Vercel) : sans elle, une panne fournisseur (clé
    # absente, quota, plan trop bas...) est invisible et se confond avec un
    # simple « aucun résultat ». Jamais montré à l'utilisateur.
    for note in resultat["avertissements"]:
        print(f"[recherche] {entreprise!r} : {note}", flush=True)
    return resultat


def _rechercher(entreprise, departement, region, limite, offset):
    entreprise = (entreprise or "").strip()
    if not entreprise:
        return {"contacts": [], "avertissements": ["Nom d'entreprise vide."]}

    if departement not in FILTRES_DEPARTEMENT:
        departement = "Les deux"
    if region not in PAYS_PAR_REGION:
        region = "Toutes"

    limite = max(1, min(limite, 25))
    offset = max(0, offset)
    besoin = offset + limite

    def tranche(contacts):
        return _trier_pertinence(contacts)[offset:offset + limite]

    avertissements = []
    erreurs = []          # ErreurAPI attrapées, par fournisseur
    un_fournisseur_a_repondu = False  # au moins un appel sans erreur bloquante
    # NB : une étape sautée faute de clé ne compte PAS comme une réponse —
    # sinon, avec aucune clé configurée, l'utilisateur verrait « Non trouvé »
    # au lieu de « Service temporairement indisponible ».

    # Étapes A / B — Hunter.io
    if not config.HUNTER_API_KEY:
        avertissements.append("Hunter.io : clé API absente — étape ignorée.")
    else:
        try:
            contacts, av = _hunter_domain_search(entreprise, departement, region, besoin)
            un_fournisseur_a_repondu = True
            avertissements += av
            if contacts:
                return {"contacts": tranche(contacts), "avertissements": avertissements}
        except ErreurAPI as e:
            print(f"[recherche] Hunter.io indisponible : {e.message}", flush=True)
            erreurs.append(e)

    # Étape C — Apollo.io
    if not config.APOLLO_API_KEY:
        avertissements.append("Apollo.io : clé API absente — étape ignorée.")
    else:
        try:
            contacts, av = _apollo_search(entreprise, departement, region, besoin)
            un_fournisseur_a_repondu = True
            avertissements += av
            if contacts:
                return {"contacts": tranche(contacts), "avertissements": avertissements}
        except ErreurAPI as e:
            print(f"[recherche] Apollo.io indisponible : {e.message}", flush=True)
            erreurs.append(e)

    # Étape D — SerpAPI (repli Google) : une seule piste LinkedIn, jamais paginée.
    # Sans objet pour un « Voir plus » (offset>0) -> on ne la renvoie qu'au 1er appel.
    if offset == 0:
        if not config.SERPAPI_KEY:
            avertissements.append("SerpAPI : clé absente — pas de repli Google.")
        else:
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

    # Aucun fournisseur n'a réellement été interrogé (clés absentes) ou tous
    # ont échoué en erreur bloquante : on remonte, l'interface affichera le
    # message « Service temporairement indisponible ».
    if not un_fournisseur_a_repondu:
        if erreurs:
            raise ErreurAPI(
                "Tous les fournisseurs de données sont indisponibles : "
                + " | ".join(e.message for e in erreurs))
        raise ErreurAPI(
            "Aucun fournisseur de données n'est configuré "
            "(clés API absentes de l'environnement).")

    # « Voir plus » sans résultat supplémentaire -> liste vide (pas de fiche).
    if offset > 0:
        return {"contacts": [], "avertissements": avertissements}

    # Aucune piste (mais au moins un fournisseur a répondu normalement).
    fiche = _fiche_vide(entreprise, "Non trouvé — vérification manuelle requise")
    return {"contacts": [fiche], "avertissements": avertissements}
