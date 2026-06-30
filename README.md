# Outil de prospection B2B — Site web

Application web qui trouve automatiquement le bon contact marketing ou ventes
d'une entreprise (nom, titre, courriel, localisation) et l'exporte en Excel.
Chaque utilisateur crée un compte et saisit **ses propres** clés API.

---

## Architecture

Deux choses cohabitent dans ce dossier :

| Partie | Fichiers | Rôle |
|---|---|---|
| **Site web** (nouveau) | `main.py`, `database.py`, `auth.py`, `templating.py`, `routes/`, `templates/`, `static/` | FastAPI + Jinja2 : accueil, login, app, paramètres |
| **Moteur** (inchangé) | `recherche.py`, `export.py`, `config.py` | Recherche Hunter/Apollo/SerpAPI + génération Excel |

- **Backend** : FastAPI · **Templates** : Jinja2 (HTML/CSS pur, sans framework)
- **Base de données** : SQLite via SQLAlchemy (fichier `prospection.db`, créé automatiquement)
- **Sécurité** : mots de passe hachés (bcrypt), sessions par cookie signé
  (itsdangerous, 7 jours), clés API chiffrées en base (Fernet), protection CSRF.

> Les clés API ne sont **plus** dans `.env` : chaque utilisateur saisit les
> siennes dans `/parametres`. `config.py` les fournit au moteur par requête,
> sans modifier `recherche.py`.

---

## Étape 1 — Installer les dépendances

```bash
cd ~/prospection-lise
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Étape 2 — Générer la clé secrète

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Colle la valeur affichée dans `.env`, après `SECRET_KEY=` :

```
SECRET_KEY=la_longue_valeur_generee_ici
```

> Cette clé chiffre les clés API stockées. Si tu la changes plus tard, les
> clés API déjà enregistrées devront être ressaisies.

## Étape 3 — Lancer le site en local

```bash
uvicorn main:app --reload
```

Ouvre ensuite **<http://localhost:8000>**.

## Étape 4 — Utiliser

1. Page d'accueil → **Essayer maintenant** → **Créer un compte**.
2. Tu es redirigé vers **Paramètres** : saisis au moins ta clé **Hunter.io**
   (Apollo et SerpAPI sont optionnels), puis **Sauvegarder**.
3. Va dans **Outil** :
   - *Recherche simple* : nom d'entreprise + département + région → **Rechercher**.
   - *Recherche en lot* : téléverse un CSV (`entreprise, departement, region`).
4. Clique **📥 Télécharger Excel**.

---

## Où trouver les clés API

| Service | Lien |
|---|---|
| Hunter.io | <https://hunter.io/api-keys> |
| Apollo.io | <https://app.apollo.io/#/settings/integrations/api> |
| SerpAPI | <https://serpapi.com/manage-api-key> |

---

## Mise en ligne (plus tard)

Le site tourne avec n'importe quel hébergeur Python. En production :

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

- Définis `SECRET_KEY` comme variable d'environnement (ne committe jamais `.env`).
- Sers le site en **HTTPS** et passe les cookies en `secure=True`
  (dans `auth.py` et `templating.py`).
- Options d'hébergement : Railway.app, Render.com, ou un VPS.

---

## En cas de problème

- **`⚠️ SECRET_KEY absente`** au démarrage → tu n'as pas rempli `.env`
  (étape 2). Le site fonctionne quand même, mais les sessions sont perdues à
  chaque redémarrage.
- **`command not found: uvicorn`** → l'environnement n'est pas activé
  (`source venv/bin/activate`).
- **« Aucune clé API configurée »** dans l'outil → va dans `/parametres`.
- **Repartir de zéro** → supprime le fichier `prospection.db`
  (toutes les données utilisateurs sont effacées).

---

## Note sur l'ancienne version

L'interface Streamlit (`app.py`, lancée avec `streamlit run app.py`) est
remplacée par ce site web. Elle reste présente mais n'est plus la méthode
recommandée ; `requirements.txt` ne contient plus Streamlit.
