# Résumé du projet — Outil de prospection B2B

> **Document régénéré le : 1er juillet 2026**
> Basé uniquement sur les fichiers réellement présents dans le dépôt.
> Quand une fonctionnalité attendue n'est pas codée, c'est indiqué clairement.

> 🔄 **Refonte majeure du 1er juillet 2026 — architecture des clés API.**
> Les clés Hunter.io / Apollo.io / SerpAPI sont désormais **côté serveur uniquement**
> (fichier `.env`, lues par `os.getenv()`). Elles ne transitent plus jamais par la
> base de données, les routes, le HTML ou le JavaScript. Les utilisateurs se
> connectent avec email + mot de passe et utilisent l'outil **directement**, sans
> aucune configuration. La page `/parametres` et la table `cles_api` ont été
> **supprimées**. Seul l'admin voit le statut des APIs (`/admin`).

> ✅ **État par rapport au cahier des charges**
> - ✅ **3 plans d'abonnement : CODÉS.** Gratuit 0 $ (25 rech./mois), Pro 29 $ (500), Business 79 $ (illimité). CAD, dans `plans.py`.
> - ✅ **Limite + blocage de quota : CODÉS.** Décompte mensuel réel, blocage à la limite (front **et** back).
> - ✅ **Panneau admin : CODÉ.** Stats, activation/désactivation de comptes, changement de plan, statut des APIs. (`/admin`)
> - ✅ **Clés API côté serveur : CODÉ.** Plus aucune clé côté utilisateur ni en base.
> - ❌ **Paiement en ligne : absent (choix assumé).** Le changement de plan se fait via le panneau admin, pas par une passerelle de paiement.

---

## 1. Vue d'ensemble

**Nom du projet :** Outil de prospection B2B (nom interne : `prospection-lise`, dépôt GitHub : `Site_web_scraping`, marque affichée : **ProspectB2B**).

**Ce que fait l'outil, en clair :**
1. L'utilisateur tape le nom d'une entreprise (ou téléverse une liste CSV).
2. Le **serveur** interroge des fournisseurs de données (avec ses propres accès) pour trouver le bon contact marketing ou ventes : prénom, nom, titre, courriel, localisation.
3. Le résultat s'affiche dans un tableau et se télécharge en fichier Excel prêt à l'emploi.
4. L'utilisateur n'a **rien à configurer** : il crée un compte et utilise l'outil. Il ne voit ni ne fournit aucune clé API, et ne sait pas quels services sont utilisés.

**Pour qui c'est fait :** d'après le contexte du projet, l'outil vise **Lise et ses vendeurs de publicité**, pour trouver rapidement les contacts à démarcher. Le code est générique (« prospection B2B ») et ne nomme Lise que dans le nom interne du projet (`prospection-lise.iml`).

---

## 2. Architecture technique

### Stack utilisée (vérifiée dans `requirements.txt` et le code)
- **Backend :** FastAPI (`>=0.110`), servi par Uvicorn.
- **Templates HTML :** Jinja2 (HTML/CSS pur, sans framework front-end).
- **Base de données :** SQLAlchemy (`>=2.0`) — PostgreSQL (Neon) via `psycopg2-binary` si `DATABASE_URL` est défini, sinon repli SQLite.
- **Sécurité :** `bcrypt` (mots de passe), `itsdangerous` (sessions signées), protection CSRF maison.
- **Recherche / export :** `requests` (appels API) et `openpyxl` (génération Excel).
- **Formulaires / upload :** `python-multipart`, `aiofiles`.
- **Config :** `python-dotenv` (chargement du `.env`).
- **Ancienne interface (héritage) :** Streamlit + pandas, dans `app.py` — voir la note en fin de section.

### Comment les clés API sont protégées (nouvelle architecture — détails en section 8)
- Stockées **uniquement dans le `.env` du serveur** (ou les variables d'environnement Vercel en production).
- Lues côté serveur via `os.getenv()` au moment de la recherche (`config.py`), jamais persistées ailleurs.
- **Jamais** envoyées au navigateur, ni dans le HTML, ni dans le JS, ni en base de données.
- En cas d'échec d'un service externe, l'utilisateur voit un message générique (« Service temporairement indisponible ») — jamais le nom du service ni la cause.

### Schéma du flux de données
```
   Navigateur (utilisateur)
        │  formulaire (nom d'entreprise, département, région) + cookie de session
        ▼
   Notre serveur (FastAPI, routes/app_routes.py)
        │  1. vérifie la session + le jeton CSRF
        │  2. vérifie le quota mensuel du plan
        ▼
   Moteur de recherche (recherche.py)
        │  lit les clés API depuis config.py → os.getenv() (côté serveur)
        │  appelle, dans l'ordre, jusqu'à trouver :
        ▼
   Fournisseurs de données externes
        ├── Hunter.io   (Domain Search)
        ├── Apollo.io   (People Search)   ← si Hunter ne trouve rien
        └── SerpAPI     (repli Google)    ← si Apollo ne trouve rien
        │
        ▼
   Résultats → tableau HTML + export Excel (export.py)
   Trace enregistrée dans historique_recherches (sans les contacts, juste le compte)
```

### Liste des fichiers et leur rôle (une ligne chacun)

| Fichier | Rôle |
|---|---|
| `main.py` | Assemble l'app FastAPI, monte `/static`, branche les routes, initialise la base au démarrage, gère les redirections d'accès. |
| `api/index.py` | Point d'entrée serverless pour Vercel : expose l'objet `app` importé de `main`. |
| `vercel.json` | Réécrit toutes les URLs (`/(.*)`) vers `/api/index`. |
| `config.py` | Lit les clés API depuis l'environnement (`os.getenv`) ; expose `statut_apis()` pour l'admin ; définit le timeout réseau (10 s). |
| `auth.py` | Mots de passe (bcrypt), sessions signées (itsdangerous), protection CSRF, dépendances de contrôle d'accès (`exiger_connexion`, `exiger_admin`). |
| `database.py` | Modèles SQLAlchemy (2 tables) + connexion Neon Postgres / repli SQLite + suppression de l'ancienne table `cles_api`. |
| `templating.py` | Configure Jinja2 et le helper `rendre()` qui injecte `utilisateur` et le jeton CSRF. |
| `recherche.py` | Moteur : Hunter → Apollo → SerpAPI, avec repli automatique et gestion des erreurs bloquantes. |
| `export.py` | Génère le fichier Excel `.xlsx` formaté (12 colonnes). |
| `plans.py` | Définition des 3 plans (prix, limites) + calcul de l'usage mensuel et de l'état du quota. |
| `setup.py` | Script d'initialisation : crée/met à jour le compte administrateur en ligne de commande. |
| `app.py` | **Ancienne interface Streamlit** (héritage, non recommandée) — voir note ci-dessous. |
| `routes/__init__.py` | Fait de `routes/` un package Python (vide). |
| `routes/public.py` | Pages publiques : `/` (accueil), `/tarifs`, `/confidentialite`. |
| `routes/auth_routes.py` | `/login`, `/inscription`, `/logout`. |
| `routes/app_routes.py` | L'outil : `/app`, `/app/recherche`, `/app/lot`, `/app/telecharger`. |
| `routes/plan_routes.py` | Route `/abonnement` (« Mon compte » : plan + usage). |
| `routes/admin_routes.py` | Panneau admin : `/admin`, `/admin/utilisateur/{id}/actif`, `/admin/utilisateur/{id}/plan`. |
| `templates/base.html` | Gabarit commun : nav, pied de page, styles. |
| `templates/accueil.html` | Page d'accueil (hero, étapes, fonctionnalités, tarifs). |
| `templates/tarifs.html` | Page dédiée des 3 plans. |
| `templates/login.html` | Formulaire de connexion. |
| `templates/inscription.html` | Formulaire de création de compte. |
| `templates/app.html` | Page de l'outil (recherche simple, recherche en lot, tableau de résultats). |
| `templates/abonnement.html` | Page « Mon compte » : plan actuel, usage du mois, plans. |
| `templates/admin.html` | Panneau admin : stats, statut des APIs, tableau des comptes. |
| `templates/confidentialite.html` | Politique de confidentialité. |
| `static/style.css` | Feuille de style globale. |
| `static/app.js` | Interactions : onglets et barre de progression. |
| `requirements.txt` | Dépendances Python. |
| `.env.example` | Modèle de variables d'environnement (`SECRET_KEY`, `DATABASE_URL`, `COOKIE_SECURE`, clés API serveur). |
| `exemple_entree.csv` | Exemple de fichier CSV pour la recherche en lot. |
| `demarrer.command` | Script macOS de lancement du site FastAPI (uvicorn). |
| `README.md` | Documentation d'installation et d'utilisation. |

> **Note sur `app.py` (Streamlit) :** ancienne version de l'outil, remplacée par le site web FastAPI. `requirements.txt` ne contient **plus** Streamlit ni pandas, donc `app.py` ne fonctionnerait pas sans réinstaller ces paquets manuellement.

---

## 3. Les trois plans d'abonnement

**✅ Les 3 plans sont définis et appliqués par le code** (`plans.py`), avec un vrai décompte des recherches et un blocage au quota. Prix en **CAD, par mois**.

| Plan | Prix / mois | Recherches incluses | Fonctionnalités | Blocage à la limite |
|---|---|---|---|---|
| **Gratuit** | 0 $ | **25 / mois** | Recherche simple, export Excel | Recherche bloquée dès 25/25 ce mois-ci |
| **Pro** | 29 $ | **500 / mois** | Recherche simple **et en lot (CSV)**, export Excel | Recherche bloquée dès 500/500 ce mois-ci |
| **Business** | 79 $ | **Illimité** | Tout Pro + support prioritaire | Jamais bloqué |

**Règles de décompte (codées dans `plans.py`) :**
- **1 entreprise recherchée = 1 recherche décomptée.** En recherche en lot, chaque ligne du CSV compte pour 1.
- Le compteur se base sur la table `historique_recherches` et se **remet à zéro chaque mois calendaire** (1er du mois, en UTC).
- Quand la limite est atteinte : les boutons de recherche sont désactivés, un message invite à passer à un plan supérieur, et le serveur refuse aussi la recherche côté back-end (pas seulement dans l'interface).
- En lot, si la limite est atteinte **en cours de fichier**, le traitement s'arrête proprement et garde les résultats déjà obtenus.

**Ce qui n'est PAS codé :** le **paiement en ligne**. Le changement de plan se fait via le **panneau admin** (section 5), et la page d'abonnement invite à écrire à l'équipe.

> ⚠️ **Prix facilement modifiables :** noms, prix et limites sont regroupés dans le dictionnaire `PLANS` de `plans.py`. Les changer là met à jour automatiquement l'accueil, la page `/tarifs`, la page d'abonnement, le panneau admin et les blocages.

---

## 4. Fonctionnement pour l'utilisateur

### Inscription (`routes/auth_routes.py`)
1. L'utilisateur va sur `/inscription`, saisit un nom (optionnel), un courriel, un mot de passe (8 caractères minimum) et la confirmation.
2. Le serveur valide : jeton CSRF, format du courriel, longueur du mot de passe, correspondance des deux mots de passe, et unicité du courriel.
3. Le mot de passe est haché (bcrypt) puis l'utilisateur est créé.
4. Une session est ouverte et l'utilisateur est redirigé **directement vers `/app`** (aucune configuration requise).

### Connexion (`routes/auth_routes.py`)
1. Sur `/login`, l'utilisateur entre courriel + mot de passe.
2. Le serveur valide le CSRF, vérifie le mot de passe (bcrypt) et que le compte est `actif`.
3. En cas de succès, une session (cookie signé) est créée et l'utilisateur est redirigé vers `/app`.
4. Un utilisateur déjà connecté qui visite `/login` ou `/inscription` est redirigé vers `/app`.

### Recherche simple (`/app/recherche`)
1. Sur `/app`, l'utilisateur saisit le nom de l'entreprise, choisit le département (Marketing / Ventes / Les deux) et la région (Canada / États-Unis / Europe / Toutes).
2. Le serveur vérifie le CSRF, **puis que le quota mensuel n'est pas atteint**. Il n'y a plus de vérification de clé côté utilisateur : les clés sont côté serveur.
3. Le moteur `rechercher_entreprise()` interroge les fournisseurs (Hunter → Apollo → SerpAPI).
4. Les résultats s'affichent dans un tableau. Une trace est enregistrée dans `historique_recherches` (= le décompte du quota).
5. En cas d'échec d'un service externe : message générique « Service temporairement indisponible » — aucun détail sur le service ni la cause.

### Recherche en lot / CSV (`/app/lot`)
1. L'utilisateur téléverse un fichier CSV avec les colonnes **`entreprise, departement, region`** (un exemple est fourni : `exemple_entree.csv`).
2. Le serveur lit le CSV, vérifie que les colonnes requises sont présentes.
3. Pour chaque ligne, il lance une recherche — **dans la limite des recherches restantes du mois**. Si le quota du plan est atteint en cours de fichier, le traitement s'arrête et les lignes non traitées sont signalées. Une erreur d'API externe arrête aussi le traitement (message générique). Dans tous les cas, **les résultats déjà obtenus sont conservés**.
4. Tous les résultats sont regroupés dans un seul tableau ; chaque entreprise traitée est journalisée (et décomptée).

### Télécharger l'Excel (`/app/telecharger`)
- Les résultats affichés sont stockés dans un champ caché (encodés en base64). Le bouton « Télécharger Excel » renvoie ce contenu au serveur, qui génère le `.xlsx` avec `openpyxl`.
- Le téléchargement **ne relance pas** de recherche, donc ne reconsomme pas de quota. Fichier nommé `prospection_AAAA-MM-JJ_HHMM.xlsx`.

### Quand la limite est atteinte
- **Limite du plan :** dès que l'utilisateur atteint le nombre de recherches de son plan pour le mois (25 en Gratuit, 500 en Pro), la page `/app` affiche un bandeau ambre « X/limite », désactive les boutons de recherche et montre un message invitant à passer à un plan supérieur. Le serveur refuse aussi la recherche (sécurité côté back-end). Le compteur repart à zéro le 1er du mois suivant. Le plan Business (illimité) n'est jamais bloqué.
- **Limite d'API externe :** si un fournisseur renvoie une erreur (quota, clé invalide…), l'utilisateur voit un message **générique** (« Service temporairement indisponible ») ; le détail (service, cause) reste côté serveur. En lot, le traitement s'arrête et garde ce qui a déjà été trouvé.
- **Page « Mon compte » (`/abonnement`) :** montre à tout moment le plan actuel, le nombre de recherches utilisées/restantes du mois, et les 3 plans.

---

## 5. Panneau admin (`routes/admin_routes.py`, `templates/admin.html`)

**✅ Le panneau admin est codé et fonctionnel.** Accès réservé aux comptes `admin=True` via la dépendance `exiger_admin` : un utilisateur non connecté est renvoyé vers `/login`, un utilisateur connecté non-admin vers `/app`. Le lien « Admin » n'apparaît dans la navigation que pour les administrateurs.

### Ce que l'admin voit et peut faire (`/admin`)
- **Statistiques :** nombre total de comptes, comptes actifs / désactivés, total des recherches, répartition des utilisateurs par plan.
- **Statut des APIs (réservé admin) :** pour chaque service (Hunter.io, Apollo.io, SerpAPI), affiche **✅ connectée** ou **❌ clé manquante**, selon la présence de la clé dans le `.env` du serveur. Personne d'autre ne voit cette information.
- **Tableau des comptes :** courriel, nom, plan, usage du mois, statut (actif/désactivé), avec pour chaque compte :
  - **Changer le plan** (menu déroulant Gratuit / Pro / Business → `POST /admin/utilisateur/{id}/plan`).
  - **Activer / désactiver** le compte (`POST /admin/utilisateur/{id}/actif`).

### Sécurités du panneau
- Toutes les routes admin passent par `exiger_admin`.
- Chaque action POST valide le **jeton CSRF**.
- Le plan soumis est validé contre la liste connue (`plans.PLANS`).
- **Un admin ne peut pas se désactiver lui-même** (protection anti lock-out).

### Compte administrateur
- Créé par `setup.py` en ligne de commande (courriel + mot de passe), avec `admin=True` et plan `business`. Relancer le script ne crée jamais de doublon (il propose de promouvoir/réinitialiser un compte existant).

---

## 6. Base de données (`database.py`)

Deux tables sont définies avec SQLAlchemy (la table `cles_api` a été **supprimée** avec la refonte).

### Table `utilisateurs`
| Colonne | Type | Détail |
|---|---|---|
| `id` | entier | Clé primaire. |
| `email` | texte | Unique, indexé, obligatoire. |
| `mot_de_passe_hash` | texte | Hash bcrypt (jamais le mot de passe en clair). |
| `nom` | texte | Optionnel. |
| `date_creation` | date/heure | Par défaut : maintenant (UTC). |
| `actif` | booléen | Par défaut `True` ; `False` = compte désactivé (connexion refusée). |
| `admin` | booléen | Par défaut `False` ; `True` = accès au panneau admin. |
| `plan` | texte | `gratuit` (défaut), `pro` ou `business`. Détermine la limite mensuelle. |

> **Migrations automatiques :** au démarrage, `init_db()` ajoute les colonnes `plan` et `admin` aux bases déjà existantes qui ne les ont pas encore, et **supprime l'ancienne table `cles_api`** si elle existe — sans perte de données pour les autres tables, en SQLite comme en PostgreSQL.

### Table `historique_recherches`
| Colonne | Type | Détail |
|---|---|---|
| `id` | entier | Clé primaire. |
| `utilisateur_id` | entier | Clé étrangère vers `utilisateurs`. |
| `entreprise` | texte | Nom recherché. |
| `departement` | texte | Marketing / Ventes / Les deux. |
| `region` | texte | Région choisie. |
| `nb_contacts_trouves` | entier | Nombre de contacts « exploitables ». |
| `date` | date/heure | Date de la recherche. |

**Ce qui est enregistré à chaque recherche :** une ligne avec l'entreprise, le département, la région, le nombre de contacts trouvés (comptés comme ayant un prénom **ou** un courriel) et la date. **Les contacts eux-mêmes (noms, courriels) ne sont pas stockés** — seulement le décompte. Cette table sert aussi de **compteur pour le quota mensuel** : le nombre de lignes du mois en cours est comparé à la limite du plan (`plans.py`).

---

## 7. Fournisseurs de données externes (`recherche.py`)

Le moteur essaie les services **dans l'ordre**, et s'arrête dès qu'un service renvoie au moins un contact. Les clés proviennent toutes du `.env` du serveur (`config.HUNTER_API_KEY` / `APOLLO_API_KEY` / `SERPAPI_KEY`, résolus via `os.getenv`).

### 1. Hunter.io — *étape A/B, appelée en premier*
- **Ce qu'elle fait :** « Domain Search » sur le nom de l'entreprise → trouve le domaine, le modèle de courriel, et une liste de contacts (jusqu'à 50). Le code filtre selon le département visé (marketing/communication ou sales) ou selon des mots-clés dans le titre.
- **Renvoie :** prénom, nom, titre, courriel, indice de confiance, localisation.

### 2. Apollo.io — *étape C, appelée si Hunter n'a rien trouvé*
- **Ce qu'elle fait :** recherche de personnes (`mixed_people/search`) par nom d'entreprise + titres visés, éventuellement filtrée par pays selon la région.
- **Particularité :** sur le plan gratuit d'Apollo, les courriels sont verrouillés (`email_not_unlocked...`) ; le code les met alors à vide.

### 3. SerpAPI — *étape D, repli Google, appelée si Apollo n'a rien trouvé*
- **Ce qu'elle fait :** une recherche Google ciblée `site:linkedin.com "<entreprise>" (...titres...)`. Si un lien LinkedIn est trouvé, il est renvoyé comme **piste à vérifier manuellement** (pas un courriel).

### Logique de repli (ordre des tentatives)
```
Hunter.io  →  (rien ?)  →  Apollo.io  →  (rien ?)  →  SerpAPI  →  (rien ?)  →  fiche « Non trouvé »
```
- Si une clé manque côté serveur, l'étape est simplement ignorée (l'utilisateur ne le voit pas ; l'admin le constate via le statut des APIs).
- Une erreur de clé invalide (401/403) ou de quota (429) **interrompt** la recherche ; l'utilisateur reçoit un message **générique**.
- Si aucune piste n'est trouvée, une ligne « Non trouvé — vérification manuelle requise » est produite (l'export Excel n'est jamais vide).
- Timeout réseau : 10 secondes par appel (`config.TIMEOUT`).

---

## 8. Sécurité (`auth.py`, `config.py`)

### Clés API (nouvelle architecture)
- Stockées **uniquement dans l'environnement serveur** (`.env` en local, variables d'environnement Vercel en production).
- Lues à la demande via `os.getenv()` (`config.py`), au moment de la recherche.
- **Jamais** en base de données, jamais dans le HTML/JS, jamais renvoyées au navigateur.
- Aucune fuite d'identité de service côté client : les pages publiques ne nomment aucun fournisseur, et les erreurs sont génériques.

### Mots de passe
- Hachés avec **bcrypt** (avec sel automatique). Le mot de passe en clair n'est jamais stocké ni journalisé.

### Sessions
- Cookie **signé** avec `itsdangerous` (contenu : l'identifiant utilisateur), valable **7 jours**.
- Attributs du cookie : `httponly` (inaccessible au JavaScript), `samesite=lax`, `secure` en production.
- Protection **CSRF** par « double-submit cookie » : un jeton est posé en cookie et redemandé dans chaque formulaire ; les deux doivent correspondre.

### Contrôle d'accès
- `exiger_connexion` : protège `/app/*` et `/abonnement` → redirige vers `/login` si non connecté.
- `exiger_admin` : protège `/admin/*` → non connecté vers `/login`, non-admin vers `/app`.

### Ce que le navigateur ne voit jamais
- La `SECRET_KEY`, les hash de mots de passe, et les **clés API du service** (aucune, pour aucun utilisateur).
- L'identité des fournisseurs de données et le détail des erreurs externes.

> 🔄 **Changement du 1er juillet 2026 :** le chiffrement Fernet et les fonctions `chiffrer`/`dechiffrer` ont été retirés — ils ne servaient qu'aux clés API par utilisateur, désormais inexistantes. La dépendance `cryptography` a été retirée de `requirements.txt`.

---

## 9. Hébergement et déploiement

### Vercel (hébergement)
- `api/index.py` expose l'app ASGI pour l'environnement serverless de Vercel.
- `vercel.json` redirige toutes les requêtes vers `/api/index` (`maxDuration` 60 s).
- Le code tient compte du système de fichiers en lecture seule de Vercel : sans base Postgres, le repli SQLite pointe vers `/tmp` pour éviter un crash au démarrage.

### Neon.tech (base PostgreSQL)
- `database.py` utilise PostgreSQL si `DATABASE_URL` est fournie (cas d'usage : Neon).
- Il normalise le préfixe de l'URL, force `sslmode=require`, et utilise `NullPool` (adapté au serverless, à combiner avec l'URL « pooler » de Neon).
- **Sans `DATABASE_URL`, l'app bascule sur SQLite** (local ou `/tmp` sur Vercel).

> ⚠️ **En production, `DATABASE_URL` (Neon) est obligatoire.** Sinon le repli SQLite `/tmp` est éphémère sur Vercel → tous les comptes seraient perdus à chaque redéploiement.

### GitHub (code source)
- Dépôt relié à **`https://github.com/leodrolet/Site_web_scraping.git`** (remote `origin`, branche `main`).

### Variables d'environnement nécessaires (sans les valeurs)
| Variable | Rôle | Où c'est utilisé |
|---|---|---|
| `SECRET_KEY` | Signe les sessions. Obligatoire. | `auth.py` |
| `DATABASE_URL` | Connexion à Neon/PostgreSQL. Obligatoire en prod. | `database.py` |
| `HUNTER_API_KEY` / `APOLLO_API_KEY` / `SERPAPI_KEY` | Clés du service, côté serveur (au moins Hunter). | `config.py` → `recherche.py` |
| `VERCEL` | Définie automatiquement par Vercel ; fait pointer le repli SQLite vers `/tmp`. | `database.py` |
| `COOKIE_SECURE` | `true` pour n'envoyer les cookies qu'en HTTPS. Auto-activé sur Vercel. | `auth.py` |

---

## 10. Ce qui reste à faire (état réel du code)

### ✅ Complètement terminé
- Création de compte, connexion, déconnexion (avec CSRF et validations).
- **Clés API côté serveur uniquement** (plus de configuration utilisateur, plus de table `cles_api`).
- Recherche simple (entreprise + département + région).
- Recherche en lot par CSV, avec arrêt propre en cas de quota épuisé.
- Repli automatique Hunter → Apollo → SerpAPI, avec messages d'erreur **génériques** côté utilisateur.
- Export Excel formaté (12 colonnes, en-têtes stylés).
- Journalisation des recherches (`historique_recherches`) et **quota mensuel** avec blocage front + back.
- **3 plans d'abonnement** fonctionnels (Gratuit / Pro / Business).
- **Panneau admin complet** : stats, statut des APIs, activation/désactivation, changement de plan.
- Page `/tarifs` dédiée.
- Configuration de déploiement Vercel + base Neon/SQLite.
- Interface web complète et responsive (accueil, tarifs, login, inscription, outil, mon compte, admin, confidentialité).

### ⚠️ Partiellement fait / à surveiller
- **Paiement en ligne : absent (choix assumé).** Le changement de plan passe par le panneau admin, pas par une passerelle de paiement.
- Le plan par défaut « Canada » sur `/app` diffère du défaut « Toutes » du moteur — sans conséquence fonctionnelle.

### ❌ Manquant (non codé)
- **Réinitialisation de mot de passe** et **vérification du courriel** à l'inscription.
- **Suppression de compte en autonomie** (la politique de confidentialité renvoie à un courriel de contact ; l'admin peut désactiver un compte).
- **Passerelle de paiement** (Stripe ou autre).

### Notes / héritage
- **`app.py` (Streamlit) reste présent** mais inutilisable en l'état (Streamlit/pandas retirés de `requirements.txt`). Fichier hérité ; à supprimer ou réactiver volontairement.

---

## 11. Modèle d'affaires

**⚠️ Le code définit les prix des plans mais aucune donnée de coût ni de profit.**

### Prix présents dans le code (`plans.py`)
- **Gratuit :** 0 $ / mois — 25 recherches.
- **Pro :** 29 $ / mois — 500 recherches.
- **Business :** 79 $ / mois — illimité.
- Le paiement n'est pas implémenté : l'attribution de plan est manuelle (panneau admin).

### Estimation des coûts mensuels
- **Coût des appels API désormais supporté par l'exploitant**, plus par l'utilisateur : depuis la refonte, les clés Hunter/Apollo/SerpAPI sont celles du service. Le coût dépend donc du **volume total de recherches** de tous les utilisateurs et des tarifs de chaque fournisseur — à mesurer, non déductible du code.
- **Hébergement :** Vercel et Neon disposent d'offres gratuites ; les vrais coûts dépendraient du volume réel d'usage.

### Profit estimé selon le nombre de clients
- **Non calculable à partir du code** sans connaître le coût unitaire réel d'une recherche (tarifs Hunter/Apollo/SerpAPI) ni le taux de conversion vers les plans payants. À modéliser en amont, une fois les coûts fournisseurs connus.

> **En résumé :** avec la refonte, l'exploitant fournit les accès aux données et facture des plans — le modèle économique dépend désormais de la **marge entre le prix d'un plan et le coût des recherches** qu'il autorise. Fixer cette marge nécessite de mesurer le coût unitaire réel côté fournisseurs.

---

*Fin du document. Régénéré à partir de la lecture intégrale des fichiers du dépôt, le 1er juillet 2026.*
