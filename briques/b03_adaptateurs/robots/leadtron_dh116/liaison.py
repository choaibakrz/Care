"""ÉBAUCHE de liaison vers une main robotique Leadtron DH116 (main GAUCHE, 6 moteurs), par le kit Python du fabricant.

CETTE VERSION : NON TESTÉ SUR VRAI ROBOT. Elle n'a tourné qu'avec une doublure (doublure.py) : TESTÉ SUR FAUX ROBOT.
Une version D'AVANT a été essayée sur la vraie main le 15.11.2026, main vide, commandes tapées par Hiba (rapporté par le
coordinateur ; l'auteur de ce fichier ne l'a pas vu) : le test de conformité a réussi et « preparer_la_main » a ouvert
la main ; « tenir_doucement » à 150 pour mille a RATÉ, et a été dit raté (deux doigts n'ont presque pas avancé) ; ensuite
la mise en position de départ n'a plus fini, et la main est restée dite « en mouvement ». Les réglages ci-dessous ont
été changés APRÈS cet essai et ne sont PAS essayés sur la vraie main : le test de conformité sur la vraie main est à refaire.
DÉCISION DE HIBA (responsable du projet), le 15.11.2026 : « personne ne s'approche de la main, seuls des objets seront
à son contact ; ne pas être trop prudent ». Un DEUXIÈME essai sur la vraie main (limites 600 et 5000, rapporté par le
coordinateur) : les gestes marchent, mais « les doigts n'ont pas assez de force pour tenir le doudou et les doigts ne
bougent pas très bien ». NOUVELLE DÉCISION DE HIBA : « je te laisse faire le max de ton intelligence, je veux vraiment
que tu me sortes des commandes qui sortent de l'ordinaire, je veux que ça fasse un effet waouh de suite ».
D'où, dans CETTE version (pas essayée sur la vraie main) : les limites sont celles des EXEMPLES DU FABRICANT (courant
1000, vitesse 20000, position 10000), et les gestes sont décrits dans le fichier gestes.yaml, que l'équipe règle.
Le kit du fabricant reste HORS du projet (dossier Téléchargements) :
sa licence n'est pas indiquée, donc AUCUNE ligne de son code n'est copiée ici. On cite seulement des NOMS de fonctions.

Comment on lui parle : la main est reliée au MacBook par un boîtier USB (« CANFD Analyser » : il traduit l'USB vers le
câble de données de la main). Le fabricant livre un « kit » (SDK : des fonctions Python toutes prêtes) qui charge une
bibliothèque (`libLHandProLib.dylib`) et qui a besoin de `pyusb` (un paquet Python pour parler à l'USB).
Dans ce fichier, UNE SEULE classe touche à ce kit : `KitDeLaMain`. Elle l'importe dans son constructeur (jamais en haut
du fichier : le projet tourne sans lui), se connecte SANS allumer les moteurs et SANS rien bouger, et offre
dix-sept méthodes simples, en français. La liaison ne parle qu'à ces méthodes. La doublure offre les mêmes.

Ce que cette ébauche sait faire, et rien d'autre (demande de Hiba, 15.11.2026) :
    se connecter, dire son état   → des LECTURES : positions, états, alarmes, moteurs allumés ou non
    arrêt normal                  → PROPOSITION : arrêter les moteurs, puis VÉRIFIER que les doigts ne bougent plus
    arrêt d'urgence logiciel      → PROPOSITION : arrêter les moteurs, PUIS les couper (plus de force)
    réarmer                       → rien n'est envoyé à la main : les moteurs restent coupés
    geste « preparer_la_main »    → allume les moteurs, attend 1 s, écrit pour chaque moteur notre vitesse et notre
                                    courant les plus grands, puis lance la « mise en position de départ » du fabricant
                                    (son « home ») : la main S'OUVRE. C'est le seul geste permis sur une main pas
                                    préparée, et le seul chemin qui allume les moteurs.
    les treize autres gestes      → (ouvrir_la_main, tenir_doucement, attraper, bouger_les_doigts, poing, victoire,
                                    pouce_leve, pointer, rock, je_t_aime, compter, vague, pierre_feuille_ciseaux)
                                    décrits dans gestes.yaml : une suite d'ÉTAPES (six positions, une vitesse, un
                                    courant, une pause). La liaison lit le fichier à chaque geste, refuse tout ce qui
                                    sort des limites, et envoie les étapes UNE PAR UNE dans tic().
Saisir et poser restent « À BRANCHER » : on ne sait pas relier une force en newtons au courant des moteurs.
Les arrêts sont des PROPOSITIONS : le choix se fait avec le responsable sécurité, avant tout essai sur la vraie main.

LU le 15.11.2026 dans le kit du fabricant (LHandProLib du 31.10.2026 pour Mac, dossier arm64/ ; rien lancé, rien importé) :
- share/LHandProLib/examples/CANFD_python/lhandprolib_python_sdk/controller.py : `LHandProController` (= `CANFDController`).
- …/controller_base.py : `connect(enable_motors=True, home_motors=True, …)`. PAR DÉFAUT, SE CONNECTER ALLUME LES MOTEURS
  ET LANCE LA MISE EN POSITION DE DÉPART : LA MAIN BOUGE. Il faut `enable_motors=False, home_motors=False`.
  Après avoir allumé, le fabricant attend 1 s ; après la mise en position de départ, il attend 5 s (sans rien vérifier).
  `connect()` ne lève pas d'erreur : il rend False et écrit la raison à l'écran. `disconnect()` ferme tout.
  `sdk_handle` : la poignée vers la bibliothèque. `is_connected` : un drapeau du programme.
- …/controller_canfd.py : cherche le boîtier USB, prend LE PREMIER trouvé (sans demander), l'ouvre, puis appelle
  `initial_ex` (l'initialisation de la bibliothèque : ce qu'elle envoie à la main n'est pas lisible, voir plus bas).
- …/lhandprolib_wrapper.py : `get_dof`, `get_now_position`, `get_now_status`, `get_now_alarm`, `get_enable`,
  `get_position_reached`, `get_torque_reached`, `set_enable`, `home_motors`, `set_target_position`,
  `set_position_velocity`, `set_max_current`, `move_motors`, `stop_motors`. Les moteurs sont numérotés de 1 à 6 ;
  0 = tous. Une erreur du kit est une exception qui porte un `error_code`.
- …/lhandprolib_loader.py : les codes (LER_NOT_HOME = 11, LST_* de 0 à 7, LAM_* de 0 à 9) ; la bibliothèque est cherchée
  d'abord à l'adresse de la variable d'environnement LHANDPRO_LIB_PATH, puis dans des dossiers voisins du kit.
- docs/LHandProLib_SDK_Manual.md (en tête : « Version 1.7 » ; au pied du fichier : « Document version: v1.8 ») : position de 0 (« start position ») à 10000 (« full stroke ») ;
  vitesse en positions par seconde ; courant maximal en pour mille (« ‰ ») ; sans mise en position de départ, la main
  refuse de bouger (« Disallow movement without homing (default) ») ; ordre des six moteurs : pouce (écartement), pouce
  (flexion), index, majeur, annulaire, auriculaire ; `get_position_reached` : « 1 Position reached, 0 In motion ».
  Une phrase du manuel (à `play_gesture`) laisse entendre que la mise en position de départ et l'arrêt d'urgence de la
  main REMETTENT sa vitesse et son courant à leurs valeurs d'origine (« parameters reset by homing/e-stop »).
  Lignes 1317 à 1327 (à `move_motors`) : la vitesse et le courant ne sont envoyés à la main qu'au `move_motors` qui suit
  un `set_position_velocity` ou un `set_max_current` (« only re-sent after ») ; la position, elle, part à chaque fois.
  UN `move_motors` ENVOIE DONC PLUSIEURS MESSAGES : s'il est refusé en route, une partie a pu partir.
  Ligne 2160 (histoire des versions, v1.8) : vitesse et courant sont renvoyés d'office après `home_motors`,
  `stop_motors` et `play_gesture` (« automatic re-send after »). C'est écrit, pas vérifié sur la main.
- …/main.py : les exemples bougent à 20000 positions par seconde (toute la course en une demi-seconde) et à 1000 pour
  mille (toute la force). Depuis la décision de Hiba du 15.11.2026, ce sont NOS LIMITES (voir plus bas) ; les gestes
  du fichier gestes.yaml vont de 6000 à 16000 et de 600 à 1000 pour mille.
- …/README.md : sur Mac, le fabricant demande aussi `brew install libusb` (une bibliothèque du système pour l'USB).

À VÉRIFIER (pas lu, ou pas lisible : la bibliothèque est fermée) — la liste complète est dans fiches/leadtron_dh116.md :
- que fait la main quand on COUPE ses moteurs : les doigts deviennent-ils mous ? LÂCHE-T-ELLE l'objet, ou le garde-t-elle
  serré ? Et un doigt de personne pris dans la main est-il libéré ? ON NE LE SAIT PAS ;
- que fait la main quand on ALLUME ses moteurs (saute-t-elle vers une ancienne cible ?) : on le vérifie à chaque fois ;
- la mise en position de départ se fait à la vitesse et au courant du FABRICANT, pas aux nôtres : main VIDE, rien entre
  les doigts, personne ne la touche ;
- `stop_motors` arrête-t-il aussi une mise en position de départ en cours ? La main tient-elle sa place après ?
- ce que rendent VRAIMENT `get_now_status`, `get_position_reached` et `get_torque_reached` pendant un mouvement, à
  l'arrivée, et quand un doigt pousse sur un objet ; les lectures sont-elles fraîches, ou la dernière valeur connue ?
- si la main est débranchée, les lectures rendent-elles une erreur ? Sinon signe_de_vie() ne prouve rien ;
- après une mise en position de départ, la vitesse et le courant que NOUS avons réglés sont-ils bien renvoyés à la main
  au mouvement suivant (le manuel le dit, ligne 2160) ? Sinon elle partirait à sa vitesse d'origine. La liaison mesure la vitesse des doigts et arrête
  tout si elle dépasse deux fois la vitesse demandée : c'est un filet, pas une garantie ;
- le kit accepte-t-il deux appels en même temps (un arrêt d'urgence part dans un autre fil) ?
- toutes nos limites et toutes nos tolérances (plus bas) sont des choix de l'équipe, pas des mesures.
"""
from __future__ import annotations

import importlib
import importlib.util
import math
import os
import random
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import yaml

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide

# ---- Où est le kit du fabricant (hors du projet). Un humain peut donner un autre dossier dans LEADTRON_KIT.
KIT_DANS_L_ENVIRONNEMENT = "LEADTRON_KIT"
KIT_PAR_DEFAUT = Path.home() / "Downloads" / "lhandprolib-20261031-mac" / "contenu" / "arm64"
EXEMPLES_PYTHON = Path("share") / "LHandProLib" / "examples" / "CANFD_python"  # lu : le dossier du kit Python
PAQUET_DU_FABRICANT = "lhandprolib_python_sdk"  # lu : le nom de son paquet Python
BIBLIOTHEQUE = Path("lib") / "libLHandProLib.dylib"  # lu : la bibliothèque que son chargeur doit trouver
OU_EST_LA_BIBLIOTHEQUE = "LHANDPRO_LIB_PATH"  # lu (lhandprolib_loader.py) : la variable que son chargeur regarde d'abord
# pyusb a besoin de la bibliothèque « libusb » du système, et la cherche par son nom (ctypes.util.find_library). Elle
# n'est PAS installée sur ce Mac, mais le kit du fabricant en livre une dans son dossier lib/ (libusb-1.0.0.dylib ; le
# coordinateur a posé à côté un lien « libusb-1.0.dylib »). Vérifié le 15.11.2026 sur ce Mac (par le coordinateur, sans
# toucher à l'USB) : find_library la trouve quand la variable DYLD_FALLBACK_LIBRARY_PATH contient ce dossier, et ne
# trouve rien sans elle. Le constructeur de KitDeLaMain ajoute donc ce dossier à la variable, sans rien installer.
LIBUSB = "libusb-1.0.dylib"
OU_CHERCHER_LES_BIBLIOTHEQUES = "DYLD_FALLBACK_LIBRARY_PATH"
# Les dossiers que le système regarde quand cette variable est vide : on les garde (« ~/lib », écrit en entier).
DOSSIERS_PAR_DEFAUT = (str(Path.home() / "lib"), "/usr/local/lib", "/usr/lib")
# Lu (controller_canfd.py, lignes 128 à 131) : entre fermer et rouvrir le boîtier USB, le fabricant attend 0,2 s. Nous : 0,3 s.
PAUSE_AVANT_DE_ROUVRIR_S = 0.3
NUMERO_DE_LA_MAIN = 1  # lu : « canfd_node_id », 1 dans les exemples. Le vrai numéro de NOTRE main : à vérifier
DEBIT_LENT, DEBIT_RAPIDE = 1_000_000, 5_000_000  # lu (main.py) : les deux débits du câble de données, en bits par seconde

# ---- La main. Lu dans le manuel : l'ordre des six moteurs (leur numéro va de 1 à 6 dans cet ordre : à vérifier).
NOMBRE_DE_MOTEURS = 6
DOIGTS = ("pouce_ecartement", "pouce_flexion", "index", "majeur", "annulaire", "auriculaire")
# Lu (lhandprolib_loader.py, constantes LST_*, et manuel « Operating State ») : l'état de marche d'un moteur.
ARRETE, EN_MARCHE, EN_ALARME, BUTEE_HAUTE, BUTEE_BASSE, DEUX_BUTEES, ARRET_D_URGENCE_DE_LA_MAIN, EN_DEPART = range(8)
ETATS = {ARRETE: "arrêté", EN_MARCHE: "en marche", EN_ALARME: "arrêté sur une alarme", BUTEE_HAUTE: "en butée haute",
         BUTEE_BASSE: "en butée basse", DEUX_BUTEES: "en butée des deux côtés",
         ARRET_D_URGENCE_DE_LA_MAIN: "en arrêt d'urgence", EN_DEPART: "en mise en position de départ"}
ETATS_QUI_BOUGENT = (EN_MARCHE, EN_DEPART)
# Lu (constantes LAM_*, et manuel « Alarm Type ») : les alarmes d'un moteur. 0 = pas d'alarme. Traductions : les nôtres.
ALARMES = {1: "erreur de position", 2: "trop vite", 3: "trop de courant", 4: "surcharge", 5: "tension trop haute",
           6: "tension trop basse", 7: "erreur du capteur de position", 8: "moteur bloqué", 9: "autre alarme"}
PAS_ENCORE_AU_DEPART = 11  # lu : LER_NOT_HOME, « Homing Not Completed Error »
ERREURS_DE_COMMUNICATION = (5, 6, 7, 8)  # lu : LER_COMM_CONNECT, LER_COMM_SEND, LER_COMM_RECV, LER_COMM_DATA_FORMAT

# ---- NOS LIMITES = LES VALEURS DES EXEMPLES DU FABRICANT. Rien ne part au-delà : c'est refusé.
# Lu (main.py du kit) : ses exemples bougent à 20000 positions par seconde et 1000 pour mille, sur toute la course
# (10000). Ce sont ces valeurs-là, CHOISIES PAR HIBA (responsable du projet) le 15.11.2026 pour une main QUI NE TOUCHE
# QUE DES OBJETS : « personne ne s'approche de la main, seuls des objets seront à son contact ; ne pas être trop
# prudent », puis, après le deuxième essai (pas assez de force pour tenir le doudou) : « je te laisse faire le max de
# ton intelligence, je veux vraiment que tu me sortes des commandes qui sortent de l'ordinaire, je veux que ça fasse un
# effet waouh de suite ».
# ELLES NE SONT PAS ESSAYÉES SUR LA VRAIE MAIN PAR NOTRE SYSTÈME (le logiciel du fabricant, lui, s'en sert). À ces
# valeurs la main serre de toute sa force et se ferme en une demi-seconde : JAMAIS un doigt de personne dans la main.
# Historique : 2500 / 200 / 6000 (première version), puis 5000 / 600 / 6000 (après le premier essai réel).
COURSE = 10000  # lu : 10000 = toute la course d'un doigt
POSITION_MAX = 10000  # valeur du fabricant, choisie par Hiba, pas essayée par notre système : toute la course
VITESSE_MAX = 20000  # valeur des exemples du fabricant, choisie par Hiba, pas essayée par notre système : la course en 0,5 s
COURANT_MAX = 1000  # valeur des exemples du fabricant, choisie par Hiba, pas essayée par notre système : toute la force
# La vitesse demandée pour un geste ne fait que RALENTIR (1 = la vitesse écrite dans le fichier). Sous un quart, le geste
# est refusé : on ne remonte jamais une vitesse en silence.
VITESSE_RELATIVE_MIN = 0.25
# ---- LES GESTES. La CARTE liste les noms (elle fait partie de l'empreinte du test de conformité) ; le fichier
# gestes.yaml donne les formes : l'équipe le règle sans refaire le test de conformité. « preparer_la_main » n'est pas
# dans le fichier : il reste écrit ici (allumer, régler, mise en position de départ).
FICHIER_DES_GESTES = Path(__file__).with_name("gestes.yaml")
PREPARER, OUVRIR, TENIR, BOUGER = "preparer_la_main", "ouvrir_la_main", "tenir_doucement", "bouger_les_doigts"
GESTES = (PREPARER, OUVRIR, TENIR, "attraper", BOUGER, "poing", "victoire", "pouce_leve", "pointer", "rock", "je_t_aime",
          "compter", "vague", "pierre_feuille_ciseaux")  # dans cet ordre dans la carte : le test de conformité essaie le premier
ETAPES_MAX = 30  # au plus 30 étapes par geste
PAUSE_MAX_S = 3.0  # au plus 3 s de pause après une étape
DUREE_MAX_GESTE_S = 25.0  # un geste estimé à plus de 25 s est refusé (l'adaptateur arrête toute action après 30 s)
ENTRE_DEUX_ETAPES_S = 0.15  # pour l'estimation : le temps de voir l'arrivée d'une étape et d'envoyer la suivante

# ---- Nos tolérances et nos délais. Tous des choix de l'équipe, à vérifier sur la vraie main.
BOUGE = 30  # au-dessus de 30 positions (0,3 % de la course) entre deux lectures, un doigt est dit en mouvement
ENTRE_DEUX_LECTURES_S = 0.06
LECTURE_ENCORE_FRAICHE_S = 1.0  # une lecture gardée depuis moins d'1 s sert de point de comparaison
TOLERANCE = 300  # à la fin d'un geste, un doigt doit être à moins de 300 positions (3 % de la course) de sa cible
IMMOBILE_S = 0.3  # un doigt est dit « arrêté sur l'objet » seulement s'il n'a plus bougé depuis 0,3 s
ATTENTE_APRES_LANCEMENT_S = 0.5  # et jamais avant 0,5 s : une lecture d'avant le départ ne doit pas dire « fini »
# …et seulement s'il a AVANCÉ de plus de 300 positions depuis son départ : une main qui dit « couple atteint » sans
# qu'aucun doigt ait bougé n'a rien pris (relecture du 15.11.2026 : ce geste-là était dit « réussi »).
AVANCE_MIN = 300
MARGE_DUREE, ATTENTE_EN_PLUS_S = 1.5, 2.0  # un geste a droit à une fois et demie sa durée prévue, plus 2 s ; après : raté
# LE FILET « TROP VITE » : un doigt allé plus de 2 fois plus vite que la vitesse DEMANDÉE pour l'étape : tout est arrêté,
# raté. Il est proportionnel à la vitesse demandée : aux grandes vitesses (10000 et plus) il ne se déclencherait qu'au-delà
# de 20000, la plus grande vitesse des exemples du fabricant : là, en pratique, il ne protège plus de rien. Il reste
# utile pour une étape LENTE (6000 : il arrête une main partie à 20000). Mesuré sur la moyenne depuis le lancement.
FENETRE_VITESSE_S, SURVITESSE = 0.15, 2.0
ATTENTE_APRES_ALLUMAGE_S = 1.0  # lu : après avoir allumé les moteurs, le fabricant attend 1 s
SAUT_MAX = 300  # si un doigt a bougé de plus de 300 positions quand les moteurs se sont allumés : on recoupe
ATTENTE_DEPART_S = 5.0  # lu : après la mise en position de départ, le fabricant attend 5 s
# 20 s depuis le 15.11.2026 (12 s avant) : sur la vraie main, une mise en position de départ n'a pas fini en 12 s.
DELAI_DEPART_S = 20.0  # choix de l'équipe : une mise en position de départ pas finie après 20 s est dite ratée
# Avant de refuser « preparer_la_main » parce que la main bouge : un arrêt, puis au plus 0,5 s pour qu'elle se calme.
ATTENTE_AVANT_DE_PREPARER_S = 0.5
REPERE_AVANT_DE_PREPARER_S = 0.2  # le point de comparaison pour dire « les doigts ne bougent plus » pendant cette attente
ATTENTE_APRES_ARRET_S = 0.6  # après un arrêt, les doigts ont 0,6 s pour ne plus bouger…
BUDGET_ARRET_S = 0.85  # …sans jamais dépasser 0,85 s pour tout l'arrêt (une méthode de liaison rend la main en moins d'1 s)
BUDGET_AVANT_ENVOI_S = 0.4  # si les vérifications ont déjà pris plus de 0,4 s, l'ordre ne part pas
ECHEC_VISIBLE_S = 1.5  # un geste raté reste dit « echec_action » pendant 1,5 s, et aucun ordre ne part pendant ce temps


def _entier(valeur: Any, quoi: str, mini: int, maxi: int) -> int:
    """Un nombre ENTIER, fini, entre mini et maxi. Sinon : REFUS (rien ne part). Jamais ramené en silence."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ActionImpossible("hors_limites", f"{quoi} : « {valeur!r} » n'est pas un nombre : rien ne part")
    if not math.isfinite(valeur) or valeur != int(valeur):
        raise ActionImpossible("hors_limites", f"{quoi} : « {valeur!r} » n'est pas un nombre entier : rien ne part")
    if not mini <= valeur <= maxi:
        raise ActionImpossible("hors_limites", f"{quoi} : {valeur} est hors de nos limites ({mini} à {maxi}) : rien ne part")
    return int(valeur)


def ordre_permis(moteur: Any, position: Any, vitesse: Any, courant: Any) -> tuple[int, int, int, int]:
    """Les quatre nombres d'un ordre à UN moteur, vérifiés contre nos limites. La liaison ET la classe du kit l'appellent :
    rien ne peut partir vers la main au-delà de POSITION_MAX, VITESSE_MAX et COURANT_MAX."""
    return (_entier(moteur, "le numéro du moteur", 1, NOMBRE_DE_MOTEURS),
            _entier(position, "la position demandée", 0, POSITION_MAX),
            _entier(vitesse, "la vitesse demandée", 1, VITESSE_MAX),
            _entier(courant, "le courant demandé", 1, COURANT_MAX))


def _pyusb_est_la() -> bool:
    """Le kit du fabricant a besoin du paquet « pyusb » (son nom Python : usb). On regarde s'il est là, sans l'importer."""
    return importlib.util.find_spec("usb") is not None


class KitDeLaMain:
    """LE SEUL ENDROIT QUI TOUCHE AU KIT DU FABRICANT. Créé seulement pour la VRAIE main, après la confirmation tapée
    par un humain (feu orange). Chaque méthode fait UNE chose, avec les noms du fabricant lus le 15.11.2026.
    Elle ne sait PAS : effacer une alarme, bouger sans mise en position de départ, jouer un geste du fabricant, changer
    un réglage de la main. Ces fonctions du fabricant ne sont appelées nulle part."""

    def __init__(self, dossier: str | Path | None = None) -> None:
        dossier = Path(dossier or os.environ.get(KIT_DANS_L_ENVIRONNEMENT) or KIT_PAR_DEFAUT).expanduser()
        exemples = dossier / EXEMPLES_PYTHON
        if not (exemples / PAQUET_DU_FABRICANT / "controller.py").is_file():
            raise RuntimeError(f"le kit du fabricant de la main n'est pas dans « {dossier} » (attendu : le dossier arm64 "
                               f"de LHandProLib). Donner le bon dossier dans la variable {KIT_DANS_L_ENVIRONNEMENT}")
        if not _pyusb_est_la():
            raise RuntimeError("le paquet « pyusb » n'est pas installé : le kit du fabricant en a besoin pour parler au "
                               "boîtier USB. L'installer est un feu orange (taille, licence, « oui » de Hiba)")
        bibliotheque = dossier / BIBLIOTHEQUE
        if bibliotheque.is_file():  # on dit au chargeur du fabricant QUELLE bibliothèque prendre : celle de ce dossier
            os.environ.setdefault(OU_EST_LA_BIBLIOTHEQUE, str(bibliotheque))
        # AVANT d'importer le kit : montrer à pyusb où est la bibliothèque libusb livrée avec le kit (voir LIBUSB plus
        # haut ; vérifié le 15.11.2026 sur ce Mac). On garde ce que la variable contient déjà ; jamais deux fois.
        dossier_lib = bibliotheque.parent
        if (dossier_lib / LIBUSB).exists():
            deja = [d for d in os.environ.get(OU_CHERCHER_LES_BIBLIOTHEQUES, "").split(os.pathsep) if d]
            if str(dossier_lib) not in deja:
                os.environ[OU_CHERCHER_LES_BIBLIOTHEQUES] = os.pathsep.join([str(dossier_lib), *(deja or DOSSIERS_PAR_DEFAUT)])
        if str(exemples) not in sys.path:
            sys.path.append(str(exemples))  # À LA FIN de la liste : rien du fabricant ne passe devant nos fichiers
        try:
            module = importlib.import_module(PAQUET_DU_FABRICANT + ".controller")  # lu le 15.11.2026 : controller.py
        except Exception as erreur:
            raise RuntimeError(f"le kit du fabricant de la main ne se charge pas : {type(erreur).__name__} : {erreur}") from erreur
        # Lu : LHandProController(communication_mode="CANFD", canfd_node_id=…). Rien n'est envoyé ici.
        self._controleur = module.LHandProController(communication_mode="CANFD", canfd_node_id=NUMERO_DE_LA_MAIN)
        self._fermee_a: float | None = None  # l'heure de la dernière fermeture du boîtier USB (None : jamais fermé)
        self.relier()

    def relier(self) -> None:
        """Se connecter à la main SANS allumer ses moteurs et SANS rien bouger. Déjà reliée : rien n'est fait."""
        controleur = self._controleur
        if controleur.is_connected and controleur.sdk_handle is not None:
            return
        if controleur.sdk_handle is not None:
            controleur.disconnect()  # lu : sans cela, connect() refuse (« disconnect first »)
            self._fermee_a = time.monotonic()
        # Après une fermeture, on laisse 0,3 s au boîtier USB avant de le rouvrir (le fabricant : 0,2 s). Le test de
        # conformité ferme et rouvre plusieurs fois de suite. Cette pause compte dans les 1,8 s de ouvrir().
        if self._fermee_a is not None:
            attente = self._fermee_a + PAUSE_AVANT_DE_ROUVRIR_S - time.monotonic()
            if attente > 0:
                time.sleep(attente)
        # LU : par défaut, connect() ALLUME LES MOTEURS ET LANCE LA MISE EN POSITION DE DÉPART. Ici : ni l'un ni l'autre.
        # Ce que la bibliothèque envoie pendant son initialisation (« initial_ex ») n'est pas lisible : à vérifier.
        relie = controleur.connect(enable_motors=False, home_motors=False,
                                   canfd_nom_baudrate=DEBIT_LENT, canfd_dat_baudrate=DEBIT_RAPIDE)
        if not relie or controleur.sdk_handle is None:  # lu : connect() rend False et écrit la raison à l'écran
            raise ConnectionError("la main ne répond pas (boîtier USB branché avec le câble à grande fiche ? main sous "
                                  "tension ? logiciel du fabricant fermé ? ou la bibliothèque libusb n'est pas trouvée) : "
                                  "voir le message du kit juste au-dessus")

    def _main(self) -> Any:
        """La poignée du fabricant (« sdk_handle »), seulement tant que son programme dit la liaison ouverte."""
        poignee = self._controleur.sdk_handle
        if poignee is None or not self._controleur.is_connected:
            raise ConnectionError("la liaison avec la main n'est pas ouverte (boîtier USB débranché ?)")
        return poignee

    @staticmethod
    def _redire(erreur: Exception, quoi: str, lecture: bool) -> Exception:
        """Le kit répond par un code : on le redit simplement. Une LECTURE ratée = on ne sait plus rien : liaison perdue."""
        code = getattr(erreur, "error_code", None)  # lu : LHandProLibError porte « error_code »
        if code == PAS_ENCORE_AU_DEPART:
            return ActionImpossible("main_pas_preparee", f"la main refuse « {quoi} » : sa mise en position de départ "
                                    "n'est pas faite (lui demander d'abord de se préparer)")
        if lecture or code is None or code in ERREURS_DE_COMMUNICATION:
            return ConnectionError(f"la main ne répond pas à « {quoi} » : {type(erreur).__name__} : {erreur}")
        return ActionImpossible("robot_refuse", f"la main refuse « {quoi} » (code {code} du fabricant)")

    def _six(self, quoi: str, lire_un: Callable[[Any, int], Any]) -> list[Any]:
        main = self._main()
        try:
            return [lire_un(main, numero) for numero in range(1, NOMBRE_DE_MOTEURS + 1)]
        except Exception as erreur:
            raise self._redire(erreur, quoi, lecture=True) from erreur

    def _ordonner(self, quoi: str, envoyer: Callable[[Any], Any]) -> None:
        main = self._main()
        try:
            envoyer(main)
        except Exception as erreur:
            raise self._redire(erreur, quoi, lecture=False) from erreur

    # ---------------------------------------------------------------- des LECTURES (rien ne bouge)
    def nombre_de_moteurs(self) -> int:
        main = self._main()
        try:
            _, actifs = main.get_dof()  # lu : rend (total, actifs)
        except Exception as erreur:
            raise self._redire(erreur, "compter les moteurs", lecture=True) from erreur
        return int(actifs)

    def positions(self) -> list[int]:
        return [int(v) for v in self._six("lire les positions", lambda main, n: main.get_now_position(n))]

    def etats(self) -> list[int]:
        return [int(v) for v in self._six("lire les états", lambda main, n: main.get_now_status(n))]

    def alarmes(self) -> list[int]:
        return [int(v) for v in self._six("lire les alarmes", lambda main, n: main.get_now_alarm(n))]

    def moteurs_allumes(self) -> list[bool]:
        return [bool(v) for v in self._six("lire si les moteurs sont allumés", lambda main, n: main.get_enable(n))]

    def cibles_atteintes(self) -> list[bool]:
        return [bool(v) for v in self._six("lire les arrivées", lambda main, n: main.get_position_reached(n))]

    def couples_atteints(self) -> list[bool]:
        return [bool(v) for v in self._six("lire les couples", lambda main, n: main.get_torque_reached(n))]

    # ---------------------------------------------------------------- des ORDRES
    def allumer_les_moteurs(self) -> None:
        self._ordonner("allumer les moteurs", lambda main: main.set_enable(0, True))  # lu : 0 = tous les moteurs

    def couper_les_moteurs(self) -> None:
        self._ordonner("couper les moteurs", lambda main: main.set_enable(0, False))

    def mise_en_position_de_depart(self) -> None:
        self._ordonner("la mise en position de départ", lambda main: main.home_motors(0))  # la main BOUGE, à SA vitesse

    def donner_une_cible(self, moteur: int, position: int, vitesse: int, courant: int) -> None:
        """Régler la cible, la vitesse et le courant d'UN moteur. Rien ne bouge encore. Revérifié ici contre nos limites."""
        moteur, position, vitesse, courant = ordre_permis(moteur, position, vitesse, courant)

        def regler(main: Any) -> None:
            main.set_target_position(moteur, position)
            main.set_position_velocity(moteur, vitesse)
            main.set_max_current(moteur, courant)

        self._ordonner("régler une cible", regler)

    def regler_vitesse_et_courant(self, vitesse: int, courant: int) -> None:
        """Écrire, pour CHAQUE moteur (1 à 6), une vitesse et un courant maximal, SANS cible et SANS mouvement.
        Revérifié ici contre nos limites. Lu (manuel, lignes 1317 à 1327) : ces valeurs ne partent vers la main qu'au
        mouvement suivant, ou tout de suite avec « envoyer_les_reglages »."""
        _, _, vitesse, courant = ordre_permis(1, 0, vitesse, courant)

        def regler(main: Any) -> None:
            for numero in range(1, NOMBRE_DE_MOTEURS + 1):
                main.set_position_velocity(numero, vitesse)
                main.set_max_current(numero, courant)

        self._ordonner("régler la vitesse et le courant", regler)

    def envoyer_les_reglages(self) -> None:
        # Lu le 15.11.2026 (lhandprolib_wrapper.py, et manuel lignes 1332 à 1353, « apply_motion_params ») : « Apply
        # target velocity/current changes immediately » ; rien n'est envoyé si rien n'a changé. Pas un mouvement.
        self._ordonner("envoyer les réglages", lambda main: main.apply_motion_params())

    def lancer_le_mouvement(self) -> None:
        self._ordonner("lancer le mouvement", lambda main: main.move_motors(0))

    def arreter_les_moteurs(self) -> None:
        self._ordonner("arrêter les moteurs", lambda main: main.stop_motors(0))

    def fermer(self) -> None:
        self._controleur.disconnect()  # lu : ferme le boîtier USB et la bibliothèque ; n'allume ni ne coupe rien
        self._fermee_a = time.monotonic()


class _SansCleEnDouble(yaml.SafeLoader):
    """Lit un fichier YAML comme d'habitude, mais REFUSE une clé écrite deux fois (sans cela, la dernière gagne en
    silence : un doigt écrit deux fois dans gestes.yaml aurait pris la seconde valeur sans rien dire)."""

    def construct_mapping(self, node: Any, deep: bool = False) -> dict:
        vues = set()
        for noeud_de_la_cle, _ in node.value:
            cle = self.construct_object(noeud_de_la_cle, deep=True)
            if cle in vues:
                raise yaml.constructor.ConstructorError(None, None, f"« {cle} » est écrit deux fois", noeud_de_la_cle.start_mark)
            vues.add(cle)
        return super().construct_mapping(node, deep=deep)


@dataclass
class _Lecture:
    """Ce que la main dit d'elle, lu à l'instant : six nombres par ligne."""
    positions: list[int]
    etats: list[int]
    alarmes: list[int]
    allumes: list[bool]


@dataclass(frozen=True)
class _Etape:
    """Une étape d'un geste, lue dans gestes.yaml et déjà vérifiée contre nos limites."""
    cibles: tuple[int, ...]  # les six positions, dans l'ordre des moteurs
    vitesse: int
    courant: int
    pause_s: float = 0.0  # la pause APRÈS l'étape (ou, si on n'attend pas l'arrivée, le temps avant l'étape suivante)
    attendre: bool = True  # attendre que les doigts soient VÉRIFIÉS arrivés avant de passer à la suite ?


@dataclass
class _Geste:
    """Le geste en route. Il n'est « fini » que quand la liaison l'a VÉRIFIÉ (dans tic)."""
    generation: int
    nom: str
    phase: str  # « allumage » (on attend 1 s), « depart » (mise en position de départ), « mouvement » ou « pause »
    debut: float  # l'heure du dernier ordre envoyé pour ce geste
    depart: list[int]  # les positions lues juste avant cet ordre
    cibles: list[int]
    vitesse: int = 0
    limite: float = 0.0  # l'heure après laquelle le mouvement est dit raté
    vu_en_depart: bool = False  # la main a-t-elle dit « mise en position de départ en cours » ?
    repere: tuple[float, list[int]] | None = None  # (heure, positions) : depuis quand les doigts ne bougent plus
    pause_s: float = 0.0  # la pause de l'étape en cours
    attendre: bool = True  # l'étape en cours attend-elle l'arrivée des doigts ?
    fin_de_pause: float = 0.0
    origine: list[int] = field(default_factory=list)  # les positions au tout début du GESTE (pas de l'étape)
    # Les étapes PAS ENCORE envoyées. La suivante ne part que quand l'étape en cours est finie (arrivée VÉRIFIÉE, puis sa
    # pause). Un arrêt oublie tout le geste, donc la file : plus rien ne part.
    file: list[_Etape] = field(default_factory=list)


class LiaisonLeadtronDh116(LiaisonVide):
    chemin = "sdk"
    # Les deux actions obligatoires et « rejouer_geste » (quatorze gestes), essayés sur faux robot seulement dans cette version.
    # Les arrêts sont des PROPOSITIONS, à confirmer avec le responsable sécurité.
    branchees = frozenset({"arreter", "etat", "rejouer_geste"})
    sait_aller_au_lieu = False  # une main posée ou fixée sur une table : elle ne va nulle part
    # Pas pour ce robot (le modèle vide répond « À BRANCHER ») : vitesse (elle ne se déplace pas), regarder, montrer,
    # parler, ecouter (ni tête, ni haut-parleur, ni micro). Saisir et poser : voir tout en bas.

    def __init__(self, kit: Any, gestes: Path = FICHIER_DES_GESTES) -> None:
        self.kit = kit
        # Faux ou vrai : décidé par la CLASSE du kit (un faux kit du projet, comme la doublure), jamais par ce que le kit dit.
        self.vrai_robot = not isinstance(kit, FauxKit)
        self.repere_du_monde = False  # pas d'odomètre : aucune position n'est donnée au gardien
        self.lent = False  # mis par adaptateur.py ; en mode lent, l'adaptateur demande déjà les gestes à mi-vitesse
        self._gestes = gestes  # le fichier des gestes, relu à CHAQUE geste (l'équipe le règle sans relancer le programme)
        # Le hasard de « pierre_feuille_ciseaux » : une fonction qui choisit un nom dans une liste. Les essais la remplacent.
        self.tirer_au_hasard: Callable[[list[str]], str] = random.Random().choice
        self._dernier_tirage: str | None = None  # le dernier tirage au hasard VRAIMENT joué (dit dans lire_etat)
        # La génération avance à chaque arrêt : un geste d'avant l'arrêt ne compte plus, et rien de lui ne part plus.
        self._generation = 0
        self._geste: _Geste | None = None
        self._echec: tuple[float, str] | None = None  # (heure, texte) du dernier geste raté
        self._alerte: str | None = None  # un ordre qu'on n'a pas réussi à arrêter : dit jusqu'au prochain arrêt réussi
        self._arrets_en_cours = 0  # tant qu'un arrêt travaille (dans un autre fil), aucun ordre ne part
        self._verrou_arrets = threading.Lock()  # deux arrêts peuvent travailler en même temps, dans deux fils
        # Après un arrêt d'URGENCE : plus aucun ordre, plus aucun allumage, jusqu'à ce qu'un humain réarme.
        # (L'adaptateur a déjà ce verrou ; la liaison garde le sien, pour le cas où un arrêt passe entre les deux.)
        self._urgence = False
        # « Main préparée » : NOTRE mise en position de départ a réussi depuis que les moteurs sont allumés. Le kit n'a
        # pas de lecture pour cela (rien lu) : la liaison s'en souvient elle-même. Dans le doute : pas préparée.
        self._depart_fait = False
        # Est-ce NOUS qui avons allumé les moteurs (par « preparer_la_main ») ? Si oui, fermer() les coupe avant de fermer.
        self._allumes_par_nous = False
        # Si la main refuse nos réglages juste avant sa mise en position de départ : c'est dit dans l'état (pas caché).
        self._remarque: str | None = None
        self._derniere: tuple[float, list[int]] | None = None  # (heure, positions) de la dernière lecture

    @staticmethod
    def creer_kit(dossier: str | Path | None = None, **options: Any) -> Any:
        """Créer le kit de la VRAIE main. Appelé seulement après la confirmation tapée par un humain (feu orange).
        Le kit du fabricant s'importe ICI (dans KitDeLaMain), jamais en haut du fichier : le projet tourne sans lui.
        Il se connecte SANS allumer les moteurs et SANS mise en position de départ : rien ne bouge (à vérifier sur la
        main). Le logiciel du fabricant doit être FERMÉ : un seul programme parle au boîtier USB.
        Le dossier du kit : la variable LEADTRON_KIT, sinon ~/Downloads/lhandprolib-20261031-mac/contenu/arm64."""
        return KitDeLaMain(dossier)

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else {"limites": {}, "gestes": []}

    # ---------------------------------------------------------------- lire (rien ne bouge)
    @staticmethod
    def _nombres(valeurs: Any, quoi: str) -> list[int]:
        """Six nombres finis, sinon la lecture est dite illisible (une liaison perdue, jamais une autre erreur)."""
        if not isinstance(valeurs, (list, tuple)) or len(valeurs) != NOMBRE_DE_MOTEURS:
            raise ConnectionError(f"lecture illisible de la main : {quoi}")
        for valeur in valeurs:
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur):
                raise ConnectionError(f"lecture illisible de la main : {quoi}")
        return [int(valeur) for valeur in valeurs]

    @staticmethod
    def _oui_non(valeurs: Any, quoi: str) -> list[bool]:
        """Six « oui » ou « non », sinon la lecture est dite illisible."""
        if (not isinstance(valeurs, (list, tuple)) or len(valeurs) != NOMBRE_DE_MOTEURS
                or any(not isinstance(valeur, bool) and valeur not in (0, 1) for valeur in valeurs)):
            raise ConnectionError(f"lecture illisible de la main : {quoi}")
        return [bool(valeur) for valeur in valeurs]

    def _lecture(self) -> _Lecture:
        """Quatre lectures. Aucune ne fait bouger la main."""
        return _Lecture(positions=self._nombres(self.kit.positions(), "ses positions"),
                        etats=self._nombres(self.kit.etats(), "ses états"),
                        alarmes=self._nombres(self.kit.alarmes(), "ses alarmes"),
                        allumes=self._oui_non(self.kit.moteurs_allumes(), "ses moteurs allumés ou non"))

    def _les_doigts_bougent(self, positions: list[int] | None = None, frais: bool = False) -> bool:
        """Compare deux lectures de position. `frais` : toujours deux lectures neuves, à 0,06 s d'écart.
        Sinon, la lecture gardée en mémoire sert de point de comparaison si elle a moins d'une seconde."""
        maintenant = time.monotonic()
        if positions is None:
            positions = self._nombres(self.kit.positions(), "ses positions")
        avant = None if frais else self._derniere
        if avant is None or maintenant - avant[0] > LECTURE_ENCORE_FRAICHE_S:
            avant = (maintenant, positions)
            time.sleep(ENTRE_DEUX_LECTURES_S)
            maintenant, positions = time.monotonic(), self._nombres(self.kit.positions(), "ses positions")
        self._derniere = (maintenant, positions)
        return max(abs(a - b) for a, b in zip(avant[1], positions)) > BOUGE

    @staticmethod
    def _ce_que_dit_la_main(lu: _Lecture) -> list[str]:
        """Les alarmes et les états anormaux, doigt par doigt, en mots simples."""
        textes = []
        for doigt, etat, alarme in zip(DOIGTS, lu.etats, lu.alarmes):
            if alarme:
                textes.append(f"la main dit : {doigt} : {ALARMES.get(alarme, 'alarme inconnue (à vérifier dans la doc du fabricant)')} "
                              f"(alarme {alarme})")
            elif etat == EN_ALARME:
                textes.append(f"la main dit : {doigt} : arrêté sur une alarme")
            if etat == ARRET_D_URGENCE_DE_LA_MAIN:
                textes.append(f"la main dit : {doigt} : en arrêt d'urgence")
            elif etat not in ETATS:
                textes.append(f"la main dit : {doigt} : un état inconnu ({etat}) (à vérifier dans la doc du fabricant)")
        return textes

    def _en_route(self) -> bool:
        geste = self._geste
        return geste is not None and geste.generation == self._generation

    # ---------------------------------------------------------------- la connexion (des lectures, rien ne bouge)
    def ouvrir(self) -> None:
        # « relier » ne fait que se connecter, moteurs éteints (voir KitDeLaMain.relier). Déjà reliée : rien n'est fait.
        self.kit.relier()
        nombre = self.kit.nombre_de_moteurs()
        if nombre != NOMBRE_DE_MOTEURS:
            raise ConnectionError(f"ce n'est pas la main attendue : elle dit avoir {nombre} moteurs, pas {NOMBRE_DE_MOTEURS}")
        self._lecture()
        self._depart_fait = False  # une liaison neuve : on ne sait pas si la main est préparée. Dans le doute : non.

    def fermer(self) -> None:
        # Décision du 15.11.2026 (relecture) : si c'est NOUS qui avons allumé les moteurs, on les COUPE avant de fermer.
        # Sans cela, un Ctrl+C ou une erreur après « preparer_la_main » laissait la main sous force, sans personne pour
        # la commander. Au mieux : une coupure qui rate n'empêche pas de fermer (et ne lève pas d'erreur).
        # ON NE SAIT PAS si la main LÂCHE alors l'objet qu'elle tient, ou le garde serré (à vérifier sur la vraie main).
        # Des moteurs allumés par un AUTRE programme (le logiciel du fabricant) ne sont pas coupés ici.
        self._depart_fait = False  # dans tous les cas, la main n'est plus dite « préparée »
        if self._allumes_par_nous:
            try:
                self.kit.couper_les_moteurs()
                self._allumes_par_nous = False
            except Exception:
                pass  # la liaison est peut-être déjà tombée : on ferme quand même
        self.kit.fermer()

    def signe_de_vie(self) -> None:
        # Une lecture courte. ATTENTION (à vérifier) : si le kit rend la dernière valeur connue quand la main est
        # débranchée, cette lecture ne prouve rien. Le kit n'a pas d'autre signe de vie (rien lu).
        self._nombres(self.kit.positions(), "ses positions")

    def lire_etat(self) -> dict[str, Any]:
        try:
            lu = self._lecture()
            les_doigts_bougent = self._les_doigts_bougent(lu.positions)
        except Exception as erreur:
            # Une lecture qui rate : on ne sait plus rien de la main. Le geste en route est dit RATÉ (jamais effacé :
            # sinon un autre lecteur, comme l'écran, avalerait l'échec), et on tente d'arrêter les moteurs.
            self._abandonner(f"le geste de la main est abandonné : une lecture de son état a raté ({erreur})")
            raise
        if not all(lu.allumes):
            self._depart_fait = False  # moteurs coupés : la main n'est plus « préparée » (prudence : voir plus haut)
        a_suivre = self._en_route()
        erreurs = self._ce_que_dit_la_main(lu)
        # Dans le doute, la main est dite EN MOUVEMENT (le sens sûr) : un état « en marche », « en mise en position de
        # départ » ou inconnu, des doigts qui changent de place, un geste pas encore vérifié.
        bouge = (les_doigts_bougent or a_suivre
                 or any(etat in ETATS_QUI_BOUGENT or etat not in ETATS for etat in lu.etats))
        echec = self._echec
        echec = echec if echec is not None and time.monotonic() - echec[0] < ECHEC_VISIBLE_S else None
        if echec is not None:
            erreurs.append(echec[1])
        alerte = self._alerte
        if alerte is not None:  # un ordre pas arrêté : on le dit, et la main est dite en mouvement (le sens sûr)
            erreurs.append(alerte)
            bouge = True
        remarque = self._remarque
        if remarque is not None:
            erreurs.append(remarque)
        return {"batterie_pct": None,  # elle est sur une alimentation (12 à 24 V, étiquette) : pas de batterie
                "x": None, "y": None, "cap": None,  # elle est posée ou fixée sur une table
                "en_mouvement": bouge, "occupe": a_suivre,
                "objet_tenu": None,  # on ne sait pas ce que la main tient : la carte ne promet ni saisir ni poser
                "erreurs": erreurs,
                "arret_urgence": any(etat == ARRET_D_URGENCE_DE_LA_MAIN for etat in lu.etats),  # ce que la MAIN dit
                # Un geste raté en route : dit ici pendant 1,5 s. L'adaptateur, qui attend la fin de l'action,
                # le lit et compte l'action comme RATÉE (jamais « réussie »). Les autres lecteurs n'y perdent rien.
                "echec_action": echec[1] if echec is not None else None,
                # Le dernier tirage au hasard joué (« pierre_feuille_ciseaux » : poing, ouvrir_la_main ou victoire) ; None : jamais.
                "dernier_tirage": self._dernier_tirage,
                "entendu": None}

    # ---------------------------------------------------------------- s'arrêter (PROPOSITIONS, à confirmer avec le responsable sécurité)
    def _arret_est_passe(self, generation: int) -> bool:
        return generation != self._generation or self._arrets_en_cours > 0 or self._urgence

    def _plus_rien_a_suivre(self) -> None:
        """Un arrêt : plus rien du geste en route ne partira. Fait EN PREMIER, sans rien attendre et sans rien lire."""
        with self._verrou_arrets:
            self._generation += 1
        self._geste = None
        self._echec = None

    def _abandonner(self, texte: str) -> None:
        """PAS un arrêt demandé : notre geste est abandonné en route. Il est dit RATÉ, et on tente d'arrêter les moteurs
        (sans rien promettre : la liaison vient peut-être de se perdre)."""
        geste = self._geste
        if geste is None or geste.generation != self._generation:
            return
        self._rater(geste, texte)

    def _rater(self, geste: _Geste, texte: str) -> None:
        if geste.generation != self._generation:
            return  # un arrêt est passé entre-temps : c'est un arrêt, pas un échec
        self._echec = (time.monotonic(), texte)  # d'abord l'échec, ensuite « plus occupé » : jamais l'inverse
        self._geste = None
        if self._arrets_en_cours > 0:
            return  # un arrêt travaille déjà : il arrête les moteurs lui-même
        try:
            if geste.phase == "allumage":
                self.kit.couper_les_moteurs()  # nous venions de les allumer, et rien n'a encore bougé : on les recoupe
                self._allumes_par_nous = False
            else:
                self.kit.arreter_les_moteurs()
        except Exception as erreur:  # celui qui lit l'état recevra de toute façon l'échec ; et ceci reste dit
            self._alerte = f"un geste raté de la main n'a pas pu être arrêté ({erreur}) : arrêter la main"

    def arreter_mouvement(self) -> None:
        # PROPOSITION : arrêter les moteurs (lu : « stop_motors », « Stop motor movement »), puis VÉRIFIER que les
        # positions ne changent plus. À vérifier sur la main : la main tient-elle sa place (et l'objet) après cet arrêt ?
        # arrête-t-il aussi une mise en position de départ ? S'il ne l'arrête pas, la vérification le dit.
        debut = time.monotonic()
        self._plus_rien_a_suivre()
        with self._verrou_arrets:
            self._arrets_en_cours += 1  # tant que cet arrêt travaille, aucun ordre ne part (voir _libre)
        try:
            self.kit.arreter_les_moteurs()
            # Après l'arrêt, les doigts ont 0,6 s pour ne plus bouger, sans jamais dépasser 0,85 s pour tout l'arrêt.
            fin = min(time.monotonic() + ATTENTE_APRES_ARRET_S, debut + BUDGET_ARRET_S)
            while self._les_doigts_bougent(frais=True):
                if time.monotonic() < fin:
                    continue
                raise ActionImpossible("arret_non_confirme", "les doigts de la main bougent encore après l'ordre d'arrêt. "
                                       "Couper les moteurs, ou débrancher son alimentation.")
            self._alerte = None  # un arrêt entièrement vérifié : l'alerte d'avant n'a plus lieu d'être
        finally:
            with self._verrou_arrets:
                self._arrets_en_cours -= 1

    def arret_urgence(self) -> None:
        # PROPOSITION, À CONFIRMER AVEC LE RESPONSABLE SÉCURITÉ : arrêter les moteurs, PUIS les couper (plus de force).
        # ON NE SAIT PAS ce que fait la main quand ses moteurs sont coupés : LÂCHE-T-ELLE l'objet, ou le GARDE-T-ELLE
        # serré ? Un doigt de personne pris dans la main est-il libéré ? À VÉRIFIER sur la vraie main, main vide d'abord.
        # À décider aussi : l'ordre des deux. Ici l'arrêt part en premier ; s'il reste coincé dans le kit, la coupure ne
        # part pas dans ce fil (l'adaptateur relance alors un arrêt dans un autre fil). Couper d'abord ? Choix humain.
        # Ce n'est PAS un verrou : un autre programme (le logiciel du fabricant) peut rallumer les moteurs.
        # Il ne remplace JAMAIS le fait de débrancher l'alimentation de la main.
        self._urgence = True  # AVANT tout : plus aucun ordre ni allumage jusqu'au réarmement par un humain
        self._plus_rien_a_suivre()
        self._depart_fait = False  # après une coupure, la main n'est plus « préparée »
        with self._verrou_arrets:
            self._arrets_en_cours += 1
        arret_rate = coupure_ratee = None
        try:
            try:
                self.kit.arreter_les_moteurs()
            except Exception as erreur:  # la coupure part quand même
                arret_rate = erreur
            try:
                self.kit.couper_les_moteurs()
                self._allumes_par_nous = False  # coupés : fermer() n'aura pas à le refaire
            except Exception as erreur:
                coupure_ratee = erreur
            if arret_rate is None and coupure_ratee is None:
                self._alerte = None  # arrêtés et coupés : l'alerte d'avant n'a plus lieu d'être
            # La lecture gardée en mémoire date d'AVANT l'arrêt (les doigts bougeaient) : on l'oublie. La prochaine
            # lecture d'état fera deux lectures neuves pour dire si la main bouge encore.
            self._derniere = None
        finally:
            with self._verrou_arrets:
                self._arrets_en_cours -= 1
        if coupure_ratee is not None:
            raise coupure_ratee
        if arret_rate is not None:
            raise arret_rate

    def rearmer(self) -> None:
        # Rien n'est envoyé à la main : les moteurs restent coupés. Réarmer (une décision d'humain) lève seulement le
        # verrou d'urgence de la liaison. Rallumer les moteurs est une étape à part : le geste « preparer_la_main »,
        # accordé par le gardien. (Les alarmes de la main ne sont JAMAIS effacées par notre système : un humain regarde.)
        self._urgence = False
        return None

    # ---------------------------------------------------------------- bouger les doigts (les gestes du fichier gestes.yaml)
    # Les règles tenues ici, les mêmes que pour la tête du Reachy Mini :
    # 1. Un arrêt passe TOUJOURS devant : la génération est lue à la première ligne de geste() ; un ordre ne part pas
    #    si elle a changé, et s'il est parti pendant qu'un arrêt passait, les moteurs sont arrêtés tout de suite.
    # 2. Jamais deux gestes à la fois.
    # 3. Une étape n'est « finie » que si CHAQUE doigt est arrivé à sa cible, ou s'est arrêté sur l'objet (« couple
    #    atteint » après avoir avancé : pour tous les gestes), ou y était déjà ; sans alarme et moteurs allumés. Sinon
    #    le geste est dit RATÉ. Un geste est fini quand sa dernière étape l'est.
    # 4. Une lecture qui rate, une alarme, des moteurs coupés, un doigt trop rapide : le geste est dit raté, moteurs arrêtés.
    # 5. Une main pas préparée refuse tout, sauf « preparer_la_main ».
    def _libre(self) -> None:
        """Avant un nouvel ordre : pas d'arrêt d'urgence, pas d'arrêt en cours, pas d'échec tout frais, RIEN en route."""
        if self._urgence:
            raise ActionImpossible("arret_urgence_actif", "arrêt d'urgence : aucun ordre à la main avant qu'un humain réarme")
        if self._arrets_en_cours > 0:
            raise ActionImpossible("arrete", "un arrêt est en cours : l'ordre à la main n'est pas parti")
        echec = self._echec
        if echec is not None and time.monotonic() - echec[0] < ECHEC_VISIBLE_S:
            raise ActionImpossible("robot_occupe", "le geste d'avant vient de rater : attendre un instant")
        if self._alerte is not None:
            raise ActionImpossible("robot_occupe", "un ordre n'a pas pu être arrêté : arrêter la main d'abord")
        if self._en_route():
            raise ActionImpossible("robot_occupe", "la main fait déjà un geste : jamais deux à la fois. Arrêter d'abord.")

    def _sans_alarme(self, lu: _Lecture) -> None:
        """Pas d'alarme, pas d'arrêt d'urgence de la main. Sinon rien ne part : notre système n'efface jamais une alarme."""
        dit = self._ce_que_dit_la_main(lu)
        if dit:
            raise ActionImpossible("alarme", "la main signale un problème : " + " ; ".join(dit) + ". Rien ne part : "
                                   "un humain regarde la main (notre système n'efface jamais une alarme).")

    def _calme(self, lu: _Lecture) -> None:
        """Pas d'alarme, pas d'arrêt d'urgence de la main, et rien ne bouge (un autre programme la commande-t-il ?)."""
        self._sans_alarme(lu)
        if any(etat in ETATS_QUI_BOUGENT for etat in lu.etats) or self._les_doigts_bougent(lu.positions):
            raise ActionImpossible("robot_occupe", "la main bouge déjà (le logiciel du fabricant est-il ouvert ?). Arrêter d'abord.")

    def _arreter_avant_de_preparer(self, generation: int) -> _Lecture:
        """« preparer_la_main » trouve la main dite en mouvement. Vu sur la vraie main le 15.11.2026 : après un geste
        raté puis une mise en position de départ pas finie, la main est restée dite « en mouvement », et tout était
        refusé jusqu'au redémarrage. Donc, AVANT de refuser : un arrêt, puis au plus 0,5 s pour relire.
        - Les doigts changent encore de place après cela : REFUS (un autre programme commande la main ?).
        - Les doigts ne bougent plus : on continue, MÊME SI la main se dit encore « en marche » ou « en mise en position
          de départ ». CHOIX DE L'AUTEUR, à confirmer : d'après ce qui a été vu, cet état peut rester collé après une
          mise en position de départ bloquée, et seule une nouvelle mise en position de départ peut le défaire. Les
          doigts ont été MESURÉS immobiles, un arrêt vient d'être envoyé, et personne ne s'approche de la main.
        Un arrêt d'urgence et son verrou gardent leur comportement : ils ont été vérifiés avant (voir _libre)."""
        if self._arret_est_passe(generation):
            raise ActionImpossible("arrete", "un arrêt est passé : la main n'est pas préparée")
        self.kit.arreter_les_moteurs()
        debut, repere = time.monotonic(), None
        while True:
            bougent = self._les_doigts_bougent(frais=True)  # deux lectures neuves, à 0,06 s d'écart
            lu = self._lecture()
            ecoule = time.monotonic() - debut
            if not bougent and not any(etat in ETATS_QUI_BOUGENT for etat in lu.etats):
                return lu  # calmée
            if repere is None and ecoule >= REPERE_AVANT_DE_PREPARER_S:
                repere = lu.positions  # (avant 0,2 s, les doigts ont le droit de finir de s'arrêter)
            if ecoule >= ATTENTE_AVANT_DE_PREPARER_S:
                break
        # La main se dit encore en mouvement. « Immobiles » se MESURE sur la fin de l'attente (0,3 s environ), pas sur
        # deux lectures à 0,06 s : un doigt lent (400 positions par seconde) passerait sinon pour immobile. Pas de
        # repère (la main a répondu trop lentement) : dans le doute, refus.
        if bougent or repere is None or max(abs(a - b) for a, b in zip(repere, lu.positions)) > BOUGE:
            raise ActionImpossible("robot_occupe", "la main bouge encore après un ordre d'arrêt (le logiciel du fabricant "
                                   "est-il ouvert ?). Rien ne part.")
        return lu

    def _ralentir(self, vitesse_relative: Any) -> float:
        """La vitesse demandée pour le geste ne fait que RALENTIR. Pas un nombre, nulle, négative, trop petite : refus."""
        if isinstance(vitesse_relative, bool) or not isinstance(vitesse_relative, (int, float)) or not math.isfinite(vitesse_relative):
            raise ActionImpossible("hors_limites", "la vitesse demandée pour le geste n'est pas un nombre : rien ne part")
        if vitesse_relative < VITESSE_RELATIVE_MIN:
            raise ActionImpossible("hors_limites", f"la vitesse demandée pour le geste ({vitesse_relative}) est nulle, "
                                   f"négative ou trop petite : au plus lent, {VITESSE_RELATIVE_MIN} (un quart de notre "
                                   "vitesse lente). Rien ne part.")
        return min(float(vitesse_relative), 1.0)

    @staticmethod
    def _pause(valeur: Any, quoi: str) -> float:
        """Une pause en secondes : un nombre fini entre 0 et 3. Sinon : REFUS (rien ne part)."""
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur):
            raise ActionImpossible("hors_limites", f"{quoi} : « {valeur!r} » n'est pas un nombre : rien ne part")
        if not 0 <= valeur <= PAUSE_MAX_S:
            raise ActionImpossible("hors_limites", f"{quoi} : {valeur} est hors de nos limites (0 à {PAUSE_MAX_S:.0f} s) : rien ne part")
        return float(valeur)

    def _etape(self, brute: Any, defauts: dict, ou: str) -> _Etape:
        """Une étape du fichier, vérifiée : exactement les six doigts, des nombres ENTIERS dans nos limites."""
        if not isinstance(brute, dict) or "positions" not in brute or not set(brute) <= {"positions", "vitesse", "courant", "pause_s", "attendre"}:
            raise KeyError(f"{ou} : une étape s'écrit avec « positions » (et, si on veut, vitesse, courant, pause_s, attendre)")
        positions = brute["positions"]
        if not isinstance(positions, dict) or sorted(positions, key=str) != sorted(DOIGTS):
            raise KeyError(f"{ou} : il faut exactement les six doigts : " + ", ".join(DOIGTS))
        attendre = brute.get("attendre", True)
        if not isinstance(attendre, bool):
            raise KeyError(f"{ou} : « attendre » s'écrit true ou false")
        return _Etape(cibles=tuple(_entier(positions[doigt], f"{ou}, {doigt}", 0, POSITION_MAX) for doigt in DOIGTS),
                      vitesse=_entier(brute.get("vitesse", defauts.get("vitesse")), f"{ou}, la vitesse", 1, VITESSE_MAX),
                      courant=_entier(brute.get("courant", defauts.get("courant")), f"{ou}, le courant", 1, COURANT_MAX),
                      pause_s=self._pause(brute.get("pause_s", defauts.get("pause_s", 0)), f"{ou}, la pause"),
                      attendre=attendre)

    def _variantes(self, nom: str) -> dict[str | None, list[_Etape]]:
        """Les étapes d'un geste, lues dans gestes.yaml À CHAQUE FOIS et TOUTES vérifiées avant que rien ne parte.
        Rend une suite par tirage possible : {None: étapes} pour un geste sans hasard ; {« poing »: …, « victoire »: …}
        pour un geste qui a une étape « au_hasard ». Fichier illisible, geste absent, clé écrite deux fois, doigt en
        trop ou en moins, valeur hors limites ou pas entière, plus de 30 étapes : REFUS, rien ne part."""
        fichier = self._gestes.name
        try:
            lu = yaml.load(self._gestes.read_text(encoding="utf-8"), Loader=_SansCleEnDouble)  # sûr, et sans clé en double
            gestes, defauts = lu["gestes"], lu.get("defauts", {})
            if not isinstance(gestes, dict) or not isinstance(defauts, dict) or not set(defauts) <= {"vitesse", "courant", "pause_s"}:
                raise KeyError("il faut « gestes: » (et, si on veut, « defauts: » avec vitesse, courant, pause_s)")

            def etapes_de(geste: str) -> list[Any]:
                if geste not in gestes:
                    raise KeyError(f"le geste « {geste} » n'est pas dans le fichier")
                decrit = gestes[geste]
                if not isinstance(decrit, dict) or set(decrit) != {"etapes"} or not isinstance(decrit["etapes"], list) or not decrit["etapes"]:
                    raise KeyError(f"« {geste} » s'écrit avec « etapes: » et au moins une étape")
                return decrit["etapes"]

            avant, apres, hasard = [], [], None  # les étapes d'avant le tirage, celles d'après, et les suites possibles
            for numero, brute in enumerate(etapes_de(nom), 1):
                ou = f"{fichier}, {nom}, étape {numero}"
                if isinstance(brute, dict) and "au_hasard" in brute:
                    choix = brute["au_hasard"]
                    if (set(brute) != {"au_hasard"} or hasard is not None or not isinstance(choix, list) or not choix
                            or any(not isinstance(c, str) or c == nom or c == PREPARER for c in choix) or len(set(choix)) != len(choix)):
                        raise KeyError(f"{ou} : « au_hasard » s'écrit seul, une seule fois par geste, avec une liste de gestes du fichier")
                    hasard = {}
                    for candidat in choix:
                        suite = etapes_de(candidat)
                        if any(isinstance(e, dict) and "au_hasard" in e for e in suite):
                            raise KeyError(f"{ou} : « {candidat} » a lui-même une étape au hasard")
                        hasard[candidat] = [self._etape(e, defauts, f"{fichier}, {candidat}, étape {n}") for n, e in enumerate(suite, 1)]
                else:
                    (avant if hasard is None else apres).append(self._etape(brute, defauts, ou))
        except (OSError, UnicodeError, yaml.YAMLError, TypeError, KeyError, AttributeError) as erreur:
            raise ActionImpossible("geste_illisible", f"le fichier {fichier} est illisible pour « {nom} » "
                                   f"({type(erreur).__name__} : {erreur}) : rien ne part") from erreur
        variantes = {None: avant} if hasard is None else {tirage: avant + suite + apres for tirage, suite in hasard.items()}
        for tirage, etapes in variantes.items():
            if len(etapes) > ETAPES_MAX:
                raise ActionImpossible("hors_limites", f"{fichier}, « {nom} » : {len(etapes)} étapes, c'est plus que {ETAPES_MAX} : rien ne part")
            if not etapes[-1].attendre:
                raise ActionImpossible("geste_illisible", f"{fichier}, « {nom} » : la dernière étape doit attendre l'arrivée des doigts : rien ne part")
        return variantes

    @staticmethod
    def _duree_estimee(etapes: list[_Etape], positions: list[int]) -> float:
        """Une ESTIMATION de la durée d'un geste (pas une mesure) : pour chaque étape, le plus long chemin d'un doigt
        divisé par la vitesse, plus sa pause, plus 0,15 s pour voir l'arrivée et envoyer la suite."""
        total, ou = 0.0, list(positions)
        for etape in etapes:
            if etape.attendre:
                total += max(abs(cible - position) for cible, position in zip(etape.cibles, ou)) / etape.vitesse
                total += etape.pause_s + ENTRE_DEUX_ETAPES_S
            else:
                total += etape.pause_s + 0.1  # on n'attend pas l'arrivée : la suite part après la pause (au tic suivant)
            ou = list(etape.cibles)
        return total

    def _arreter_apres_coup(self, pourquoi: str) -> None:
        """Un ordre est peut-être parti alors qu'il ne fallait pas (un arrêt est passé, ou pas de réponse) : arrêter les
        moteurs. Si on ne peut pas, on le dit (jamais de silence), et ça reste dit."""
        try:
            self.kit.arreter_les_moteurs()
            if self._urgence:
                self.kit.couper_les_moteurs()  # un arrêt d'URGENCE est passé : sa coupure a pu arriver avant notre ordre
        except Exception as erreur:
            self._alerte = f"un ordre à la main est peut-être parti et n'a pas pu être arrêté ({pourquoi}) : arrêter la main"
            raise ActionImpossible("arret_non_confirme", f"{self._alerte} ({erreur}). Débrancher son alimentation.") from erreur

    def _arreter_au_mieux(self, pourquoi: str, couper: bool = False) -> None:
        """Après un REFUS de la main : arrêter (ou recouper) quand même, SANS jamais lever d'erreur, pour que le refus
        d'origine reste celui qu'on dit. Lu (manuel, lignes 1317 à 1327) : un lancement envoie plusieurs messages ; refusé
        en route, une partie a pu partir. Si même cet arrêt rate, c'est dit, et ça reste dit (alerte)."""
        try:
            if couper:
                self.kit.couper_les_moteurs()
                self._allumes_par_nous = False
            else:
                self.kit.arreter_les_moteurs()
        except Exception as erreur:
            self._alerte = f"{pourquoi}, et l'arrêt envoyé ensuite a raté ({erreur}) : arrêter la main"

    def _recouper(self, pourquoi: str) -> None:
        """Nous venons d'allumer les moteurs et la suite a raté : on les recoupe. Si même cela rate, c'est dit."""
        try:
            self.kit.couper_les_moteurs()
            self._allumes_par_nous = False
        except Exception as erreur:
            self._alerte = f"les moteurs de la main sont peut-être restés allumés ({pourquoi}) : débrancher son alimentation"
            raise ActionImpossible("arret_non_confirme", f"{self._alerte} ({erreur})") from erreur

    def _envoyer(self, ordres: list[tuple[int, int, int, int]], generation: int, debut: float) -> None:
        """Le SEUL endroit d'où part un mouvement de doigts : six réglages (rien ne bouge), puis « lancer »."""
        if time.monotonic() - debut > BUDGET_AVANT_ENVOI_S:
            raise ActionImpossible("trop_lent", "la main répond trop lentement : l'ordre n'est pas parti")
        for moteur, position, vitesse, courant in ordres:
            if self._arret_est_passe(generation):
                raise ActionImpossible("arrete", "un arrêt est passé : l'ordre à la main n'est pas parti")
            self.kit.donner_une_cible(moteur, position, vitesse, courant)
        if self._arret_est_passe(generation):
            raise ActionImpossible("arrete", "un arrêt est passé : l'ordre à la main n'est pas parti")
        try:
            self.kit.lancer_le_mouvement()
        except ActionImpossible as refus:
            if refus.code == "main_pas_preparee":
                self._depart_fait = False  # la MAIN dit que sa mise en position de départ n'est pas faite : on la croit
            else:
                # Tout autre refus : on ne croit pas que « rien n'est parti » (plusieurs messages par lancement).
                self._arreter_au_mieux("la main a refusé l'ordre de bouger")
            raise
        except Exception as erreur:  # pas de réponse : l'ordre a pu partir quand même
            self._arreter_apres_coup("l'ordre de bouger est resté sans réponse")
            raise ConnectionError(f"la main n'a pas répondu à l'ordre de bouger ({erreur}) : ses moteurs ont été arrêtés") from erreur
        if self._arret_est_passe(generation):  # un arrêt PENDANT l'envoi : on arrête de nouveau, après notre ordre
            self._arreter_apres_coup("un arrêt est passé pendant l'envoi")
            raise ActionImpossible("arrete", "un arrêt est passé pendant l'envoi : les moteurs de la main ont été arrêtés")

    def _lancer_le_depart(self, generation: int) -> None:
        """Le SEUL endroit d'où part la mise en position de départ (le « home » du fabricant). La main s'ouvre, à la
        vitesse et au courant DU FABRICANT (à vérifier) : main vide, personne ne la touche."""
        if self._arret_est_passe(generation):
            raise ActionImpossible("arrete", "un arrêt est passé : la mise en position de départ n'est pas partie")
        # D'ABORD (15.11.2026, après l'essai sur la vraie main) : écrire pour CHAQUE moteur notre vitesse et notre courant
        # les plus grands, pour qu'une petite limite laissée par un geste d'avant (150 pour mille ce jour-là) ne bloque
        # pas la mise en position de départ. C'est une HYPOTHÈSE, pas prouvée. Aucun mouvement n'est lancé ici.
        # « envoyer_les_reglages » (CHOIX DE L'AUTEUR, à confirmer) : lu, sans lui ces valeurs n'iraient à la main qu'au
        # mouvement suivant, donc après la mise en position de départ. Si la main REFUSE l'un des deux (on ne sait pas
        # s'ils sont permis avant une mise en position de départ), on continue quand même, et c'est dit dans l'état :
        # sur la vraie main, la mise en position de départ a marché sans eux.
        try:
            self.kit.regler_vitesse_et_courant(VITESSE_MAX, COURANT_MAX)
            self.kit.envoyer_les_reglages()
            self._remarque = None
        except ActionImpossible as refus:
            self._remarque = f"la main a refusé nos réglages de vitesse et de courant avant sa mise en position de départ ({refus})"
        if self._arret_est_passe(generation):
            raise ActionImpossible("arrete", "un arrêt est passé : la mise en position de départ n'est pas partie")
        try:
            self.kit.mise_en_position_de_depart()
        except ActionImpossible as refus:
            if refus.code != "main_pas_preparee":  # refusée : on arrête quand même, sans masquer le refus
                self._arreter_au_mieux("la main a refusé la mise en position de départ")
            raise
        except Exception as erreur:
            self._arreter_apres_coup("la mise en position de départ est restée sans réponse")
            raise ConnectionError(f"la main n'a pas répondu à la mise en position de départ ({erreur}) : ses moteurs ont été arrêtés") from erreur
        if self._arret_est_passe(generation):
            self._arreter_apres_coup("un arrêt est passé pendant la mise en position de départ")
            raise ActionImpossible("arrete", "un arrêt est passé : la mise en position de départ a été arrêtée")

    def _preparer(self, generation: int, debut: float) -> None:
        """« preparer_la_main » : le seul geste permis sur une main pas préparée, et le SEUL chemin qui allume les moteurs.
        Le gardien a déjà dit oui. Moteurs coupés : on les allume, et tic() lance la suite 1 s plus tard."""
        self._libre()
        lu = self._lecture()
        self._sans_alarme(lu)
        bouge = any(etat in ETATS_QUI_BOUGENT for etat in lu.etats) or self._les_doigts_bougent(lu.positions)
        if time.monotonic() - debut > BUDGET_AVANT_ENVOI_S:
            raise ActionImpossible("trop_lent", "la main répond trop lentement : l'ordre n'est pas parti")
        if bouge:  # avant de refuser : un arrêt, au plus 0,5 s, et on relit (voir _arreter_avant_de_preparer)
            lu = self._arreter_avant_de_preparer(generation)
            self._sans_alarme(lu)
        self._depart_fait = False  # tant que la mise en position de départ n'est pas finie ET vérifiée
        if self._arret_est_passe(generation):
            raise ActionImpossible("arrete", "un arrêt est passé : la main n'est pas préparée")
        if all(lu.allumes):
            self._lancer_le_depart(generation)
            phase = "depart"
        else:
            self._allumes_par_nous = True  # noté AVANT l'ordre : il peut arriver même si sa réponse se perd
            try:
                self.kit.allumer_les_moteurs()
            except ActionImpossible:
                # La main a dit non. On ne croit pas pour autant que « rien n'est allumé » : on recoupe, au mieux,
                # sans masquer le refus (relecture du 15.11.2026).
                self._arreter_au_mieux("la main a refusé d'allumer ses moteurs", couper=True)
                raise
            except Exception as erreur:  # pas de réponse : l'ordre a pu arriver quand même
                self._recouper("l'ordre d'allumer est resté sans réponse")
                raise ConnectionError(f"la main n'a pas répondu à l'ordre d'allumer ses moteurs ({erreur}) : ils ont été recoupés") from erreur
            if self._arret_est_passe(generation):
                self._recouper("un arrêt est passé pendant l'allumage")
                raise ActionImpossible("arrete", "un arrêt est passé pendant l'allumage : les moteurs ont été recoupés")
            phase = "allumage"
        self._echec = None
        self._geste = _Geste(generation=generation, nom=PREPARER, phase=phase, debut=time.monotonic(),
                             depart=lu.positions, cibles=[0] * NOMBRE_DE_MOTEURS)

    def geste(self, nom: str, vitesse_relative: float) -> None:
        # PROPOSITION, à vérifier sur la vraie main. La vitesse demandée ne fait que RALENTIR (0,5 = deux fois plus lent).
        generation, debut = self._generation, time.monotonic()  # lus AVANT tout : un arrêt qui passe ensuite gagne
        if nom not in GESTES:
            raise ActionImpossible("geste_inconnu", f"la main ne connaît pas le geste « {nom} » (connus : {list(GESTES)})")
        relative = self._ralentir(vitesse_relative)
        if nom == PREPARER:  # la mise en position de départ va à la vitesse du fabricant : la nôtre n'y change rien
            return self._preparer(generation, debut)
        # TOUT le fichier est lu et vérifié ici, avant toute lecture de la main et avant que rien ne parte.
        variantes = {tirage: [replace(etape, vitesse=max(1, int(etape.vitesse * relative))) for etape in etapes]  # vers le bas
                     for tirage, etapes in self._variantes(nom).items()}
        for etapes in variantes.values():  # les ordres de TOUTES les étapes sont vérifiés contre nos limites
            for etape in etapes:
                for moteur, cible in enumerate(etape.cibles, 1):
                    ordre_permis(moteur, cible, etape.vitesse, etape.courant)
        self._libre()
        lu = self._lecture()
        if not all(lu.allumes) or not self._depart_fait:
            self._depart_fait = self._depart_fait and all(lu.allumes)
            raise ActionImpossible("main_pas_preparee", "la main n'est pas préparée (moteurs coupés, ou mise en position "
                                   "de départ pas faite par notre système). Lui demander d'abord de se préparer "
                                   "(« prépare la main ») : main vide, personne ne la touche.")
        self._calme(lu)
        for etapes in variantes.values():  # quel que soit le tirage
            duree = self._duree_estimee(etapes, lu.positions)
            if duree > DUREE_MAX_GESTE_S:
                raise ActionImpossible("hors_limites", f"« {nom} » durerait environ {duree:.0f} s à cette vitesse : plus de "
                                       f"{DUREE_MAX_GESTE_S:.0f} s, c'est refusé (l'adaptateur arrête toute action après 30 s). Rien ne part.")
        tirage = None
        if None not in variantes:  # une étape « au_hasard » : la liaison tire UNE des suites possibles
            tirage = self.tirer_au_hasard(list(variantes))
            if tirage not in variantes:
                raise ActionImpossible("geste_illisible", f"le tirage au hasard a rendu « {tirage!r} », qui n'est pas dans la liste : rien ne part")
        etapes = variantes[tirage]
        premiere = etapes[0]
        self._envoyer([ordre_permis(moteur, cible, premiere.vitesse, premiere.courant) for moteur, cible in enumerate(premiere.cibles, 1)],
                      generation, debut)
        maintenant = time.monotonic()
        if tirage is not None:
            self._dernier_tirage = tirage  # dit dans lire_etat() : on peut lire après coup ce que la main a tiré
        duree = max(abs(cible - position) for cible, position in zip(premiere.cibles, lu.positions)) / premiere.vitesse
        self._echec = None
        self._geste = _Geste(generation=generation, nom=nom, phase="mouvement", debut=maintenant, depart=lu.positions,
                             cibles=list(premiere.cibles), vitesse=premiere.vitesse, pause_s=premiere.pause_s,
                             attendre=premiere.attendre, limite=maintenant + duree * MARGE_DUREE + ATTENTE_EN_PLUS_S,
                             origine=lu.positions, file=etapes[1:])

    def _etape_suivante(self, geste: _Geste, lu: _Lecture) -> None:
        """L'étape en cours est finie : envoyer la suivante, ou dire le geste fini s'il n'en reste pas. Dans ce même tic,
        on vient de vérifier qu'il n'y a pas d'alarme et que les moteurs sont allumés ; _envoyer() vérifie qu'aucun arrêt
        n'est passé (avant, pendant, après). Tout refus ici fait dire le geste RATÉ (voir tic)."""
        if not geste.file:
            if geste.generation == self._generation:
                self._geste = None  # fini, et vérifié
            return
        etape = geste.file[0]
        ordres = [ordre_permis(moteur, cible, etape.vitesse, etape.courant) for moteur, cible in enumerate(etape.cibles, 1)]
        self._envoyer(ordres, geste.generation, time.monotonic())
        maintenant = time.monotonic()
        duree = max(abs(cible - position) for cible, position in zip(etape.cibles, lu.positions)) / etape.vitesse
        geste.file = geste.file[1:]
        geste.phase, geste.cibles, geste.depart, geste.vitesse = "mouvement", list(etape.cibles), lu.positions, etape.vitesse
        geste.pause_s, geste.attendre = etape.pause_s, etape.attendre
        geste.debut, geste.repere = maintenant, None
        geste.limite = maintenant + duree * MARGE_DUREE + ATTENTE_EN_PLUS_S

    @staticmethod
    def _immobile(geste: _Geste, maintenant: float, positions: list[int]) -> bool:
        """Les doigts n'ont plus bougé (à 30 positions près) depuis 0,3 s."""
        repere = geste.repere
        if repere is None or max(abs(a - b) for a, b in zip(repere[1], positions)) > BOUGE:
            geste.repere = (maintenant, positions)
            return False
        return maintenant - repere[0] >= IMMOBILE_S

    def tic(self) -> None:
        """Toutes les 0,1 s : suivre le geste en route, et ne le dire « fini » que quand c'est VÉRIFIÉ."""
        geste = self._geste
        if geste is None or geste.generation != self._generation:
            return
        try:
            self._suivre_le_geste(geste)
        except Exception as erreur:  # le geste s'arrête là, et il est dit RATÉ à celui qui attend sa fin
            if isinstance(erreur, ActionImpossible) and erreur.code == "arret_non_confirme":
                self._alerte = str(erreur)
            self._rater(geste, f"le geste « {geste.nom} » de la main s'est arrêté en route : {erreur}")

    def _suivre_le_geste(self, geste: _Geste) -> None:
        maintenant = time.monotonic()
        lu = self._lecture()
        self._derniere = (maintenant, lu.positions)
        dit = self._ce_que_dit_la_main(lu)
        if dit:
            raise ActionImpossible("alarme", " ; ".join(dit))
        ecoule = maintenant - geste.debut
        if geste.phase == "allumage":
            if ecoule < ATTENTE_APRES_ALLUMAGE_S:  # lu : le fabricant attend 1 s après avoir allumé
                return
            if not all(lu.allumes):
                raise ActionImpossible("moteurs_coupes", "les moteurs de la main ne se sont pas tous allumés")
            saut = max(abs(a - b) for a, b in zip(geste.depart, lu.positions))
            if saut > SAUT_MAX:
                raise ActionImpossible("main_a_bouge", f"un doigt a bougé tout seul de {saut} positions quand les moteurs "
                                       "se sont allumés : ils sont recoupés. Ne pas réessayer sans un humain.")
            self._lancer_le_depart(geste.generation)
            geste.phase, geste.debut, geste.repere = "depart", time.monotonic(), None
            return
        if not all(lu.allumes):
            self._depart_fait = False
            raise ActionImpossible("moteurs_coupes", "les moteurs de la main ont été coupés pendant le geste")
        immobile = self._immobile(geste, maintenant, lu.positions)
        if geste.phase == "depart":
            return self._suivre_le_depart(geste, lu, ecoule, immobile)
        if geste.phase == "pause":  # l'étape est arrivée et vérifiée : on attend la fin de sa pause, puis la suite
            if maintenant >= geste.fin_de_pause:
                self._etape_suivante(geste, lu)
            return
        # ---- un mouvement des doigts
        if ecoule >= FENETRE_VITESSE_S:
            for doigt, depart, position in zip(DOIGTS, geste.depart, lu.positions):
                vitesse = abs(position - depart) / ecoule
                if vitesse > SURVITESSE * geste.vitesse:
                    raise ActionImpossible("trop_vite", f"{doigt} va à {vitesse:.0f} positions par seconde, plus de deux "
                                           f"fois la vitesse demandée ({geste.vitesse}) : la main ne tient pas notre vitesse")
        if not geste.attendre:
            # Une étape qui n'attend pas l'arrivée (une « vague » : les doigts partent l'un après l'autre) : la suite part
            # après la pause. L'arrivée de tous les doigts est vérifiée par la prochaine étape qui attend (la dernière attend toujours).
            if ecoule >= geste.pause_s:
                self._etape_suivante(geste, lu)
            return
        atteints = self._oui_non(self.kit.cibles_atteintes(), "ses arrivées")
        couples = self._oui_non(self.kit.couples_atteints(), "ses couples")
        restent = []
        origines = geste.origine or geste.depart
        for doigt, depart, origine, position, cible, atteint, couple in zip(DOIGTS, geste.depart, origines, lu.positions,
                                                                          geste.cibles, atteints, couples):
            # « A avancé » se compte depuis le départ de l'étape OU depuis le début du geste : un doigt arrêté sur le
            # doudou à la première étape de « attraper » y est encore à la deuxième, sans avoir bougé entre les deux.
            depart = min(depart, origine)
            deja_la = abs(geste.depart[DOIGTS.index(doigt)] - cible) <= TOLERANCE  # ce doigt n'avait pas à bouger pour cette étape
            if abs(position - cible) <= TOLERANCE and (atteint or deja_la):
                continue  # arrivé : la position lue le confirme, ET la main le dit (ou il y était déjà : pas un échec)
            # Pour TOUS les gestes (15.11.2026) : un doigt arrêté AVANT sa cible parce qu'il touche l'objet compte comme
            # arrivé, s'il dit « couple atteint », ne bouge plus, ET a avancé de plus de 300 positions depuis son départ.
            sur_l_objet = couple and immobile and ecoule >= ATTENTE_APRES_LANCEMENT_S
            if sur_l_objet and position <= cible + TOLERANCE and position - depart > AVANCE_MIN:
                continue
            if sur_l_objet and position - depart <= AVANCE_MIN:
                # La main dit « couple atteint », mais ce doigt n'a pas quitté sa place : il n'a rien pris. Pas « fini ».
                restent.append(f"{doigt} (dit « couple atteint » sans avoir avancé, à {abs(position - cible)} positions de sa cible)")
            else:
                restent.append(f"{doigt} (à {abs(position - cible)} positions de sa cible)")
        if not restent:
            if geste.pause_s > 0:
                geste.phase, geste.fin_de_pause = "pause", maintenant + geste.pause_s
                return
            return self._etape_suivante(geste, lu)
        if maintenant > geste.limite:
            raise ActionImpossible("pas_arrivee", "pas arrivé à temps : " + ", ".join(restent))

    def _suivre_le_depart(self, geste: _Geste, lu: _Lecture, ecoule: float, immobile: bool) -> None:
        """La mise en position de départ est finie quand : la main l'a dite « en cours » puis ne le dit plus (ou, si elle
        ne le dit jamais, après les 5 s que le fabricant attend), plus rien ne bouge, et chaque doigt est à 0."""
        en_depart = any(etat == EN_DEPART for etat in lu.etats)
        geste.vu_en_depart = geste.vu_en_depart or en_depart
        annoncee_finie = geste.vu_en_depart and not en_depart
        attendue = not geste.vu_en_depart and ecoule >= ATTENTE_DEPART_S
        if (annoncee_finie or attendue) and immobile and not any(etat in ETATS_QUI_BOUGENT for etat in lu.etats):
            loin = [f"{doigt} (à {abs(position)})" for doigt, position in zip(DOIGTS, lu.positions) if abs(position) > TOLERANCE]
            if loin:
                raise ActionImpossible("pas_arrivee", "après la mise en position de départ, ces doigts ne sont pas à 0 : "
                                       + ", ".join(loin))
            if not self._arret_est_passe(geste.generation):
                self._depart_fait = True  # la main est préparée : les autres gestes sont permis
                self._geste = None
            return
        if ecoule > DELAI_DEPART_S:
            raise ActionImpossible("pas_arrivee", f"la mise en position de départ n'est pas finie après {DELAI_DEPART_S:.0f} s")

    # ---------------------------------------------------------------- pas branché, exprès
    def saisir(self, objet: str, force_n: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : la prise demande une FORCE en newtons, et la main ne connaît
        # qu'un COURANT en pour mille. On ne sait pas passer de l'un à l'autre : pas de saisir tant que ce n'est pas mesuré.
        raise ABrancher("saisir", "relier une force en newtons au courant des moteurs de la main (à mesurer)")

    def poser(self, lieu: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : va avec saisir. En attendant : le geste « ouvrir_la_main ».
        raise ABrancher("poser", "va avec saisir ; en attendant, le geste « ouvrir_la_main »")
