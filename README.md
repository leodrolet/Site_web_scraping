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
| `COOKIE_SECURE` | `true` pour n'envoyer les cookies qu'en HTTPS. Auto-activé sur Vercel. |

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
