#!/bin/bash
# ============================================================
#  Outil de prospection B2B — script de démarrage
#  Double-cliquez sur ce fichier dans le Finder pour lancer.
# ============================================================

# Se placer dans le dossier du script (fonctionne même en double-clic)
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "   Outil de prospection B2B — demarrage"
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

# 5. Creer le fichier .env a partir du modele s'il manque
if [ ! -f ".env" ]; then
  echo ""
  echo "!  Le fichier .env n'existe pas encore : je le cree a partir du modele."
  echo "   Pense a l'ouvrir et a y coller tes cles API (voir README, etape 3)."
  cp .env.example .env
fi

# 6. Lancer l'outil
echo ""
echo ">> Lancement... l'outil va s'ouvrir dans ton navigateur."
echo "   Pour l'arreter : reviens dans cette fenetre et fais Ctrl+C."
echo ""
streamlit run app.py
