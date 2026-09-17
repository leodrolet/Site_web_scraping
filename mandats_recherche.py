"""Une organisation / un fournisseur / une page par requête. Aucune extraction de profil."""
from datetime import date
from urllib.parse import urlparse
from uuid import uuid4

import config
import recherche
from mandats import url

SERVICES = {"hunter": ("Hunter", "HUNTER_API_KEY"), "apollo": ("Apollo", "APOLLO_API_KEY"),
            "serpapi": ("SerpAPI", "SERPAPI_KEY")}


def disponibles():
    return {cle: {"nom": nom, "actif": bool(getattr(config, variable))}
            for cle, (nom, variable) in SERVICES.items()}


def chercher(ent, service, departement, region):
    if service not in SERVICES or not disponibles()[service]["actif"]:
        raise ValueError("Ce fournisseur n’est pas configuré. Les liens de recherche et la saisie manuelle restent disponibles.")
    if departement not in recherche.FILTRES_DEPARTEMENT or region not in recherche.PAYS_PAR_REGION:
        raise ValueError("Département ou zone de recherche invalide.")
    try:
        if service == "serpapi":
            titres = recherche.FILTRES_DEPARTEMENT[departement]["titres"][:5]
            query = f'site:linkedin.com/in/ "{ent.nom}" (' + " OR ".join(f'"{t}"' for t in titres) + ")"
            if region != "Toutes":
                query += " " + region
            pistes, note = recherche._serpapi_fallback(ent.nom, departement, max_pistes=5, requete=query)
            if not pistes and note and "aucune piste" not in note.lower():
                raise ValueError("Fournisseur indisponible.")
            return [], [{"url": url(p), "provenance": "SerpAPI", "date": date.today().isoformat()}
                        for p in pistes], "Recherche terminée. Les liens sont des pistes à examiner manuellement."
        if service == "hunter":
            bruts, notes = recherche._hunter_domain_search(ent.nom, departement, region, besoin=5,
                domaine_cible=urlparse(ent.site).hostname if ent.site else None, max_pages=1, avec_sources=True)
        else:
            bruts, notes = recherche._apollo_search(ent.nom, departement, region, besoin=5, max_pages=1, avec_sources=True)
        if not bruts and any(any(mot in n.lower() for mot in ("délai", "erreur", "inattendue", "clé api absente")) for n in notes):
            raise ValueError("Fournisseur indisponible.")
    except Exception as exc:
        # Ne renvoie jamais les messages requests : ils peuvent contenir l'URL et la clé API.
        raise ValueError("Le fournisseur n’a pas pu répondre. Vérifiez sa configuration ou réessayez plus tard.") from exc
    contacts = []
    for brut in recherche._trier_pertinence(bruts)[:10]:
        nom = " ".join(filter(None, [brut.get("Prénom"), brut.get("Nom")])).strip()
        if not nom:
            continue
        sources = []
        for valeur in brut.get("URLs sources", []):
            try:
                if valeur:
                    sources.append(url(valeur))
            except ValueError:
                continue
        courriel = brut.get("Courriel") or ""
        contacts.append(dict(id=uuid4().hex, nom=nom, poste=brut.get("Titre") or "",
            departement=brut.get("Département") or "", region=brut.get("Région personne") or "",
            langue="", courriel=courriel, courriel_statut="a_verifier" if courriel else "non_trouve",
            source="\n".join(dict.fromkeys(sources)), source_courriel="", date_verification="",
            verification="a_verifier", retenu=False, provenance=SERVICES[service][0],
            date_recherche=date.today().isoformat(),
            note="Suggestion du fournisseur. Organisation annoncée : " + (brut.get("Organisation source") or "non précisée") +
                 ". Confirmer l’emploi actuel, le périmètre géographique et la capacité à communiquer en anglais."))
    return contacts, [], "Recherche terminée : suggestions à vérifier, aucun contact retenu automatiquement."
