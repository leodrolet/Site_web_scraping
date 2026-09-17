# Outil de prospection B2B — Site web

Application web qui trouve automatiquement le bon contact marketing ou ventes
d'une entreprise (nom, titre, courriel, localisation) et l'exporte en Excel.
Les utilisateurs créent un compte (email + mot de passe) et utilisent l'outil
directement. Les clés API sont côté **serveur** (fichier `.env`) : jamais
visibles ni saisies par les utilisateurs.

---

## Architecture

Deux choses cohabitent dans ce dossier :

| Partie | Fichiers | Rôle |
|---|---|---|
| **Site web** | `main.py`, `database.py`, `auth.py`, `templating.py`, `routes/`, `templates/`, `static/` | FastAPI + Jinja2 : accueil, login, app, admin |
| **Moteur** (inchangé) | `recherche.py`, `export.py`, `config.py` | Recherche Hunter/Apollo/SerpAPI + génération Excel |

- **Backend** : FastAPI · **Templates** : Jinja2 (HTML/CSS pur, sans framework)
- **Base de données** : SQLAlchemy — **PostgreSQL (Neon.tech)** si `DATABASE_URL`
  est défini, sinon **repli automatique sur SQLite** (fichier `prospection.db`
  en local, ou `/tmp` sur Vercel). Les tables sont créées automatiquement.
- **Sécurité** : mots de passe hachés (bcrypt), sessions par cookie signé
  (itsdangerous, 7 jours), protection CSRF.

> Les clés API (Hunter/Apollo/SerpAPI) sont lues **uniquement** depuis `.env`
> côté serveur (`config.py` → `os.getenv`). Elles ne transitent jamais par la
> base de données, les routes, le HTML ou le JavaScript. Seul l'admin voit leur
> statut (connectée / manquante) dans `/admin`.

---

## Étape 1 — Installer les dépendances

```bash
cd ~/Site_web_scraping
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

> **Raccourci macOS :** double-cliquez sur `demarrer.command` dans le Finder.
> Il crée l'environnement, installe les dépendances, génère un `.env` avec une
> `SECRET_KEY` aléatoire, puis lance le site et l'ouvre dans le navigateur.

## Étape 2 — Générer la clé secrète

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Colle la valeur affichée dans `.env`, après `SECRET_KEY=` :

```
SECRET_KEY=la_longue_valeur_generee_ici
```

> Cette clé signe les sessions. Si tu la changes, les utilisateurs connectés
> devront se reconnecter.

Ajoute ensuite tes clés API du service dans `.env` (au moins Hunter.io) :

```
HUNTER_API_KEY=ta_cle_hunter
APOLLO_API_KEY=ta_cle_apollo
SERPAPI_KEY=ta_cle_serpapi
```

## Étape 3 — Créer ton compte administrateur

```bash
python3 setup.py
```

## Étape 4 — Lancer le site en local

```bash
uvicorn main:app --reload
```

Ouvre ensuite **<http://localhost:8000>**.

## Étape 5 — Utiliser

1. Page d'accueil → **Essayer maintenant** → **Créer un compte**.
2. Tu arrives directement dans l'**Outil** (aucune configuration à faire) :
   - *Recherche simple* : nom d'entreprise + département + région → **Rechercher**.
   - *Recherche en lot* : téléverse un CSV (`entreprise, departement, region`).
3. Clique **📥 Télécharger Excel**.

## Mandats de recherche privés (administrateur)

Connecte-toi avec ton compte administrateur, puis ouvre **Mandats** ou
`/admin/mandats`. Chaque mandat appartient à son créateur. Les autres comptes,
y compris les autres administrateurs, n'ont pas accès à ses fiches.

1. Crée un mandat pour Lyse. Le budget proposé est de 480 minutes (8 heures),
   modifiable à 420 minutes pour 7 heures. Le temps réellement travaillé se saisit
   manuellement; il n'est pas déduit du temps pendant lequel l'onglet reste ouvert.
2. Importe un CSV (UTF-8 ou Windows-1252, virgule, point-virgule ou tabulation)
   ou un Excel `.xlsx`. Limites : 2 Mo, 2 000 lignes, 100 colonnes.
   Tu peux choisir la ligne d'en-tête et le numéro de feuille Excel.
3. Associe les colonnes : organisation, secteur, pays, région, site, prix,
   notes, sources et durabilité/carbone zéro. Vérifie l'aperçu, puis confirme.
   Aucune organisation n'est créée avant confirmation. Les colonnes originales
   sont conservées sur les fiches. Les doublons peuvent être ignorés ou complétés.
4. Commence par le filtre **Les 5 premières (essai)**. Sur chaque fiche, utilise
   les liens de recherche ou un fournisseur configuré, puis enregistre les
   contacts et leurs sources. Coche **Retenir ce contact dans l'export** pour
   sélectionner les personnes pertinentes. Il est possible de conserver plus
   de deux contacts (jusqu'à 100 par organisation).
5. Marque l'organisation **Terminé** même si aucun contact pertinent n'a été trouvé,
   en expliquant le résultat dans les notes. Chaque formulaire a son bouton
   d'enregistrement; tu peux revenir au mandat et reprendre le travail plus tard.
6. Exporte l'Excel : **Contacts retenus**, **Organisations** (y compris celles sans
   contact) et **Bilan**. Les sources, dates et statuts accompagnent les résultats.

Un contact peut être **à vérifier**, **vérifié** ou **écarté**. Un contact vérifié
exige un poste, des liens de preuve et une date. Les courriels ont leur propre
statut : **non trouvé**, **à vérifier** ou **trouvé**; un courriel trouvé exige
une source. Les suggestions API restent à vérifier et ne sont jamais retenues
automatiquement. Les résultats SerpAPI sont des pistes de profils, pas des
contacts vérifiés. Aucune adresse n'est générée à partir d'un modèle de courriel.

Chaque recherche du mandat interroge une seule organisation, un seul fournisseur
et une seule page, avec le délai réseau existant de 10 secondes par appel.
Les clés restent côté serveur. Sans clé configurée, les recherches par liens
et la saisie manuelle fonctionnent. Il n'y a pas de collecte automatique de profils
LinkedIn ni de parcours automatique de répertoires.

Le [guide complet](docs/mandats-recherche.md) explique les règles de doublons,
les vérifications humaines et les limites. Un [CSV d'exemple](exemple_mandat.csv)
contient uniquement des organisations fictives.

### Vérifications du développement

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q database.py main.py mandats.py mandats_recherche.py routes
node --check static/mandats.js
git diff --check
```

Les tests utilisent une base SQLite temporaire et des réponses API simulées.
Ils ne consomment pas de crédits et ne modifient pas les données du compte réel.
La migration ajoute les tables et colonnes manquantes; elle conserve les comptes,
l'historique et les anciens dossiers. Les anciens contacts restent à vérifier
et doivent être sélectionnés explicitement pour le nouvel export.

---

## Où trouver les clés API (pour le `.env` du serveur)

| Service | Lien |
|---|---|
| Hunter.io | <https://hunter.io/api-keys> |
| Apollo.io | <https://app.apollo.io/#/settings/integrations/api> |
| SerpAPI | <https://serpapi.com/manage-api-key> |

---

## Mise en ligne (plus tard)

Le site est prêt pour **Vercel** (`vercel.json` + `api/index.py`) avec une base
**Neon.tech** (PostgreSQL). Il tourne aussi sur n'importe quel hébergeur Python :

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Variables d'environnement à définir en production (jamais committer `.env`) :

| Variable | Rôle |
|---|---|
| `SECRET_KEY` | Signe les sessions. Obligatoire. |
| `DATABASE_URL` | Connexion Neon/PostgreSQL. **Obligatoire en prod** (sinon SQLite `/tmp` éphémère sur Vercel = comptes perdus à chaque déploiement). |
| `HUNTER_API_KEY` / `APOLLO_API_KEY` / `SERPAPI_KEY` | Clés du service, côté serveur. Au moins Hunter.io. |
| `RESEND_API_KEY` | Clé API [Resend](https://resend.com) pour l'envoi des courriels de confirmation d'adresse. |
| `RESEND_FROM_EMAIL` | Adresse expéditrice (ex. `noreply@tondomaine.com`), sur un **domaine vérifié chez Resend**. |
| `COOKIE_SECURE` | `true` pour n'envoyer les cookies qu'en HTTPS. Auto-activé sur Vercel. |

> **Confirmation d'email (Resend).** Les nouveaux comptes doivent confirmer leur
> adresse avant d'accéder à l'outil. Étapes préalables côté Resend : (1) créer un
> compte, (2) **vérifier un domaine d'envoi** — sans domaine vérifié, le mode bac
> à sable n'autorise l'envoi qu'à ta propre adresse via `onboarding@resend.dev`,
> pas aux vrais utilisateurs — (3) générer une clé API. Renseigne ensuite
> `RESEND_API_KEY` et `RESEND_FROM_EMAIL`. Si ces variables sont absentes, la
> création de compte fonctionne quand même (aucun courriel envoyé, l'utilisateur
> voit un message d'échec + un bouton « Renvoyer »). Les comptes **déjà en base**
> avant cet ajout restent utilisables sans re-confirmation (`email_confirme` vaut
> `TRUE` par défaut au niveau de la colonne).

- Sers le site en **HTTPS**. Les cookies passent en `secure` automatiquement
  quand `COOKIE_SECURE=true` (ou sur Vercel) — plus rien à modifier dans le code.
- Autres options d'hébergement : Railway.app, Render.com, ou un VPS.

---

## En cas de problème

- **`⚠️ SECRET_KEY absente`** au démarrage → tu n'as pas rempli `.env`
  (étape 2). Le site fonctionne quand même, mais les sessions sont perdues à
  chaque redémarrage.
- **`command not found: uvicorn`** → l'environnement n'est pas activé
  (`source venv/bin/activate`).
- **« Service temporairement indisponible »** dans l'outil → vérifie tes clés
  API dans `.env` (statut visible dans `/admin`).
- **Repartir de zéro** → supprime le fichier `prospection.db`
  (toutes les données utilisateurs sont effacées).

---

## Note sur l'ancienne version

L'interface Streamlit (`app.py`, lancée avec `streamlit run app.py`) est
remplacée par ce site web. Elle reste présente mais n'est plus la méthode
recommandée ; `requirements.txt` ne contient plus Streamlit.
