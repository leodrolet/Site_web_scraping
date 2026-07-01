# Résumé du projet — Outil de prospection B2B

> **Document généré le : 1er juillet 2026**
> Basé uniquement sur les fichiers réellement présents dans le dépôt.
> Quand une fonctionnalité attendue n'est pas codée, c'est indiqué clairement.

> ✅ **Mise à jour du 1er juillet 2026 — incohérences corrigées + plans ajoutés.**
> - Points de cohérence réglés : `demarrer.command` lance le site FastAPI (plus Streamlit) ; `.env.example` documente `DATABASE_URL` et `COOKIE_SECURE` ; README à jour (Neon/Postgres, bon dossier) ; cookies `secure` en production ; `/parametres` n'expose plus la clé déchiffrée.
> - **Nouveau : les 3 plans d'abonnement sont maintenant codés et fonctionnels** (Gratuit / Pro / Business), avec décompte mensuel des recherches et blocage au quota. Détails en sections 3, 4 et 11.
> - **Toujours absent :** le panneau admin et le paiement en ligne (voir sections 5 et 11).

> ⚠️ **À lire en premier — état des écarts par rapport au cahier des charges**
> - ✅ **3 plans d'abonnement : CODÉS.** Gratuit 0 $ (25 rech./mois), Pro 29 $ (500), Business 79 $ (illimité). Prix en CAD, définis dans `plans.py`.
> - ✅ **Limite de recherche + blocage de quota : CODÉS.** Décompte mensuel réel, blocage à la limite, bandeau d'usage.
> - ❌ **Panneau admin : toujours absent.** Le plan d'un utilisateur se change en base de données (pas d'écran admin).
> - ❌ **Paiement en ligne : absent (choix assumé).** Le passage à un plan payant se fait manuellement pour l'instant.
>
> Le détail de chaque point est dans les sections 3, 5, 10 et 11.

---

## 1. Vue d'ensemble

**Nom du projet :** Outil de prospection B2B (nom interne du projet : `prospection-lise`, nom du dépôt GitHub : `Site_web_scraping`, marque affichée dans l'interface : **ProspectB2B**).

**Ce que fait l'outil, en clair :**
1. L'utilisateur tape le nom d'une entreprise (ou téléverse une liste).
2. L'outil interroge des services externes (Hunter.io, puis Apollo.io, puis Google via SerpAPI) pour trouver le bon contact marketing ou ventes de cette entreprise : prénom, nom, titre, courriel, localisation.
3. Le résultat s'affiche dans un tableau et se télécharge en fichier Excel prêt à l'emploi.
4. Chaque utilisateur possède son propre compte et saisit **ses propres clés API** ; l'outil ne fournit pas de clés.

**Pour qui c'est fait :** d'après le contexte du projet, l'outil vise **Lise et ses vendeurs de publicité**, pour trouver rapidement les contacts à démarcher. À noter : le code lui-même est générique (« prospection B2B ») et ne nomme Lise nulle part, sauf dans le nom interne du projet (`prospection-lise.iml`). L'audience réelle vient donc du contexte, pas d'un texte dans l'application.

---

## 2. Architecture technique

### Stack utilisée (vérifiée dans `requirements.txt` et le code)
- **Backend :** FastAPI (`>=0.110`), servi par Uvicorn.
- **Templates HTML :** Jinja2 (HTML/CSS pur, sans framework front-end).
- **Base de données :** SQLAlchemy (`>=2.0`) — PostgreSQL (Neon) via `psycopg2-binary` si `DATABASE_URL` est défini, sinon repli SQLite.
- **Sécurité :** `bcrypt` (mots de passe), `cryptography`/Fernet (chiffrement des clés API), `itsdangerous` (sessions signées).
- **Recherche / export :** `requests` (appels API) et `openpyxl` (génération Excel).
- **Formulaires / upload :** `python-multipart`, `aiofiles`.
- **Config :** `python-dotenv` (chargement du `.env`).
- **Ancienne interface (héritage) :** Streamlit + pandas, dans `app.py` — voir la note en fin de section.

### Comment les clés API sont protégées (résumé, détails en section 8)
- Saisies par l'utilisateur dans `/parametres`.
- **Chiffrées avec Fernet** avant stockage en base (jamais en clair).
- Déchiffrées uniquement côté serveur, au moment d'une recherche, et déposées dans un `ContextVar` isolé par requête (`config.py`), jamais dans une variable globale partagée entre utilisateurs.

### Schéma du flux de données
```
   Navigateur (utilisateur)
        │  formulaire (nom d'entreprise, département, région) + cookie de session
        ▼
   Notre serveur (FastAPI, routes/app_routes.py)
        │  1. vérifie la session + le jeton CSRF
        │  2. lit les clés API de l'utilisateur en base, les déchiffre (Fernet)
        │  3. les dépose dans config (ContextVar, isolé par requête)
        ▼
   Moteur de recherche (recherche.py)
        │  appelle, dans l'ordre, jusqu'à trouver :
        ▼
   APIs externes
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
| `main.py` | Assemble l'app FastAPI, monte `/static`, branche les routes, initialise la base au démarrage. |
| `api/index.py` | Point d'entrée serverless pour Vercel : expose l'objet `app` importé de `main`. |
| `vercel.json` | Réécrit toutes les URLs (`/(.*)`) vers `/api/index`. |
| `config.py` | Fournit les clés API par requête via un `ContextVar` (isolé par utilisateur) ; définit le timeout réseau (10 s). |
| `auth.py` | Mots de passe (bcrypt), sessions signées (itsdangerous), chiffrement des clés (Fernet), protection CSRF, dépendances de contrôle d'accès. |
| `database.py` | Modèles SQLAlchemy (3 tables) + connexion Neon Postgres / repli SQLite. |
| `templating.py` | Configure Jinja2 et le helper `rendre()` qui injecte `utilisateur` et le jeton CSRF. |
| `recherche.py` | Moteur : Hunter → Apollo → SerpAPI, avec repli automatique et gestion des erreurs bloquantes. |
| `export.py` | Génère le fichier Excel `.xlsx` formaté (12 colonnes). |
| `app.py` | **Ancienne interface Streamlit** (héritage, non recommandée) — voir note ci-dessous. |
| `routes/__init__.py` | Fait de `routes/` un package Python (vide). |
| `routes/public.py` | Pages publiques : `/` (accueil) et `/confidentialite`. |
| `routes/auth_routes.py` | `/login`, `/inscription`, `/logout`. |
| `routes/app_routes.py` | L'outil : `/app`, `/app/recherche`, `/app/lot`, `/app/telecharger`. |
| `routes/settings_routes.py` | `/parametres` (afficher et sauvegarder les clés API). |
| `templates/base.html` | Gabarit commun : nav, pied de page, styles. |
| `templates/accueil.html` | Page d'accueil (hero, étapes, fonctionnalités, tarifs). |
| `templates/login.html` | Formulaire de connexion. |
| `templates/inscription.html` | Formulaire de création de compte. |
| `templates/app.html` | Page de l'outil (recherche simple, recherche en lot, tableau de résultats). |
| `templates/parametres.html` | Saisie/affichage des clés API. |
| `templates/abonnement.html` | Page « Mon abonnement » : plan actuel, usage du mois, choix de plan. |
| `templates/confidentialite.html` | Politique de confidentialité. |
| `plans.py` | Définition des 3 plans (prix, limites) + calcul de l'usage mensuel et de l'état du quota. |
| `routes/plan_routes.py` | Route `/abonnement`. |
| `static/style.css` | Feuille de style globale. |
| `static/app.js` | Interactions : onglets, barre de progression, afficher/masquer les clés. |
| `requirements.txt` | Dépendances Python. |
| `.env.example` | Modèle de variables d'environnement (`SECRET_KEY`, `DATABASE_URL`, `COOKIE_SECURE`). |
| `exemple_entree.csv` | Exemple de fichier CSV pour la recherche en lot. |
| `demarrer.command` | Script macOS de lancement du site FastAPI (uvicorn). |
| `README.md` | Documentation d'installation et d'utilisation. |

> **Note sur `app.py` (Streamlit) :** c'est l'ancienne version de l'outil, remplacée par le site web FastAPI. `requirements.txt` ne contient **plus** Streamlit ni pandas, donc `app.py` ne fonctionnerait pas sans réinstaller ces paquets manuellement.

---

## 3. Les trois plans d'abonnement

**✅ Les 3 plans sont maintenant définis et appliqués par le code** (`plans.py`), avec un vrai décompte des recherches et un blocage au quota. Prix en **CAD, par mois**.

| Plan | Prix / mois | Recherches incluses | Fonctionnalités | Blocage à la limite |
|---|---|---|---|---|
| **Gratuit** | 0 $ | **25 / mois** | Recherche simple, export Excel, vos propres clés API | Recherche bloquée dès 25/25 ce mois-ci |
| **Pro** | 29 $ | **500 / mois** | Recherche simple **et en lot (CSV)**, export Excel, vos propres clés API | Recherche bloquée dès 500/500 ce mois-ci |
| **Business** | 79 $ | **Illimité** | Tout Pro + support prioritaire | Jamais bloqué |

**Règles de décompte (codées dans `plans.py`) :**
- **1 entreprise recherchée = 1 recherche décomptée.** En recherche en lot, chaque ligne du CSV compte pour 1.
- Le compteur se base sur la table `historique_recherches` et se **remet à zéro chaque mois calendaire** (1er du mois, en UTC).
- Quand la limite est atteinte : les boutons de recherche sont désactivés, un message invite à passer à un plan supérieur, et le serveur refuse aussi la recherche côté back-end (pas seulement dans l'interface).
- En lot, si la limite est atteinte **en cours de fichier**, le traitement s'arrête proprement et garde les résultats déjà obtenus.

**Ce qui n'est PAS codé :** le **paiement en ligne**. Le changement de plan se fait aujourd'hui en base de données (voir README, « Changer le plan d'un utilisateur »), et la page d'abonnement invite à écrire à l'équipe. Voir section 11.

> ⚠️ **Prix facilement modifiables :** noms, prix et limites sont regroupés dans le dictionnaire `PLANS` de `plans.py`. Les changer là met à jour automatiquement l'accueil, la page d'abonnement et les blocages.

---

## 4. Fonctionnement pour l'utilisateur

### Inscription (`routes/auth_routes.py`)
1. L'utilisateur va sur `/inscription`, saisit un nom (optionnel), un courriel, un mot de passe (8 caractères minimum) et la confirmation.
2. Le serveur valide : jeton CSRF, format du courriel, longueur du mot de passe, correspondance des deux mots de passe, et unicité du courriel.
3. Le mot de passe est haché (bcrypt) puis l'utilisateur est créé, avec une ligne `cles_api` vide associée.
4. Une session est ouverte et l'utilisateur est redirigé vers `/parametres?bienvenue=1` pour saisir ses clés API tout de suite.

### Connexion (`routes/auth_routes.py`)
1. Sur `/login`, l'utilisateur entre courriel + mot de passe.
2. Le serveur valide le CSRF, vérifie le mot de passe (bcrypt) et que le compte est `actif`.
3. En cas de succès, une session (cookie signé) est créée et l'utilisateur est redirigé vers `/app`.
4. Un utilisateur déjà connecté qui visite `/login` ou `/inscription` est redirigé vers `/app`.

### Recherche simple (`/app/recherche`)
1. Sur `/app`, l'utilisateur saisit le nom de l'entreprise, choisit le département (Marketing / Ventes / Les deux) et la région (Canada / États-Unis / Europe / Toutes).
2. Le serveur vérifie le CSRF, puis qu'au moins une clé API est configurée (sinon avertissement), **puis que le quota mensuel n'est pas atteint**.
3. Le moteur `rechercher_entreprise()` interroge les API (Hunter → Apollo → SerpAPI).
4. Les résultats s'affichent dans un tableau. Une trace est enregistrée dans `historique_recherches` (= le décompte du quota).

### Recherche en lot / CSV (`/app/lot`)
1. L'utilisateur téléverse un fichier CSV avec les colonnes **`entreprise, departement, region`** (un exemple est fourni : `exemple_entree.csv`).
2. Le serveur lit le CSV, vérifie que les colonnes requises sont présentes.
3. Pour chaque ligne, il lance une recherche — **dans la limite des recherches restantes du mois**. Si le quota du plan est atteint en cours de fichier, le traitement s'arrête et les lignes non traitées sont signalées. Une erreur d'API bloquante (clé invalide/quota API) arrête aussi le traitement. Dans tous les cas, **les résultats déjà obtenus sont conservés**.
4. Tous les résultats sont regroupés dans un seul tableau ; chaque entreprise traitée est journalisée (et décomptée).

### Télécharger l'Excel (`/app/telecharger`)
- Les résultats affichés sont stockés dans un champ caché (encodés en base64). Le bouton « Télécharger Excel » renvoie ce contenu au serveur, qui génère le `.xlsx` avec `openpyxl`.
- Astuce d'implémentation : le téléchargement **ne relance pas** de recherche, donc il ne reconsomme pas de quota API. Le fichier est nommé `prospection_AAAA-MM-JJ_HHMM.xlsx`.

### Quand la limite est atteinte
- **Limite du plan (nouveau) :** dès que l'utilisateur atteint le nombre de recherches de son plan pour le mois (25 en Gratuit, 500 en Pro), la page `/app` affiche un bandeau ambre « X/limite », désactive les boutons de recherche et montre un message invitant à passer à un plan supérieur. Le serveur refuse aussi la recherche (sécurité côté back-end). Le compteur repart à zéro le 1er du mois suivant. Le plan Business (illimité) n'est jamais bloqué.
- **Limite d'API externe :** si Hunter/Apollo/SerpAPI renvoient une erreur de quota (HTTP 429) ou de clé invalide (401/403), le moteur lève une erreur bloquante et l'interface affiche un message (ex. « Hunter.io : quota mensuel dépassé. »). En lot, le traitement s'arrête et garde ce qui a déjà été trouvé.
- **Page « Mon abonnement » (`/abonnement`) :** montre à tout moment le plan actuel, le nombre de recherches utilisées/restantes du mois, et les 3 plans.

---

## 5. Panneau admin

**❌ Il n'existe aucun panneau admin dans le code.**

- Aucune route admin (rien dans `routes/`).
- Aucun gabarit admin (rien dans `templates/`).
- Aucun rôle « administrateur » ni champ `admin` sur la table `utilisateurs`.
- Les **4 pages admin** demandées (tableaux de bord, stats, gestion des utilisateurs, changement de plan) **n'existent pas**.

La seule capacité proche de l'administration : la table `utilisateurs` possède un champ booléen **`actif`**. Un compte avec `actif = False` ne peut plus se connecter (vérifié dans `auth.py` et `auth_routes.py`). **Mais aucune interface** ne permet de basculer ce champ : il faudrait le modifier directement en base de données. Il n'y a ni activation, ni blocage, ni changement de plan, ni statistiques via une interface.

---

## 6. Base de données (`database.py`)

Trois tables sont définies avec SQLAlchemy.

### Table `utilisateurs`
| Colonne | Type | Détail |
|---|---|---|
| `id` | entier | Clé primaire. |
| `email` | texte | Unique, indexé, obligatoire. |
| `mot_de_passe_hash` | texte | Hash bcrypt (jamais le mot de passe en clair). |
| `nom` | texte | Optionnel. |
| `date_creation` | date/heure | Par défaut : maintenant (UTC). |
| `actif` | booléen | Par défaut `True` ; `False` = compte désactivé. |
| `plan` | texte | `gratuit` (défaut), `pro` ou `business`. Détermine la limite mensuelle. |

> **Migration automatique :** au démarrage, `init_db()` ajoute la colonne `plan` (valeur `gratuit`) aux bases déjà existantes qui ne l'ont pas encore — sans perte de données, aussi bien en SQLite qu'en PostgreSQL.

### Table `cles_api`
| Colonne | Type | Détail |
|---|---|---|
| `id` | entier | Clé primaire. |
| `utilisateur_id` | entier | Clé étrangère unique vers `utilisateurs`. |
| `hunter_key` | texte | Clé Hunter.io **chiffrée (Fernet)**. |
| `apollo_key` | texte | Clé Apollo.io **chiffrée (Fernet)**. |
| `serpapi_key` | texte | Clé SerpAPI **chiffrée (Fernet)**. |
| `date_modification` | date/heure | Mise à jour à chaque sauvegarde. |

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

**Ce qui est enregistré à chaque recherche :** une ligne dans `historique_recherches` avec l'entreprise, le département, la région, le nombre de contacts trouvés (comptés comme ayant un prénom **ou** un courriel) et la date. **Les contacts eux-mêmes (noms, courriels) ne sont pas stockés** — seulement le décompte. Cette table sert aussi de **compteur pour le quota mensuel** : le nombre de lignes du mois en cours est comparé à la limite du plan (`plans.py`).

---

## 7. APIs externes utilisées (`recherche.py`)

Le moteur essaie les services **dans l'ordre**, et s'arrête dès qu'un service renvoie au moins un contact.

### 1. Hunter.io — *étape A/B, appelée en premier*
- **Ce qu'elle fait :** « Domain Search » sur le nom de l'entreprise → trouve le domaine, le modèle de courriel, et une liste de contacts (jusqu'à 50). Le code filtre ensuite les contacts selon le département visé (marketing/communication ou sales) ou selon des mots-clés dans le titre.
- **Renvoie :** prénom, nom, titre, courriel, indice de confiance, localisation.

### 2. Apollo.io — *étape C, appelée si Hunter n'a rien trouvé*
- **Ce qu'elle fait :** recherche de personnes (`mixed_people/search`) par nom d'entreprise + titres visés, éventuellement filtrée par pays selon la région.
- **Particularité :** sur le plan gratuit d'Apollo, les courriels sont verrouillés (`email_not_unlocked...`) ; le code les met alors à vide et prévient l'utilisateur.

### 3. SerpAPI — *étape D, repli Google, appelée si Apollo n'a rien trouvé*
- **Ce qu'elle fait :** une recherche Google ciblée `site:linkedin.com "<entreprise>" (...titres...)`. Si un lien LinkedIn est trouvé, il est renvoyé comme **piste à vérifier manuellement** (pas un courriel).

### Logique de repli (ordre des tentatives)
```
Hunter.io  →  (rien ?)  →  Apollo.io  →  (rien ?)  →  SerpAPI  →  (rien ?)  →  fiche « Non trouvé »
```
- Si une clé manque, l'étape est simplement ignorée (avec un avertissement).
- Une erreur de clé invalide (401/403) ou de quota (429) **interrompt** la recherche et remonte un message à l'utilisateur.
- Si aucune piste n'est trouvée, une ligne « Non trouvé — vérification manuelle requise » est produite (l'export Excel n'est jamais vide).
- Timeout réseau : 10 secondes par appel (`config.TIMEOUT`).

---

## 8. Sécurité (`auth.py`, `config.py`)

### Clés API
- Saisies par l'utilisateur, **chiffrées avec Fernet** avant stockage (la clé de chiffrement est dérivée de `SECRET_KEY` via SHA-256).
- Déchiffrées seulement côté serveur, au moment d'une recherche, et placées dans un `ContextVar` **isolé par requête** — jamais dans une variable partagée entre utilisateurs.

### Mots de passe
- Hachés avec **bcrypt** (avec sel automatique). Le mot de passe en clair n'est jamais stocké ni journalisé.

### Sessions
- Cookie **signé** avec `itsdangerous` (contenu : l'identifiant utilisateur), valable **7 jours**.
- Attributs du cookie : `httponly` (inaccessible au JavaScript), `samesite=lax`.
- Protection **CSRF** par « double-submit cookie » : un jeton est posé en cookie et redemandé dans chaque formulaire ; les deux doivent correspondre.

### Ce que le navigateur ne voit jamais
- La `SECRET_KEY`, les hash de mots de passe, et les clés API des **autres** utilisateurs.
- Le déchiffrement des clés se fait entièrement côté serveur pendant une recherche.
- **La clé API de l'utilisateur lui-même** n'est plus renvoyée à son navigateur : la page `/parametres` affiche seulement un badge « configurée / manquante » et laisse le champ vide (voir correction ci-dessous).

> ✅ **Corrigé (1er juillet 2026) — page `/parametres` :** auparavant, la clé déchiffrée de l'utilisateur était pré-remplie dans le champ (révélable via « Afficher »). Désormais, la page n'envoie qu'un booléen « clé présente ou non » ; le champ reste vide, avec le message « laissez vide pour la conserver ». Un enregistrement avec un champ vide **conserve** la clé existante (plus de risque de l'effacer par mégarde).

> ✅ **Corrigé (1er juillet 2026) — cookies `secure` :** `auth.py` et `templating.py` posent maintenant les cookies avec `secure=COOKIE_SECURE`. Ce booléen vaut vrai si `COOKIE_SECURE=true` (ou `1/yes/on`) **ou** si l'app tourne sur Vercel (HTTPS). En local (HTTP), il reste faux pour ne pas casser les sessions.

---

## 9. Hébergement et déploiement

### Vercel (hébergement)
- `api/index.py` expose l'app ASGI pour l'environnement serverless de Vercel.
- `vercel.json` redirige toutes les requêtes vers `/api/index`.
- Le code tient compte du système de fichiers en lecture seule de Vercel : sans base Postgres, le repli SQLite pointe vers `/tmp` pour éviter un crash au démarrage.

### Neon.tech (base PostgreSQL)
- `database.py` utilise PostgreSQL si la variable `DATABASE_URL` est fournie (cas d'usage : Neon).
- Il normalise le préfixe de l'URL, force `sslmode=require`, et utilise `NullPool` (adapté au serverless, à combiner avec l'URL « pooler » de Neon).
- **Sans `DATABASE_URL`, l'app bascule sur SQLite** (local ou `/tmp` sur Vercel).

### GitHub (code source)
- Le dépôt est relié à **`https://github.com/leodrolet/Site_web_scraping.git`** (remote `origin`, branche `main`).
- Le caractère privé/public du dépôt ne peut pas être déterminé à partir du code local ; à vérifier directement sur GitHub.

### Variables d'environnement nécessaires (sans les valeurs)
| Variable | Rôle | Où c'est utilisé |
|---|---|---|
| `SECRET_KEY` | Signe les sessions **et** dérive la clé de chiffrement des clés API. | `auth.py` |
| `DATABASE_URL` | Connexion à Neon/PostgreSQL. Si absente → SQLite. | `database.py` |
| `VERCEL` | Définie automatiquement par Vercel ; fait pointer le repli SQLite vers `/tmp`. | `database.py` |
| `COOKIE_SECURE` | `true` pour n'envoyer les cookies qu'en HTTPS. Auto-activé sur Vercel. | `auth.py` |

> ✅ **Corrigé (1er juillet 2026) :** `.env.example` documente désormais `DATABASE_URL` (Neon) et `COOKIE_SECURE`, en plus de `SECRET_KEY`.

---

## 10. Ce qui reste à faire (état réel du code)

### ✅ Complètement terminé
- Création de compte, connexion, déconnexion (avec CSRF et validations).
- Saisie et **chiffrement** des clés API par utilisateur.
- Recherche simple (entreprise + département + région).
- Recherche en lot par CSV, avec arrêt propre en cas de quota épuisé.
- Repli automatique Hunter → Apollo → SerpAPI.
- Export Excel formaté (12 colonnes, en-têtes stylés).
- Journalisation des recherches (`historique_recherches`).
- Configuration de déploiement Vercel + base Neon/SQLite.
- Interface web complète et responsive (accueil, login, inscription, outil, paramètres, confidentialité).

### ⚠️ Partiellement fait / à surveiller
- **Offres/tarifs :** seulement du texte marketing (2 offres), sans logique réelle. « Pro » n'a ni prix, ni fonctionnalité, ni paiement.
- **Champ `actif`** présent mais **sans interface** pour l'activer/désactiver (modification en base uniquement).
- **Suppression d'une clé API :** avec la nouvelle logique, un champ vide **conserve** la clé. Effacer complètement une clé déjà enregistrée n'a pas d'option dédiée dans l'interface (à faire côté base, ou à ajouter plus tard).

### ✅ Corrigé le 1er juillet 2026 (anciennes incohérences)
- **Cookies `secure`** : désormais automatiques en production via `COOKIE_SECURE`/Vercel.
- **README** : à jour (Neon/PostgreSQL + repli SQLite, bon dossier `Site_web_scraping`).
- **`demarrer.command`** : lance le site FastAPI (`uvicorn`) et génère une vraie `SECRET_KEY`.
- **`.env.example`** : documente `DATABASE_URL` et `COOKIE_SECURE`.
- **`/parametres`** : n'expose plus la clé déchiffrée au navigateur.

### ❌ Manquant (demandé mais pas codé)
- **Panneau admin** (aucune page, aucune route, aucun rôle).
- **Troisième plan** et, plus largement, **tout le système d'abonnement** : plans en base, prix, **limites de recherche**, blocage à la limite, paiement.
- **Réinitialisation de mot de passe** et **vérification du courriel** à l'inscription.
- **Suppression de compte en autonomie** (la politique de confidentialité renvoie à un courriel de contact).
- **Aucune donnée de coûts / de modèle d'affaires** dans le code (voir section 11).

### Bugs connus / incohérences restantes
1. ✅ *(corrigé)* `demarrer.command` lançait l'ancienne app Streamlit alors que Streamlit n'est plus dans `requirements.txt` — il lance maintenant `uvicorn main:app`.
2. ✅ *(corrigé)* `.env.example` documente désormais `DATABASE_URL`.
3. ✅ *(corrigé)* README mis à jour (Neon/PostgreSQL, dossier `Site_web_scraping`).
4. **`app.py` (Streamlit) reste présent** mais inutilisable en l'état (Streamlit/pandas retirés de `requirements.txt`). C'est un fichier hérité ; à supprimer ou à réactiver volontairement.
5. Détail mineur : la page `/app` propose la région par défaut « Canada », tandis que le moteur utilise « Toutes » par défaut — sans conséquence fonctionnelle.

---

## 11. Modèle d'affaires

**⚠️ Le code ne contient aucune donnée de prix, de coût ou de profit.** Cette section ne peut donc pas être « documentée d'après le code » — il n'y a rien à documenter au-delà du texte marketing.

### Prix présents dans le code
- **Starter :** « 0 $ / pour commencer » (page d'accueil).
- **Pro :** « À venir » — aucun prix.
- Aucun troisième plan.

### Estimation des coûts mensuels
- **Impossible à calculer à partir du code**, pour deux raisons :
  1. Aucun tarif n'y est défini.
  2. **Ce sont les utilisateurs qui apportent leurs propres clés API** (Hunter/Apollo/SerpAPI). Le coût des appels API est donc **supporté par l'utilisateur**, pas par l'exploitant de l'outil, dans le modèle actuel.
- **Hébergement :** Vercel et Neon disposent tous deux d'offres gratuites ; le code n'indique aucun palier payant. Les vrais coûts dépendraient du volume réel d'usage (à mesurer, pas déductible du code).

### Profit estimé selon le nombre de clients
- **Non calculable à partir du code** : sans prix de vente ni structure de coûts définie, aucune estimation de profit ne peut être fournie sans inventer des chiffres. Ce serait à définir en amont (fixer les prix des plans, le nombre de recherches inclus, et si l'outil fournit ou non les clés API dans le plan « Pro »).

> **En résumé :** le modèle d'affaires est, à ce stade, une **intention marketing** (2 offres affichées) et non une mécanique implémentée. Le chiffrer nécessite d'abord de décider et de coder les plans, les limites et le paiement.

---

*Fin du document. Généré à partir de la lecture intégrale des fichiers du dépôt, le 1er juillet 2026.*
