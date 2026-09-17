"""Documents privés persistants et validation progressive, un bloc par sauvegarde."""
import hashlib
import json
from uuid import uuid4

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from auth import exiger_admin
from database import DocumentMandat, EntrepriseDossier, Utilisateur, get_db
import mandats as m
import mandats_documents as md
from routes.mandat_routes import router, mandat, entreprise, base, page, ecrire


def document(db, d, token):
    doc = db.query(DocumentMandat).filter_by(id=token, dossier_id=d.id).first()
    if not doc:
        raise HTTPException(404, 'Document introuvable.')
    return doc


def lien(d, doc):
    return base(d) + '/documents/' + doc.id


def vue(request, u, d, doc, numero=0, **extras):
    items = json.loads(doc.propositions_json)
    if items and not 0 <= numero < len(items):
        raise HTTPException(404, 'Bloc introuvable.')
    return page(request, 'mandat_document.html', u, mandat=d, document=doc, propositions=items,
        numero=numero, item=items[numero] if items else None, **extras)


@router.get('/{ident}/documents')
def liste_documents(ident: int, request: Request, u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    return page(request, 'mandat_documents.html', u, mandat=d, documents=d.documents)


@router.post('/{ident}/documents')
def recevoir(ident: int, request: Request, fichier: UploadFile = File(...), genre: str = Form(...), feuille: int = Form(1),
             u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    try:
        nom = fichier.filename or ''
        if nom.lower().endswith('.doc'):
            raise ValueError('Le format ancien .doc ne peut pas être converti sur Vercel. Ouvrez le fichier dans Word ou LibreOffice, choisissez Enregistrer sous → .docx, puis importez cette copie. Vérifiez que les passages rouges sont conservés. L’original reste intact.')
        ext = {'word': '.docx', 'blocs': '.xlsx'}.get(genre)
        if not ext or not nom.lower().endswith(ext):
            raise ValueError('Choisissez un fichier .docx pour Word ou .xlsx pour les blocs Excel.')
        brut = fichier.file.read(md.MAX_BYTES + 1)
        items = md.lire_word(brut) if genre == 'word' else md.lire_blocs(brut, feuille)
    except ValueError as exc:
        return page(request, 'mandat_documents.html', u, mandat=d, documents=d.documents, erreur=str(exc), status=400)
    doc = DocumentMandat(id=uuid4().hex, dossier_id=d.id, fichier=nom[:255], genre=genre,
        original=brut, propositions_json=json.dumps(items, ensure_ascii=False))
    db.add(doc); db.commit()
    return RedirectResponse(lien(d, doc), status_code=303)


@router.get('/{ident}/documents/{token}')
def apercu_document(ident: int, token: str, request: Request, bloc: int = 0,
                   u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident)
    return vue(request, u, d, document(db, d, token), bloc)


@router.post('/{ident}/documents/{token}/blocs/{numero}')
async def confirmer_bloc(ident: int, token: str, numero: int, request: Request,
                        u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident); doc = document(db, d, token)
    items = json.loads(doc.propositions_json)
    if not 0 <= numero < len(items):
        raise HTTPException(404, 'Bloc introuvable.')
    f = await request.form()
    item = items[numero]
    if item['etat'] != 'a_confirmer':
        raise HTTPException(409, 'Ce bloc est déjà traité. Modifiez la fiche organisation pour corriger ses contacts.')
    try:
        version = int(f.get('revision', '-1'))
        action = f.get('action')
        if action not in ('brouillon', 'confirmer', 'ignorer'):
            raise ValueError('Action inconnue.')
        if version != doc.revision:
            raise HTTPException(409, 'Cet aperçu a changé dans un autre onglet. Rechargez la page.')
        if action != 'ignorer':
            nom = m.champ(f, 'nom', 255)
            if '@' in nom or nom.startswith(('http:', 'https:', 'www.')):
                raise ValueError('Indiquez un nom d’organisation, pas un courriel ou un lien.')
            item['nom'], item['note'] = nom, m.champ(f, 'note', 2000)
            eid = str(f.get('organisation_id', ''))
            cible = entreprise(db, d, int(eid)) if eid.isdigit() else None
            if eid and cible is None:
                raise ValueError('Organisation invalide.')
            item['organisation_id'] = cible.id if cible else None
            contacts = []
            for i in range(12):
                co = {k: m.champ(f, f'c{i}_{k}', 2000 if k in ('note', 'source') else 255)
                      for k in ('nom', 'poste', 'courriel', 'region', 'source', 'note')}
                if not any(co.values()):
                    continue
                co['inclure'] = f.get(f'c{i}_inclure') == 'on'
                if co['inclure'] and action == 'confirmer':
                    m.contact(dict(co, courriel_statut='a_verifier' if co['courriel'] else 'non_trouve'))
                contacts.append(co)
            item['contacts'] = contacts
            if action == 'confirmer':
                if f.get('validation') != 'on':
                    raise ValueError('Confirmez que vous avez vérifié l’association entre ce passage et l’organisation.')
                if cible is None:
                    valeurs = m.organisation({'nom': nom, 'note': item['note']})
                    if m.trouver_doublon(valeurs, [dict(nom=e.nom, pays=e.pays) for e in d.entreprises]):
                        raise ValueError('Une organisation porte déjà ce nom. Choisissez sa fiche dans la liste.')
                    cible = EntrepriseDossier(dossier_id=d.id, **valeurs)
                    db.add(cible); db.flush()
                cs = m.contacts_de(cible)
                for co in contacts:
                    if not co.get('inclure'):
                        continue
                    # Ne remplace jamais un contact existant, en particulier vérifié.
                    if any((co['courriel'] and co['courriel'].casefold() == c['courriel'].casefold()) or
                           m.normaliser(co['nom']) == m.normaliser(c['nom']) for c in cs):
                        continue
                    if len(cs) >= 100:
                        raise ValueError('Limite de 100 contacts atteinte pour cette organisation.')
                    c = m.contact(dict(co, courriel_statut='a_verifier' if co['courriel'] else 'non_trouve'))
                    c.update(id=uuid4().hex, provenance=f'{doc.fichier} · {item["ancre"]}', date_recherche='')
                    cs.append(c)
                bruts = json.loads(cible.donnees_import_json or '[]')
                bruts.append(dict(fichier=doc.fichier, colonnes=['Emplacement', 'Texte original', 'Note de validation'],
                    valeurs=[str(item['ancre']), item['contexte'], item['note']]))
                ecrire(db, cible, cible.revision, dict(contacts_json=json.dumps(cs, ensure_ascii=False),
                    donnees_import_json=json.dumps(bruts, ensure_ascii=False)))
                item['organisation_id'], item['etat'] = cible.id, 'importe'
        else:
            item['etat'] = 'ignore'
        if db.query(DocumentMandat).filter_by(id=doc.id, revision=version).update(
                dict(propositions_json=json.dumps(items, ensure_ascii=False), revision=version+1), synchronize_session=False) != 1:
            db.rollback()
            raise HTTPException(409, 'Cet aperçu a été modifié. Rechargez-le.')
        db.commit()
    except (ValueError, TypeError) as exc:
        db.rollback()
        return vue(request, u, d, doc, numero, erreur=str(exc), saisie=item, status=400)
    suivant = numero if action == 'brouillon' else next((i for i in range(numero+1, len(items)) if items[i]['etat'] == 'a_confirmer'), numero)
    return RedirectResponse(lien(d, doc) + f'?bloc={suivant}', status_code=303)


@router.post('/{ident}/documents/{token}/blocs/{numero}/revoir')
async def revoir_bloc(ident: int, token: str, numero: int, request: Request,
                      u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident); doc = document(db, d, token)
    items = json.loads(doc.propositions_json)
    if not 0 <= numero < len(items):
        raise HTTPException(404, 'Bloc introuvable.')
    f = await request.form()
    if str(doc.revision) != f.get('revision'):
        raise HTTPException(409, 'Cet aperçu a changé. Rechargez-le.')
    items[numero]['etat'] = 'a_confirmer'
    if db.query(DocumentMandat).filter_by(id=doc.id, revision=doc.revision).update(
            dict(propositions_json=json.dumps(items, ensure_ascii=False), revision=doc.revision+1), synchronize_session=False) != 1:
        db.rollback()
        raise HTTPException(409, 'Cet aperçu a changé. Rechargez-le.')
    db.commit()
    return RedirectResponse(lien(d, doc) + f'?bloc={numero}', status_code=303)


def preparer_reponse(d, doc):
    if doc.genre != 'word':
        raise HTTPException(400, 'La réponse nécessite un document Word original importé.')
    es = {e.id: e for e in d.entreprises}
    lignes, insertions = [], {}
    for p in json.loads(doc.propositions_json):
        e = es.get(p.get('organisation_id')) if p['etat'] == 'importe' else None
        cs = md.lignes_reponse(m.contacts_de(e)) if e else []
        lignes.append(dict(contexte=p['contexte'], organisation=e.nom if e else '', textes=cs, etat=p['etat']))
        if cs:
            insertions.setdefault(p['ancre'], []).extend(cs)
    signature = hashlib.sha256(json.dumps([doc.revision, lignes], ensure_ascii=False).encode()).hexdigest()
    return lignes, insertions, signature


@router.get('/{ident}/documents/{token}/reponse')
def apercu_reponse(ident: int, token: str, request: Request,
                  u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident); doc = document(db, d, token)
    lignes, insertions, signature = preparer_reponse(d, doc)
    return page(request, 'mandat_reponse.html', u, mandat=d, document=doc, lignes=lignes,
        signature=signature, nombre=sum(len(v) for v in insertions.values()))


@router.post('/{ident}/documents/{token}/reponse')
async def telecharger_reponse(ident: int, token: str, request: Request,
                             u: Utilisateur = Depends(exiger_admin), db: Session = Depends(get_db)):
    d = mandat(db, u, ident); doc = document(db, d, token)
    _, insertions, signature = preparer_reponse(d, doc)
    f = await request.form()
    if f.get('signature') != signature:
        raise HTTPException(409, 'Les contacts ont changé. Rechargez et vérifiez de nouveau l’aperçu.')
    if f.get('validation') != 'on' or not insertions:
        raise HTTPException(400, 'Vérifiez l’aperçu et retenez au moins un contact associé au Word.')
    try:
        contenu = md.completer_word(doc.original, insertions)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(contenu, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename="reponse-don-{d.id}.docx"', 'Cache-Control': 'no-store'})
