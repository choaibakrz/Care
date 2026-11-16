#!/usr/bin/env bash
# =====================================================================================
# Préparer un ordinateur-cerveau (iMac M4 ou MacBook M2) — UN SEUL SCRIPT.
#
#   ./preparer_mac.sh                         vérifier, installer (après oui), tester, télécharger (après oui), mesurer
#   ./preparer_mac.sh --autre-mac 192.168.1.20   + mesurer le partage avec l'autre Mac
#   ./preparer_mac.sh --garder-cerveau        laisser le cerveau allumé à la fin (pour que l'autre Mac le mesure)
#   ./preparer_mac.sh --sans-telechargement   ne rien télécharger (seulement vérifier et tester)
#
# Ce script ne fait JAMAIS bouger de robot. Il ne télécharge ni n'installe rien sans un « oui » tapé.
# Il n'accepte aucune condition d'utilisation à votre place.
# État : écrit et relu, mais NON TESTÉ sur Mac à ce jour (seulement sur Linux, en partie).
# =====================================================================================
set -u
cd "$(dirname "$0")"
RACINE="$(pwd)"
AUTRE_MAC=""; GARDER=""; SANS_DL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --autre-mac) AUTRE_MAC="$2"; shift 2 ;;
    --garder-cerveau) GARDER="--garder-cerveau"; shift ;;
    --sans-telechargement) SANS_DL="1"; shift ;;
    *) echo "Option inconnue : $1"; exit 2 ;;
  esac
done

titre() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }
oui() { read -r -p "$1 Tapez « oui » pour accepter : " r; [ "$r" = "oui" ]; }

# ---------------------------------------------------------------- 1. La machine
titre "1. Vérifier la machine"
OS="$(uname -s)"; ARCH="$(uname -m)"
if [ "$OS" = "Darwin" ]; then
  PUCE="$(sysctl -n machdep.cpu.brand_string)"
  MEM_GO=$(( $(sysctl -n hw.memsize) / 1000000000 ))
  echo "Mac : $PUCE, ${MEM_GO} Go de mémoire, macOS $(sw_vers -productVersion)"
  [ "$ARCH" = "arm64" ] || echo "ATTENTION : ce Mac n'a pas de puce Apple. Les outils MLX ne marcheront pas."
else
  echo "Ce n'est pas un Mac ($OS $ARCH) : mode essai, les mesures propres au Mac seront sautées."
fi
LIBRE_GO=$(df -Pk "$RACINE" | awk 'NR==2 {print int($4/1000000)}')
echo "Place libre sur le disque : ${LIBRE_GO} Go (kit léger : ~6 Go ; tout le catalogue : ~18 Go)"

# ---------------------------------------------------------------- 2. Python
titre "2. Trouver Python 3.11 ou plus récent"
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Aucun Python 3.11+ trouvé. Le Python fourni par macOS est trop ancien."
  echo "À installer par une personne (feu orange), au choix :"
  echo "  - avec Homebrew :  brew install python@3.12"
  echo "  - ou l'installateur officiel : https://www.python.org/downloads/macos/"
  echo "Puis relancer ce script."
  exit 1
fi
echo "Python : $PY ($("$PY" --version))"

# ---------------------------------------------------------------- 3. Paquets
titre "3. Paquets Python (dans le dossier .venv du projet, rien ailleurs)"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
VPY="$RACINE/.venv/bin/python"
if "$VPY" -c 'import fastapi, uvicorn, pydantic, yaml, pytest, psutil' 2>/dev/null; then
  echo "Paquets de base : déjà installés."
elif oui "Installer les paquets de base (requirements.txt, ~20 Mo, licences MIT/BSD) ?"; then
  "$VPY" -m pip install -q --upgrade pip && "$VPY" -m pip install -q -r requirements.txt
else
  echo "Sans les paquets de base, rien ne peut tourner. Arrêt."; exit 1
fi
if [ "$OS" = "Darwin" ]; then
  if "$VPY" -c 'import mlx_lm, mlx_whisper, pywhispercpp, sherpa_onnx' 2>/dev/null; then
    echo "Paquets écoute/voix/cerveau : déjà installés."
  elif oui "Installer les paquets écoute/voix/cerveau pour Mac (requirements-mac.txt, ~300 Mo, licences MIT/Apache) ?"; then
    "$VPY" -m pip install -q -r requirements-mac.txt || echo "Certains paquets ont échoué : voir les messages ci-dessus."
  fi
fi

if [ ! -f reglages.yaml ]; then
  cp reglages.exemple.yaml reglages.yaml
  echo "reglages.yaml créé (hors du dépôt). À faire à la main : écrire le code d'équipe dans ecran.code_equipe."
fi

# ---------------------------------------------------------------- 4. llama.cpp
titre "4. llama.cpp (fait tourner le cerveau sur la puce graphique)"
if command -v llama-server >/dev/null 2>&1 || [ -x outils/bin/llama-server ]; then
  echo "llama-server : trouvé."
elif [ "$OS" = "Darwin" ]; then
  if command -v brew >/dev/null 2>&1; then
    oui "Installer llama.cpp avec Homebrew (brew install llama.cpp, licence MIT) ?" && brew install llama.cpp
  else
    echo "Homebrew absent. Autre chemin : télécharger la version officielle « macos-arm64 » de llama.cpp sur GitHub."
    if oui "Télécharger llama.cpp depuis github.com/ggml-org/llama.cpp (dernière version, ~30 Mo, licence MIT) ?"; then
      URL=$(curl -s https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | "$VPY" -c \
        'import sys,json; a=[x["browser_download_url"] for x in json.load(sys.stdin)["assets"] if "macos-arm64" in x["name"] and x["name"].endswith(".zip")]; print(a[0] if a else "")')
      if [ -n "$URL" ]; then
        mkdir -p outils/bin/llama && curl -L -o outils/bin/llama.zip "$URL" && unzip -oq outils/bin/llama.zip -d outils/bin/llama
        S=$(find outils/bin/llama -name llama-server -type f | head -1)
        [ -n "$S" ] && ln -sf "$RACINE/$S" outils/bin/llama-server && echo "llama-server installé dans outils/bin."
      else
        echo "Version macos-arm64 introuvable sur GitHub : à vérifier à la main."
      fi
    fi
  fi
else
  echo "Hors Mac : installer llama.cpp à la main si besoin (mode essai)."
fi
export PATH="$RACINE/outils/bin:$PATH"

# ---------------------------------------------------------------- 5. Tests
titre "5. Tests (Internet coupé pour le programme pendant les tests)"
"$VPY" lancer.py tests || echo "ATTENTION : des tests échouent. Ne pas brancher de vrai robot avant correction."

# ---------------------------------------------------------------- 6. Téléchargements
if [ -z "$SANS_DL" ]; then
  titre "6. Modèles (rien sans votre oui, groupe par groupe)"
  "$VPY" outils/telecharger.py
fi

# ---------------------------------------------------------------- 7. Mesures
titre "7. Mesurer les vitesses et la mémoire"
ARGS=""; [ -n "$AUTRE_MAC" ] && ARGS="--autre-mac $AUTRE_MAC"
"$VPY" outils/mesurer.py $ARGS $GARDER

titre "8. Mesurer la voix : deux modèles d'écoute (mémoire, temps, mots faux, ordres compris)"
for M in small large-v3-turbo; do
  "$VPY" lancer.py banc-voix --modele "$M" || echo "Banc de la voix ($M) incomplet : voir les messages ci-dessus."
done

titre "9. Mesurer le cerveau : Apertus 8B, puis 4B, un à la fois (30 demandes × 6 langues)"
"$VPY" outils/banc_cerveaux_mac.py
"$VPY" lancer.py banc-cerveau --cerveaux regles

titre "10. Essai en option : modèle suisse allemand Flix-AI (seulement si la mémoire le permet)"
"$VPY" outils/essai_suisse_allemand.py

titre "Fini"
echo "Résultats dans : $RACINE/mesures/  — à envoyer à Hiba (fichiers .md)."
echo "Pour parler au robot : $VPY lancer.py micro"
echo "Pour lancer l'ossature : $VPY lancer.py   puis ouvrir http://localhost:8000"
