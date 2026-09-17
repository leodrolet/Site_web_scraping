"""Fixtures entièrement fictives. Aucun document de Lyse ne figure dans les tests."""
import io
import json
import re
import unittest
import zipfile
from xml.sax.saxutils import escape
from openpyxl import Workbook

import test_mandats as precedent
from database import DocumentMandat, EntrepriseDossier
import mandats_documents as md


def word():
    out = io.BytesIO()
    body = '<w:p><w:r><w:t>Fournisseur : </w:t></w:r><w:r><w:rPr><w:color w:val="EE0000"/></w:rPr><w:t>Atelier Boréal Fictif</w:t></w:r></w:p>'
    body += '<w:p><w:r><w:rPr><w:color w:val="FF0000"/></w:rPr><w:t>Ms Jane Exemple, Marketing Manager</w:t></w:r></w:p>'
    body += '<w:tbl><w:tr><w:tc><w:p><w:r><w:rPr><w:rStyle w:val="Red"/></w:rPr><w:t>Fabricant Exemple</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="{md.W}"><w:body>{body}</w:body></w:document>')
        z.writestr('word/styles.xml', f'<w:styles xmlns:w="{md.W}"><w:style w:styleId="Red"><w:rPr><w:color w:val="FF0000"/></w:rPr></w:style></w:styles>')
        z.writestr('word/media/test.bin', b'contenu conserve')
    return out.getvalue()


def excel():
    w = Workbook(); s = w.active
    for cell, value in {'B2':'Fournisseur Fictif','B3':'Alex Exemple','B4':'Sales Manager','B5':'alex@example.org','B6':'Canada',
                        'E3':'Camille Exemple','E4':'Marketing Director','E5':'camille@example.org','E6':'could try',
                        'B10':'Personne Exemple','B11':'Sales Director','B12':'personne@example.org'}.items():
        s[cell] = value
    out = io.BytesIO(); w.save(out); return out.getvalue()


class DocumentsTest(unittest.TestCase):
    setUp = precedent.MandatsTest.setUp
    tearDown = precedent.MandatsTest.tearDown
    call = precedent.MandatsTest.call
    org = precedent.MandatsTest.org

    def upload(self, kind='word', data=None):
        status, _, h = self.call('POST', self.base+'/documents', {'genre':kind},
            fichier=('fictif.docx' if kind=='word' else 'fictif.xlsx', data or (word() if kind=='word' else excel())))
        self.assertEqual(status,303)
        url = h[b'location'].decode()
        return url, self.db.get(DocumentMandat,url.rsplit('/',1)[1])

    def confirm(self, url, bloc=0, **values):
        return self.call('POST',url+f'/blocs/{bloc}',dict(revision='0',action='confirmer',nom='Atelier Boréal Fictif',validation='on',**values))

    def test_word_couleurs_personne_table_et_fidelite(self):
        raw=word(); ps=md.lire_word(raw)
        self.assertEqual(len(ps),3)
        self.assertEqual(ps[1]['nom'],'')
        self.assertEqual(ps[2]['nom'],'Fabricant Exemple')
        updated=md.completer_word(raw,{0:['Alex Exemple — courriel non trouvé']})
        with zipfile.ZipFile(io.BytesIO(updated)) as out, zipfile.ZipFile(io.BytesIO(raw)) as before:
            self.assertEqual(out.read('word/styles.xml'),before.read('word/styles.xml'))
            self.assertEqual(out.read('word/media/test.bin'),before.read('word/media/test.bin'))
            d=md.xml(out.read('word/document.xml'))
            self.assertIn('FF0000',out.read('word/document.xml').decode())
            self.assertIn('Atelier Boréal Fictif',md.texte(d))
            self.assertIn('courriel non trouvé',md.texte(d))

    def test_blocs_ambigus_et_adresse_non_confirmee(self):
        ps=md.lire_blocs(excel())
        self.assertEqual(ps[0]['nom'],'Fournisseur Fictif')
        self.assertEqual(len(ps[0]['contacts']),2)
        self.assertEqual(ps[1]['nom'],'')
        self.assertIn('could try',ps[0]['contacts'][1]['note'])
        self.assertEqual(ps[0]['contacts'][0]['region'],'Canada')

    def test_acces_csrf_et_documents_prives(self):
        url,doc=self.upload()
        for target in [self.base+'/documents',url,url+'/reponse']:
            for user in ['public','anonyme','autre']:
                self.assertIn(self.call('GET',target,user=user)[0],[303,404])
        self.assertEqual(self.call('POST',url+'/blocs/0',csrf=False)[0],403)
        self.assertEqual(self.call('POST',url+'/reponse',csrf=False)[0],403)
        self.assertEqual(self.call('POST',self.base+'/documents',{'genre':'word'},fichier=('f.docx',word()),csrf=False)[0],403)
        for path in [url+'/blocs/0',url+'/reponse']:
            self.assertEqual(self.call('POST',path,user='autre')[0],404)
        self.assertEqual(self.call('GET',url)[2][b'cache-control'],b'no-store')
        self.assertEqual(self.call('GET',self.base+'/documents')[0],200)
        self.assertEqual(self.call('POST',url+'/blocs/0/revoir',csrf=False)[0],403)

    def test_import_progressif_brouillon_rejeu_et_export(self):
        url,doc=self.upload()
        self.assertEqual(self.db.query(EntrepriseDossier).count(),0)
        st,_,_=self.call('POST',url+'/blocs/0',dict(revision=0,action='brouillon',nom='Atelier corrigé'))
        self.assertEqual(st,303); self.db.expire_all()
        self.assertEqual(json.loads(doc.propositions_json)[0]['nom'],'Atelier corrigé')
        self.assertEqual(self.confirm(url)[0],409)
        data=dict(revision=1,action='confirmer',nom='Atelier corrigé',validation='on',c0_nom='Alex Exemple',c0_poste='Sales Manager',
            c0_courriel='alex@example.org',c0_inclure='on',c0_note='Adresse à essayer')
        self.assertEqual(self.call('POST',url+'/blocs/0',data)[0],303)
        self.db.expire_all(); e=self.db.query(EntrepriseDossier).one(); c=json.loads(e.contacts_json)[0]
        self.assertFalse(c['retenu']); self.assertEqual(c['verification'],'a_verifier'); self.assertEqual(c['courriel_statut'],'a_verifier')
        self.assertEqual(self.call('POST',url+'/blocs/0',data)[0],409)
        c['retenu']=True; e.contacts_json=json.dumps([c]); self.db.commit()
        st,html,_=self.call('GET',url+'/reponse'); self.assertEqual(st,200)
        signature=re.search(rb'name="signature" value="([a-f0-9]+)"',html)[1].decode()
        st,raw,headers=self.call('POST',url+'/reponse',{'signature':signature,'validation':'on'})
        self.assertEqual(st,200); self.assertIn(b'no-store',headers.values())
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            txt=md.texte(md.xml(z.read('word/document.xml')))
            self.assertIn('contact à vérifier',txt); self.assertIn('courriel à vérifier',txt)
        self.assertEqual(doc.original,word())
        self.assertEqual(self.call('GET',self.base+'/export')[0],200)
        c['nom']='Nom corrigé';e.contacts_json=json.dumps([c]); self.db.commit()
        self.assertEqual(self.call('POST',url+'/reponse',{'signature':signature,'validation':'on'})[0],409)

    def test_contact_verifie_preserve_et_suppression_cascade(self):
        e=self.org(nom='Fournisseur Fictif',contacts_json=json.dumps([dict(id='existant',nom='Alex Exemple',poste='Directeur',courriel='alex@example.org',verification='verifie',retenu=True)]))
        self.db.commit();url,doc=self.upload('blocs')
        self.assertEqual(self.call('GET',url)[0],200)
        st,_,_=self.confirm(url,organisation_id=e.id,c0_nom='Alex Exemple',c0_courriel='alex@example.org',c0_poste='Nouveau poste incertain',c0_inclure='on')
        self.assertEqual(st,303);self.db.expire_all()
        cs=json.loads(e.contacts_json);self.assertEqual(len(cs),1);self.assertEqual(cs[0]['poste'],'Directeur');self.assertTrue(cs[0]['retenu'])
        self.assertEqual(self.call('POST',url+'/blocs/0/revoir',{'revision':1})[0],303)
        self.db.expire_all();self.assertEqual(json.loads(doc.propositions_json)[0]['etat'],'a_confirmer')
        self.assertEqual(json.loads(e.contacts_json)[0]['poste'],'Directeur')
        self.db.delete(self.d);self.db.commit();self.assertEqual(self.db.query(DocumentMandat).count(),0)

    def test_formats_malformes_limites_et_messages(self):
        for nom,data in [('old.doc',b'old'),('fake.docx',b'pas un zip'),('large.docx',b'x'*(md.MAX_BYTES+1))]:
            st,body,_=self.call('POST',self.base+'/documents',{'genre':'word'},fichier=(nom,data))
            self.assertEqual(st,400)
            if nom.endswith('.doc'):self.assertIn(b'Enregistrer sous',body)
        for xml in [b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>',b'<broken']:
            with self.assertRaises(ValueError):md.xml(xml)
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('word/document.xml',b'x'*30_000_001)
        with self.assertRaises(ValueError):md.lire_word(b.getvalue())
        wb=Workbook();wb.active['A1']='=HYPERLINK("https://example.org")';b=io.BytesIO();wb.save(b)
        with self.assertRaises(ValueError):md.lire_blocs(b.getvalue())
        with self.assertRaises(ValueError):md.lire_blocs(excel(),99)

    def test_validation_et_aucune_creation_implicite(self):
        url,_=self.upload()
        for nom in ['person@example.org','https://example.org','']:
            self.assertEqual(self.call('POST',url+'/blocs/0',{'revision':0,'action':'confirmer','nom':nom,'validation':'on'})[0],400)
        self.assertEqual(self.db.query(EntrepriseDossier).count(),0)
        self.assertEqual(self.call('POST',url+'/blocs/0',{'revision':0,'action':'ignorer'})[0],303)
        self.assertEqual(self.db.query(EntrepriseDossier).count(),0)
