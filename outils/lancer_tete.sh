#!/bin/sh
# Lancer le programme de fond du Reachy Mini pour NOTRE système. À taper par un HUMAIN, robot branché en USB.
#
# NON TESTÉ SUR VRAI ROBOT.
#
# Ce programme (« daemon » : un programme du fabricant qui tourne à côté et qui parle aux moteurs) est nécessaire :
# c'est lui qui sait parler aux moteurs. Ce n'est PAS l'application du fabricant, et on ne s'en sert pas.
# Lancé comme ici :
#   - la tête NE BOUGE PAS (pas de réveil du fabricant, pas de coucher du fabricant à l'arrêt) ;
#   - il ne répond qu'à cet ordinateur, sur le port 8002 (le port 8000 est celui de notre écran) ;
#   - il n'envoie pas de mesures d'usage sur Internet et ne va pas chercher de gestes en ligne ;
#   - il ne prend ni la caméra ni le micro (la voix et l'écoute restent au Mac).
# C'est ensuite Iris qui lève la tête, lentement, après un « oui » sur l'écran (« réveille-toi »).
#
# Usage :   sh outils/lancer_tete.sh            le vrai robot (USB)
#           sh outils/lancer_tete.sh --simule   le faux robot du fabricant, pour essayer sans robot
# Pour arrêter : Ctrl+C dans cette fenêtre.

PROGRAMME="$HOME/reachy_env/bin/reachy-mini-daemon"
if [ ! -x "$PROGRAMME" ]; then
    echo "  Le kit du Reachy Mini n'est pas installé dans ~/reachy_env. Rien n'a été lancé."
    exit 2
fi
if lsof -nP -iTCP:8002 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  Un programme répond déjà sur le port 8002 (un autre lancement, ou le faux robot de la nuit)."
    echo "  L'arrêter d'abord :   pkill -f reachy-mini-daemon"
    echo "  Rien n'a été lancé."
    exit 2
fi

SIMULE=""
if [ "$1" = "--simule" ]; then
    SIMULE="--mockup-sim --headless"
    echo "  FAUX ROBOT du fabricant (simulé). Notre système entier le refuse (« MODE SIMULÉ ») : c'est voulu."
else
    echo "  VRAI ROBOT. Vérifier avant de continuer :"
    echo "    - le robot est au milieu de la table, rien sous la tête, personne penché dessus ;"
    echo "    - le responsable sécurité a une main sur la prise de courant du robot ;"
    echo "    - l'application du fabricant est fermée sur tous les ordinateurs."
    echo "  La tête ne doit PAS bouger au lancement. Si elle bouge : débrancher, et le dire."
    printf "  Taper « oui » puis Entrée pour lancer : "
    read REPONSE
    if [ "$REPONSE" != "oui" ]; then
        echo "  Rien n'a été lancé."
        exit 1
    fi
fi

export DO_NOT_TRACK=1 REACHY_MINI_TELEMETRY=0 HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
# caffeinate : un outil du Mac qui l'empêche de s'endormir tant que le programme tourne (aucun réglage n'est changé).
exec caffeinate -i "$PROGRAMME" $SIMULE --no-media --no-wake-up-on-start --no-goto-sleep-on-stop \
    --dataset-update-interval 0 --fastapi-host 127.0.0.1 --fastapi-port 8002
