#!/bin/bash
# ============================================================
#  Outil de prospection B2B (site web FastAPI) — démarrage
#  Double-cliquez sur ce fichier dans le Finder pour lancer.
# ============================================================

# Se placer dans le dossier du script (fonctionne même en double-clic)
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "   Outil de prospection B2B — demarrage du site"
echo "==================================================="
echo ""

# 1. Verifier que Python 3 est installe
if ! command -v python3 >/dev/null 2>&1; then
  echo "X  Python 3 n'est pas installe."
  echo "   Installe-le depuis https://www.python.org/downloads/ puis relance."
  echo ""
  read -p "Appuie sur Entree pour fermer..."
  exit 1
fi

# 2. Creer l'environnement virtuel s'il n'existe pas encore
if [ ! -d "venv" ]; then
  echo ">> Premiere utilisation : creation de l'environnement..."
  python3 -m venv venv || { echo "X  Echec de la creation de l'environnement."; read -p "Entree pour fermer..."; exit 1; }
fi

# 3. Activer l'environnement
source venv/bin/activate

# 4. Installer / mettre a jour les dependances seulement si necessaire
if [ ! -f "venv/.installed" ] || [ requirements.txt -nt venv/.installed ]; then
  echo ">> Installation des dependances (peut prendre 1 a 2 minutes la 1re fois)..."
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt || { echo "X  Echec de l'installation."; read -p "Entree pour fermer..."; exit 1; }
  touch venv/.installed
fi

# 5. Creer le fichier .env avec une vraie SECRET_KEY s'il manque
if [ ! -f ".env" ]; then
  echo ""
  echo "!  Le fichier .env n'existe pas encore : je le cree avec une cle secrete aleatoire."
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  echo "SECRET_KEY=$SECRET" > .env
  echo "   (Sans DATABASE_URL, le site utilise une base SQLite locale. Voir .env.example.)"
fi

# 6. Lancer le site (ouvre le navigateur automatiquement apres 2 s)
echo ""
echo ">> Lancement du site sur http://localhost:8000"
echo "   Pour l'arreter : reviens dans cette fenetre et fais Ctrl+C."
echo ""
( sleep 2 && open "http://localhost:8000" ) >/dev/null 2>&1 &
uvicorn main:app --host 127.0.0.1 --port 8000
