"""Mandats privés : contrôle admin, propriétaire et CSRF sur toutes les actions."""
import json
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import exiger_admin, valider_csrf
from database import DossierRecherche, EntrepriseDossier, ImportMandat, Utilisateur, get_db
import mandats as m
import mandats_recherche as moteur
from recherche import FILTRES_DEPARTEMENT, PAYS_PAR_REGION
from templating import rendre


async def proteger_action(request: Request):
    if request.method == "POST":
        form = await request.form()
        if not valider_csrf(request, str(form.get("csrf_token", ""))):
            raise HTTPException(403, "Session expirée. Rechargez la page avant de réessayer.")


router = APIRouter(prefix="/admin/mandats", dependencies=[Depends(exiger_admin), Depends(proteger_action)])
legacy_router = APIRouter(prefix="/app/dossiers", dependencies=[Depends(exiger_admin), Depends(proteger_action)])


@legacy_router.get("")
@legacy_router.get("/{chemin:path}")
def ancien(chemin: str = ""):
    cible = f"/{chemin}" if chemin.isdigit() else ""
    return RedirectResponse("/admin/mandats" + cible, status_code=303)


@legacy_router.post("")
@legacy_router.post("/{chemin:path}")
def ancienne_action(chemin: str = ""):
    raise HTTPException(410, "Cet espace a été remplacé par Mandats de recherche dans l’administration.")


def base(d):
    return f"/admin/mandats/{d.id}"


def mandat(db, u, ident):
    d = db.query(DossierRecherche).filter_by(id=ident, utilisateur_id=u.id).first()
    if d is None:
        raise HTTPException(404, "Mandat introuvable.")
    return d


def entreprise(db, d, ident):
    e = db.query(EntrepriseDossier).filter_by(id=ident, dossier_id=d.id).first()
    if e is None:
        raise HTTPException(404, "Organisation introuvable.")
    return e


def importation(db, d, u, ident):
    imp = db.query(ImportMandat).filter_by(id=ident, dossier_id=d.id, utilisateur_id=u.id).first()
    if not imp or imp.consomme or imp.cree_le < datetime.utcnow() - timedelta(hours=24):
        raise HTTPException(410, "Cet aperçu a expiré ou a déjà été importé. Téléversez de nouveau le fichier.")
    return imp


def revision(form):
    try:
        return int(form.get("revision", ""))
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, "Version de fiche manquante. Rechargez la page.") from exc


def ecrire(db, e, numero, valeurs):
    valeurs = dict(valeurs, revision=numero + 1, mise_a_jour=datetime.utcnow())
    n = db.query(EntrepriseDossier).filter_by(id=e.id, dossier_id=e.dossier_id, revision=numero).update(
        valeurs, synchronize_session=False)
    if n != 1:
        db.rollback()
        raise HTTPException(409, "Cette fiche a été modifiée dans un autre onglet. Rechargez-la pour éviter d’écraser les changements.")


def page(request, template, u, status=200, **contexte):
    r = rendre(request, template, utilisateur=u, etats=m.ETATS, verifications=m.VERIFICATIONS,
               courriels=m.COURRIELS, tailles=m.TAILLES, champs_import=m.CHAMPS_IMPORT, **contexte)
    r.status_code = status
    r.headers["Cache-Control"] = "no-store"
    return r


def vue_mandat(request, db, u, d, **extra):
    es = db.query(EntrepriseDossier).filter_by(dossier_id=d.id).order_by(EntrepriseDossier.id).all()
    return page(request, "mandat.html", u, mandat=d, entreprises=es, stats=m.statistiques(es),
                contacts_par_org={e.id: m.contacts_de(e) for e in es}, **extra)


def vue_fiche(request, u, d, e, **extra):
    return page(request, "mandat_fiche.html", u, mandat=d, entreprise=e,
                contacts=m.contacts_de(e), pistes=json.loads(e.pistes_json or "[]"),
                recherches=m.recherches(e), apis=moteur.disponibles(), departements=FILTRES_DEPARTEMENT,
                regions=PAYS_PAR_REGION, donnees_import=json.loads(e.donnees_import_json or "[]"), **extra)


@router.get("")
def liste(request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    ds = db.query(DossierRecherche).filter_by(utilisateur_id=u.id).order_by(DossierRecherche.debut.desc()).all()
    return page(request, "mandats.html", u, mandats=ds,
                statistiques={d.id: m.statistiques(d.entreprises) for d in ds})


@router.post("")
def creer(request: Request, nom: str = Form(...), u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    nom = m.nettoyer(nom)
    if not nom or len(nom) > 160:
        raise HTTPException(400, "Donnez un nom au mandat (160 caractères maximum).")
    d = DossierRecherche(utilisateur_id=u.id, nom=nom)
    db.add(d)
    db.commit()
    return RedirectResponse(base(d), status_code=303)


@router.get("/{ident}")
def detail(ident: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    return vue_mandat(request, db, u, mandat(db, u, ident))


@router.post("/{ident}/parametres")
async def parametres(ident: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    f = await request.form()
    try:
        nom = m.champ(f, "nom", 160, True)
        temps = int(f.get("temps_minutes", 0))
        budget = int(f.get("budget_minutes", 480))
        if not 0 <= temps <= 100000 or not 60 <= budget <= 10000:
            raise ValueError("Le temps saisi ou le budget est hors limites.")
    except ValueError as exc:
        return vue_mandat(request, db, u, d, erreur=str(exc), status=400)
    d.nom, d.temps_minutes, d.budget_minutes = nom, temps, budget
    db.commit()
    return RedirectResponse(base(d), status_code=303)


@router.post("/{ident}/organisations")
async def ajouter_organisation(ident: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    f = await request.form()
    try:
        valeurs = m.organisation(f)
        if m.trouver_doublon(valeurs, [dict(nom=e.nom, pays=e.pays) for e in d.entreprises]):
            raise ValueError("Cette organisation figure déjà dans le mandat. Ouvrez sa fiche pour la compléter.")
    except ValueError as exc:
        return vue_mandat(request, db, u, d, erreur=str(exc), saisie=dict(f), status=400)
    e = EntrepriseDossier(dossier_id=d.id, **valeurs)
    db.add(e)
    db.commit()
    return RedirectResponse(base(d) + f"/organisations/{e.id}", status_code=303)


@router.post("/{ident}/preparer")
def preparer(ident: int, request: Request, fichier: UploadFile = File(...),
             ligne_entete: int = Form(1), feuille: int = Form(1),
             u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    try:
        donnees = m.lire_fichier(fichier, ligne_entete, feuille)
    except ValueError as exc:
        return vue_mandat(request, db, u, d, erreur=str(exc), status=400)
    db.query(ImportMandat).filter(ImportMandat.utilisateur_id == u.id,
        ImportMandat.cree_le < datetime.utcnow() - timedelta(hours=24)).delete(synchronize_session=False)
    imp = ImportMandat(id=uuid4().hex, dossier_id=d.id, utilisateur_id=u.id,
        fichier=(fichier.filename or "liste")[:255], donnees_json=json.dumps(donnees, ensure_ascii=False))
    db.add(imp)
    db.commit()
    return RedirectResponse(base(d) + f"/imports/{imp.id}", status_code=303)


@router.get("/{ident}/imports/{token}")
def correspondance(ident: int, token: str, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    imp = importation(db, d, u, token)
    donnees = json.loads(imp.donnees_json)
    return page(request, "mandat_import.html", u, mandat=d, importation=imp, donnees=donnees,
                mapping=json.loads(imp.mapping_json).get("colonnes") or m.proposer_mapping(donnees["entetes"]))


@router.post("/{ident}/imports/{token}/mapper")
async def mapper(ident: int, token: str, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    imp = importation(db, d, u, token)
    donnees = json.loads(imp.donnees_json)
    f = await request.form()
    try:
        mapping = m.valider_mapping(f, donnees["entetes"])
    except ValueError as exc:
        return page(request, "mandat_import.html", u, mandat=d, importation=imp, donnees=donnees,
                    mapping=dict(f), erreur=str(exc), status=400)
    imp.mapping_json = json.dumps({"colonnes": mapping, "jeton": uuid4().hex})
    db.commit()
    return RedirectResponse(base(d) + f"/imports/{imp.id}/apercu", status_code=303)


@router.get("/{ident}/imports/{token}/apercu")
def apercu(ident: int, token: str, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    imp = importation(db, d, u, token)
    config = json.loads(imp.mapping_json)
    if "colonnes" not in config:
        return RedirectResponse(base(d) + f"/imports/{imp.id}", status_code=303)
    lignes = m.preparer_import(json.loads(imp.donnees_json), config["colonnes"], d.entreprises)
    return page(request, "mandat_apercu.html", u, mandat=d, importation=imp, lignes=lignes,
                jeton=config["jeton"], comptes={etat: sum(l["etat"] == etat for l in lignes)
                                               for etat in ("nouvelle", "doublon", "invalide")})


@router.post("/{ident}/imports/{token}/confirmer")
async def confirmer(ident: int, token: str, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    imp = importation(db, d, u, token)
    f = await request.form()
    config = json.loads(imp.mapping_json)
    if not config.get("jeton") or f.get("jeton") != config["jeton"]:
        raise HTTPException(409, "La correspondance a changé. Consultez de nouveau l’aperçu.")
    mode = f.get("doublons", "ignorer")
    if mode not in ("ignorer", "completer"):
        raise HTTPException(400, "Choix de traitement des doublons invalide.")
    donnees = json.loads(imp.donnees_json)
    es = db.query(EntrepriseDossier).filter_by(dossier_id=d.id).order_by(EntrepriseDossier.id).all()
    lignes = m.preparer_import(donnees, config["colonnes"], es)
    invalides = sum(l["etat"] == "invalide" for l in lignes)
    if invalides and f.get("ignorer_invalides") != "on":
        raise HTTPException(400, "Confirmez l’exclusion des lignes invalides dans l’aperçu.")
    verrou = db.query(ImportMandat).filter_by(id=imp.id, consomme=False).update(
        {"consomme": True}, synchronize_session=False)
    if verrou != 1:
        db.rollback()
        raise HTTPException(409, "Cet import a déjà été confirmé.")
    copies = [dict(id=e.id, nom=e.nom, pays=e.pays, original=e,
                   valeurs={k: getattr(e, k) or "" for k in m.CHAMPS_IMPORT},
                   bruts=json.loads(e.donnees_import_json or "[]"), modifie=False) for e in es]
    ajout = fusion = ignore = 0
    for ligne in lignes:
        if ligne["etat"] == "invalide":
            continue
        valeurs = ligne["valeurs"]
        existant = m.trouver_doublon(valeurs, copies)
        if existant and mode == "ignorer":
            ignore += 1
            continue
        brut = dict(fichier=imp.fichier, colonnes=donnees["entetes"], valeurs=donnees["lignes"][ligne["index"]])
        if existant:
            for k in m.CHAMPS_IMPORT:
                nouveau, actuel = valeurs[k], existant["valeurs"][k]
                if not actuel:
                    existant["valeurs"][k] = nouveau
                elif k in ("prix", "note", "sources", "durabilite") and nouveau and nouveau not in actuel.split("\n"):
                    existant["valeurs"][k] = actuel + "\n" + nouveau
            existant["bruts"].append(brut)
            existant["modifie"] = True
            existant["pays"] = existant["valeurs"]["pays"]
            fusion += 1
        else:
            copies.append(dict(id=None, nom=valeurs["nom"], pays=valeurs["pays"], valeurs=valeurs,
                               bruts=[brut], modifie=True))
            ajout += 1
    for copie in copies:
        if not copie["modifie"]:
            continue
        valeurs = dict(copie["valeurs"], donnees_import_json=json.dumps(copie["bruts"], ensure_ascii=False))
        if copie["id"] is None:
            db.add(EntrepriseDossier(dossier_id=d.id, **valeurs))
        else:
            ecrire(db, copie["original"], copie["original"].revision, valeurs)
    db.query(ImportMandat).filter_by(id=imp.id).update({"donnees_json": "{}"}, synchronize_session=False)
    db.commit()
    db.expire_all()
    return vue_mandat(request, db, u, d,
        message=f"Import terminé : {ajout} ajout(s), {fusion} ligne(s) fusionnée(s), {ignore} doublon(s) ignoré(s), {invalides} ligne(s) invalide(s) exclue(s).")


@router.get("/{ident}/organisations/{eid}")
def fiche(ident: int, eid: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    return vue_fiche(request, u, d, entreprise(db, d, eid))


@router.post("/{ident}/organisations/{eid}")
async def sauver_organisation(ident: int, eid: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    e = entreprise(db, d, eid)
    f = await request.form()
    try:
        valeurs = m.organisation(f)
        if m.trouver_doublon(valeurs, [dict(nom=x.nom, pays=x.pays) for x in d.entreprises if x.id != e.id]):
            raise ValueError("Une autre fiche porte déjà ce nom dans le même pays. Vérifiez le doublon.")
    except ValueError as exc:
        return vue_fiche(request, u, d, e, erreur=str(exc), saisie=dict(f), status=400)
    ecrire(db, e, revision(f), valeurs)
    db.commit()
    return RedirectResponse(base(d) + f"/organisations/{eid}?enregistre=1", status_code=303)


@router.post("/{ident}/organisations/{eid}/contacts")
async def sauver_contact(ident: int, eid: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    e = entreprise(db, d, eid)
    f = await request.form()
    cid = str(f.get("contact_id", ""))
    cs = m.contacts_de(e)
    ancien = next((c for c in cs if c["id"] == cid), None)
    if cid and not ancien:
        raise HTTPException(404, "Contact introuvable dans cette organisation.")
    try:
        c = m.contact(f)
        if not ancien and len(cs) >= 100:
            raise ValueError("Cette organisation a déjà 100 contacts. Modifiez les fiches existantes.")
    except ValueError as exc:
        return vue_fiche(request, u, d, e, erreur=str(exc), saisie_contact=dict(f), contact_erreur=cid, status=400)
    if ancien:
        ancien.update(c)
    else:
        c.update(id=uuid4().hex, provenance="Saisie manuelle", date_recherche=datetime.utcnow().date().isoformat())
        cs.append(c)
    ecrire(db, e, revision(f), {"contacts_json": json.dumps(cs, ensure_ascii=False)})
    db.commit()
    return RedirectResponse(base(d) + f"/organisations/{eid}?enregistre=1#contacts", status_code=303)


@router.post("/{ident}/organisations/{eid}/rechercher")
async def rechercher(ident: int, eid: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    e = entreprise(db, d, eid)
    f = await request.form()
    numero = revision(f)
    if e.revision != numero:
        raise HTTPException(409, "Cette fiche a changé. Rechargez-la avant de lancer la recherche.")
    try:
        nouveaux, pistes, message = await run_in_threadpool(moteur.chercher, e,
            str(f.get("service", "")), str(f.get("departement", "Les deux")), str(f.get("region", "Toutes")))
    except ValueError as exc:
        return vue_fiche(request, u, d, e, erreur=str(exc), status=400)
    cs = m.contacts_de(e)
    cles = {(m.normaliser(c["nom"]), m.normaliser(c["poste"])) for c in cs}
    ajoutes = 0
    for c in nouveaux:
        cle = (m.normaliser(c["nom"]), m.normaliser(c["poste"]))
        if cle not in cles and len(cs) < 100:
            cs.append(c)
            cles.add(cle)
            ajoutes += 1
    anciennes = json.loads(e.pistes_json or "[]")
    connues = {p["url"] for p in anciennes}
    for p in pistes:
        if p["url"] not in connues:
            anciennes.append(p)
            connues.add(p["url"])
    ecrire(db, e, numero, {"contacts_json": json.dumps(cs, ensure_ascii=False),
                           "pistes_json": json.dumps(anciennes[:100], ensure_ascii=False)})
    db.commit()
    db.refresh(e)
    return vue_fiche(request, u, d, e, message=f"{ajoutes} suggestion(s) ajoutée(s). {message}")


@router.get("/{ident}/export")
def exporter(ident: int, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    es = db.query(EntrepriseDossier).filter_by(dossier_id=d.id).order_by(EntrepriseDossier.id).all()
    return Response(m.excel(d, es), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="mandat-{d.id}.xlsx"', "Cache-Control": "no-store"})
