"""ÉBAUCHE de liaison vers un Reachy Mini (Pollen Robotics / Hugging Face), par les adresses web de son programme de fond.

NON TESTÉ SUR VRAI ROBOT. Essayée avec une doublure (doublure.py) et, le 15.11.2026, avec le programme du fabricant
en mode simulé (« --mockup-sim », version 1.14.0) : dans les deux cas, TESTÉ SUR FAUX ROBOT.
Le robot est avec l'équipe (dit par Hiba le 14.11.2026) ; rien ne lui a été envoyé. Son kit est installé À PART
(~/reachy_env, avec l'accord de Hiba le 15.11.2026) : rien du fabricant n'entre dans notre projet.

Comment on lui parle : le Reachy Mini a un « programme de fond » (son daemon : un programme qui tourne à côté et qui
parle aux moteurs). Ce programme répond à des adresses web simples, sur l'ordinateur même. Notre liaison n'importe donc
PAS le kit du fabricant : elle envoie de petites demandes web. Le kit du fabricant s'installe à part, dans son propre
espace (sa doc dit Python 3.10 à 3.12 ; avec notre 3.13 : à vérifier). Feu orange : taille, licences, « oui » de Hiba.
CETTE ÉBAUCHE VAUT POUR UN LITE (le programme de fond tourne sur notre ordinateur). Sur un Wireless, il tourne dans
le robot, sur le port 8000, déjà lancé : il faut le demander exprès au client (hors_de_cet_ordinateur=True).

Ce que cette ébauche sait faire, et rien d'autre (demande de Hiba, 14.11.2026) :
    se connecter, dire son état  → des LECTURES (GET) : /api/daemon/status, /api/move/running, /api/state/full
    arrêt normal                 → PROPOSITION : arrêter chaque mouvement en cours (POST /api/move/stop), puis vérifier que la tête ne bouge plus
    arrêt d'urgence logiciel     → PROPOSITION : couper les moteurs D'ABORD (POST /api/motors/set_mode/disabled), puis arrêter les mouvements
    réarmer                      → rien n'est envoyé au robot : rallumer les moteurs est une étape à part (à décider)
    regarder (15.11.2026)        → tourner LENTEMENT la tête vers une direction du fichier directions.yaml (POST /api/move/goto)
    geste « oui », « non »       → de petits mouvements de tête, envoyés un par un (le suivant part quand le précédent est fini
                                   ET que la tête est arrivée). La tête doit déjà être levée et droite.
    geste « lever_la_tete »      → NOTRE réveil, lent : allume les moteurs puis monte la tête droite, en 6 s. Le « réveil »
                                   du fabricant (rapide, avec un son) n'est jamais utilisé.
    geste « coucher_la_tete »    → repose lentement la tête sur son socle, en 6 s, puis coupe les moteurs.
Montrer et la voix restent « À BRANCHER » (la voix reste au Mac : brique 4).
Les arrêts sont des PROPOSITIONS : le choix se fait avec le responsable sécurité, avant tout essai sur le vrai robot.

LU EN LIGNE, le 14.11.2026 (rien installé ; dépôt github.com/pollen-robotics/reachy_mini, branche main, licence Apache-2.0) :
- src/reachy_mini/daemon/app/main.py : les adresses web commencent par « /api » ; le programme de fond écoute sur le
  port 8000 par défaut (« --fastapi-port ») — C'EST LE PORT DE NOTRE ÉCRAN : il faut lui en donner un autre ;
  il n'écoute que sur l'ordinateur même (127.0.0.1) pour un Lite, mais sur TOUT LE RÉSEAU pour un Wireless, et ses
  adresses n'ont pas de mot de passe (« the unauthenticated API ») ;
  AU DÉMARRAGE IL RÉVEILLE LE ROBOT (la tête bouge, un son est joué) et À L'ARRÊT IL L'ENDORT (la tête bouge) :
  « --no-wake-up-on-start » et « --no-goto-sleep-on-stop » l'empêchent ; « --mockup-sim » : un faux robot sans MuJoCo.
- routers/daemon.py : GET /api/daemon/status rend state (« running »…), error, backend_status (ready,
  motor_control_mode, last_alive, error).
- routers/state.py : GET /api/state/full rend control_mode, head_joints (7 nombres), body_yaw, antennas_position.
- routers/move.py : GET /api/move/running rend la liste des mouvements en cours (chacun avec son « uuid ») ;
  POST /api/move/stop avec {"uuid": …} : « Stop a running move task by cancelling it » ;
  POST /api/move/goto (un mouvement avec une durée) ; POST /api/move/play/wake_up et /play/goto_sleep.
- routers/motors.py : POST /api/motors/set_mode/{mode}, mode = enabled, disabled ou gravity_compensation.
- docs/source/SDK/core-concept.md : « enable_motors : Stiff. Holds position. » ; « disable_motors : Limp. No power. » ;
  limites : tête ±40° (haut-bas, côté), ±180° (rotation), corps ±160°, 65° au plus entre la tête et le corps.

VU SUR LE PROGRAMME DU FABRICANT EN MODE SIMULÉ, le 15.11.2026 (version 1.14.0 ; un faux robot, pas le vrai) :
- un ordre de tête envoyé PENDANT qu'un autre mouvement joue est PERDU SANS LE DIRE (réponse 200, avec un « uuid ») :
  la liaison refuse donc tout ordre de tête tant qu'un mouvement est en cours ;
- un mouvement arrêté par /api/move/stop s'arrête à peu près sur place (la tête glisse encore un instant) ;
- une cible hors limites n'est pas refusée : elle est ramenée à environ 67° (côté) et 34° (haut-bas), et LE CORPS
  TOURNE pour suivre. La liaison refuse donc elle-même toute cible au-delà de ses petites limites ;
- une durée de 0 seconde est acceptée : la liaison n'envoie jamais moins de DUREE_MIN_S ;
- moteurs coupés, le faux robot du fabricant « bouge » quand même : cela ne dit RIEN du vrai robot ;
- la réponse à /api/daemon/status n'a pas « ready » ni « last_alive » dans cette version.

À VÉRIFIER (pas lu, ou pas essayé) — la liste complète est dans fiches/reachy_mini.md :
- que fait la tête quand on coupe les moteurs (elle s'affaisse ?) et quand on les rallume (saute-t-elle vers sa
  dernière cible ?) : c'est pour cela que rearmer() ne rallume rien ;
- sur le VRAI robot : un mouvement arrêté par /api/move/stop s'arrête-t-il sur place ? ; un mouvement envoyé par
  « set_target » (sans durée) n'apparaît pas dans /api/move/running : il ne serait ni vu ni arrêté ;
- le SENS des angles (un lacet positif tourne-t-il la tête vers sa gauche ? un tangage positif la baisse-t-il ?) ;
- les vitesses choisies (VITESSE_TETE_RAD_S, VITESSE_GESTE_RAD_S) sont-elles assez lentes près d'une personne ? ;
- dans quel mode sont les moteurs quand le programme de fond démarre SANS réveil ? S'ils sont coupés, la liaison
  refuse de bouger, et les rallumer est une étape à part, faite par un humain ;
- le sens de last_alive ; le seuil BOUGE_RAD (choix de l'équipe) ; le temps de réponse en Wi-Fi (version Wireless) ;
- la version du programme de fond installée a-t-elle bien ces adresses ?
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide

ADRESSE_PAR_DEFAUT = "http://127.0.0.1:8002"  # choix de l'équipe : PAS le 8000 (notre écran), et l'ordinateur même seulement
ICI_SEULEMENT = ("127.0.0.1", "localhost", "::1")  # sans option exprès, le client ne parle qu'à cet ordinateur
ADRESSE_DANS_L_ENVIRONNEMENT = "REACHY_MINI_ADRESSE"  # version Wireless : l'adresse du robot, donnée par un humain
RESEAU_PRIVE_DIT = "REACHY_MINI_RESEAU_PRIVE"  # « oui » = un humain dit que le réseau est privé (partage de connexion)
DELAI_LECTURE_S = 0.2  # choix de l'équipe : lire_etat fait au plus 4 lectures ; 4 × 0,2 s + la pause restent sous 1 s
DELAI_ORDRE_S = 0.5  # choix de l'équipe : un arrêt qui n'a pas répondu en 0,5 s est un arrêt non confirmé
DELAI_ORDRE_TETE_S = 0.3  # un ordre de tête qui n'a pas répondu en 0,3 s est abandonné (et on tente de tout annuler)
# Si les vérifications ont déjà pris plus de 0,4 s, l'ordre de tête ne part pas. Le pire temps de regarder(), de geste()
# et d'un tic qui envoie est alors 0,4 + 0,3 (l'ordre) + 0,2 (relire la liste) = 0,9 s : sous la seconde de l'adaptateur.
BUDGET_AVANT_ENVOI_S = 0.4
GUET_APRES_UN_ORDRE_SANS_REPONSE_S = 1.5  # un ordre resté sans réponse peut arriver en retard : on guette, et on annule
ETAT_DU_FOND = "/api/daemon/status"  # lu : une lecture ; répond même si le robot n'est pas démarré
MOUVEMENTS_EN_COURS = "/api/move/running"  # lu : une lecture ; SEULEMENT les mouvements lancés par les adresses web
POSITIONS = "/api/state/full?with_head_joints=true&with_head_pose=false"  # lu : une lecture (head_joints est absent par défaut)
ARRETER_UN_MOUVEMENT = "/api/move/stop"  # lu : « Stop a running move task by cancelling it »
COUPER_LES_MOTEURS = "/api/motors/set_mode/disabled"  # lu : « Limp. No power. »
BOUGER_LA_TETE = "/api/move/goto"  # lu : un mouvement avec une DURÉE (longue durée = mouvement lent)
# Lu (daemon/backend/robot/backend.py, enable_motors) : « Enable motor torque; pin all targets to present pose first to
# avoid a snap » : les moteurs tiennent la position du MOMENT, la tête ne saute pas. Pas vérifié sur le vrai robot.
# Envoyé à UN seul endroit : au début du geste « lever_la_tete », lui-même accordé par le gardien (donc par un humain).
ALLUMER_LES_MOTEURS = "/api/motors/set_mode/enabled"
POSE_DE_LA_TETE = "/api/state/full?with_head_pose=true&with_head_joints=false"  # lu : une lecture ; angles en radians
# Les SEULES demandes que le client accepte d'envoyer. Tout le reste est refusé avant de partir.
PERMIS = frozenset({("GET", ETAT_DU_FOND), ("GET", MOUVEMENTS_EN_COURS), ("GET", "/api/state/full"),
                    ("POST", ARRETER_UN_MOUVEMENT), ("POST", COUPER_LES_MOTEURS), ("POST", BOUGER_LA_TETE),
                    ("POST", ALLUMER_LES_MOTEURS)})
EN_MARCHE = "running"  # lu : l'état du programme de fond quand tout va bien
MODES_CALMES = ("enabled", "disabled")  # lu ; « gravity_compensation » = on peut bouger la tête à la main : doute
BOUGE_RAD = 0.003  # choix de l'équipe, à vérifier : au-dessus, entre deux lectures, une articulation est dite en mouvement
ENTRE_DEUX_LECTURES_S = 0.06
LECTURE_ENCORE_FRAICHE_S = 1.0  # une lecture gardée en mémoire depuis moins d'1 s sert de point de comparaison
ATTENTE_APRES_ARRET_S = 0.6  # vu sur le simulateur du fabricant : après un arrêt, la tête glisse encore un instant
# L'attente « la tête glisse encore » s'arrête 0,85 s après le début de l'arrêt. Ce n'est PAS une promesse sur tout
# l'arrêt : avec un programme de fond lent, chaque annulation peut prendre 0,5 s de plus (mesuré par le relecteur :
# 1,3 s avec un mouvement). L'adaptateur, lui, coupe à 1 s et passe à l'arrêt d'urgence : c'est le sens sûr.
BUDGET_ARRET_S = 0.85

# ---- Bouger la tête. TOUS ces chiffres sont des choix de l'équipe, petits exprès, à vérifier sur le vrai robot.
MOTEURS_ALLUMES = "enabled"
DIRECTIONS = Path(__file__).with_name("directions.yaml")  # les directions que la tête connaît, réglées par l'équipe
LACET_MAX_RAD = math.radians(40.0)  # côté. Lu : 65° au plus entre la tête et le corps ; au-delà le corps tourne (vu)
TANGAGE_MAX_RAD = math.radians(20.0)  # haut-bas. Lu : ±40°
MARGE_RAD = math.radians(2.0)  # une tête lue à 41° n'empêche pas un geste ; au-delà, on refuse
# Ce sont des vitesses MOYENNES. Le fabricant accélère puis ralentit (« minjerk ») : la vitesse de POINTE vaut 1,875 fois
# la moyenne (calculé sur sa formule, et mesuré sur son faux robot le 15.11.2026) : 37,5°/s pour regarder, 46,9°/s pour
# les grands morceaux du « non », 18,75°/s pour le « oui ». Pas mesuré sur le vrai robot.
VITESSE_TETE_RAD_S = math.radians(20.0)  # vitesse moyenne pour regarder : 20° par seconde
VITESSE_GESTE_RAD_S = math.radians(25.0)  # vitesse moyenne d'un « oui » ou d'un « non » à pleine vitesse
# Une vitesse demandée sous 0,25 est jouée à 0,25 (donc un peu plus vite que demandé, mais toujours au quart de
# notre vitesse lente) : au-dessous, un geste durerait plus que les 30 s que l'adaptateur lui laisse.
VITESSE_RELATIVE_MIN = 0.25
ECART_MIN_D_UN_GESTE_RAD = math.radians(2.0)  # un geste qui ne peut presque pas bouger (tête au bord) est refusé
DUREE_MIN_S, DUREE_MAX_S = 1.0, 8.0  # jamais moins d'1 s (vu : le fabricant accepte 0 s) ; plus de 8 s = trop loin : refus
TOLERANCE_ARRIVEE_RAD = math.radians(4.0)  # à la fin d'un mouvement, la tête doit être à moins de 4° de sa cible
# « Tête en place » : levée, droite, corps de face. Sinon « regarder », « oui » et « non » sont refusés : il faut d'abord
# le geste « lever_la_tete » (notre réveil lent, accordé par le gardien).
ROULIS_MAX_RAD, DECALAGE_MAX_M, CORPS_MAX_RAD = math.radians(5.0), 0.02, math.radians(5.0)
ECHEC_VISIBLE_S = 1.5  # un mouvement raté reste dit « echec_action » pendant 1,5 s, et aucun ordre ne part pendant ce temps
# Les gestes : une suite de petits écarts (lacet, tangage) en degrés, autour de la position de départ ; on y revient à la fin.
GESTES = {"non": ((15.0, 0.0), (-15.0, 0.0), (15.0, 0.0), (0.0, 0.0)),
          "oui": ((0.0, 10.0), (0.0, 0.0), (0.0, 10.0), (0.0, 0.0))}
# ---- Se lever, se coucher (15.11.2026, demande de Hiba : tout par notre cerveau, sans l'interface du fabricant).
# Le « réveil » du fabricant n'est PAS utilisé : lu dans son code (abstract.py, wake_up), il finit par un mouvement de
# 20° en 0,2 s, avec un son. Trop rapide pour notre projet. À la place, deux gestes à nous, d'un seul mouvement LENT :
# « lever_la_tete » (allume les moteurs, puis monte la tête droite) et « coucher_la_tete » (la repose sur son socle).
# Lu : la pose levée est « INIT_HEAD_POSE » (tout à zéro) et les antennes « INIT_ANTENNAS_JOINT_POSITIONS ».
# Lu : la pose couchée est « SLEEP_HEAD_POSE » du fabricant (abstract.py : tangage 24,4°, 4,4 cm plus bas), celle où
# son propre coucher s'arrête AVANT de couper les moteurs ; la tête finit de se poser quand ils sont coupés. Relecture
# du 15.11.2026 : viser plus bas (la pose de repos complète) risquait de forcer contre le socle, moteurs allumés.
# Antennes couchées lues dans « SLEEP_ANTENNAS_JOINT_POSITIONS ». À vérifier sur le robot.
# Comme le fabricant, « coucher_la_tete » COUPE les moteurs à la fin (la tête est posée : rien ne tombe).
POSTURES = {
    "lever_la_tete": {"head_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                      "antennas": [-0.1745, 0.1745]},
    "coucher_la_tete": {"head_pose": {"x": -0.021, "y": 0.001, "z": -0.044, "roll": 0.0, "pitch": 0.426, "yaw": 0.0},
                        "antennas": [-3.05, 3.05]},
}
# 6 s pour monter ou descendre : la tête fait 31° et 5 cm (environ 5° par seconde en moyenne, 10 en pointe) ; les
# antennes font 165° (27° par seconde en moyenne, 52 en pointe : ce sont deux tiges légères). Choix de l'équipe, à vérifier.
DUREE_POSTURE_S = 6.0
VITESSE_RELATIVE_MIN_POSTURE = 0.5  # au plus lent : 12 s (l'adaptateur et le test de conformité attendent 20 s au plus)
TOLERANCE_HAUTEUR_M = 0.015  # à la fin, la tête doit être à moins de 1,5 cm de la hauteur voulue
# Après avoir rallumé les moteurs, la tête ne doit PAS bouger (lu : le fabricant cale les cibles sur la position du
# moment ; mais le relecteur a lu une course possible dans son code, où la tête repartirait vers une ancienne cible).
# Donc : on attend 0,12 s, on relit, et si la tête a bougé de plus de 2° ou de 5 mm, on recoupe et on le dit.
ATTENTE_APRES_ALLUMAGE_S, SAUT_MAX_RAD, SAUT_MAX_M = 0.12, math.radians(2.0), 0.005
# Le trajet d'une antenne est de 2,88 rad (165°) depuis sa place levée, 3,05 rad au plus si elle est toute droite.
# Tournée à la main de l'autre côté, elle en ferait 3,22 : refus.
TRAJET_MAX_ANTENNE_RAD = 3.15


class _JamaisDeRedirection(urllib.request.HTTPRedirectHandler):
    """Une redirection enverrait la demande à une autre adresse : on la refuse (elle devient une erreur)."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class ClientDuProgrammeDeFond:
    """Le « kit » du vrai robot : un petit client web vers le programme de fond du Reachy Mini. Rien d'autre.
    Il ne passe par aucun relais (proxy) du système, ne suit aucune redirection, et n'envoie que les demandes de PERMIS."""

    def __init__(self, adresse: str = ADRESSE_PAR_DEFAUT, hors_de_cet_ordinateur: bool = False) -> None:
        morceaux = urllib.parse.urlsplit(adresse)
        if morceaux.scheme not in ("http", "https") or not morceaux.hostname:
            raise ValueError(f"adresse du Reachy Mini invalide : « {adresse} » (attendu : http://…)")
        if morceaux.hostname not in ICI_SEULEMENT and not hors_de_cet_ordinateur:
            raise ValueError(f"« {adresse} » n'est pas sur cet ordinateur : il faut le demander exprès "
                             "(version Wireless : ses adresses n'ont pas de mot de passe, réseau privé seulement)")
        if morceaux.hostname not in ICI_SEULEMENT and not self._adresse_privee(morceaux.hostname):
            raise ValueError(f"« {adresse} » n'est pas une adresse de réseau privé (attendu : 192.168.…, 10.…, 172.16.… "
                             "ou un nom en « .local ») : refus, les adresses du robot n'ont pas de mot de passe")
        self.adresse = adresse.rstrip("/")
        self._ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}), _JamaisDeRedirection())

    @staticmethod
    def _adresse_privee(hote: str) -> bool:
        """Une adresse de réseau privé (ou un nom « .local », donné par le réseau lui-même). Jamais une adresse d'Internet."""
        if hote.endswith(".local"):
            return True
        try:
            adresse = ipaddress.ip_address(hote)
        except ValueError:
            return False  # un nom d'Internet (exemple.com) : refus
        return adresse.is_private and not adresse.is_loopback or adresse.is_link_local

    def _demander(self, verbe: str, chemin: str, corps: dict | None, delai_s: float) -> Any:
        if (verbe, chemin.split("?")[0]) not in PERMIS:
            raise ValueError(f"demande non permise vers le Reachy Mini : {verbe} {chemin}")
        donnees = json.dumps(corps).encode("utf-8") if corps is not None else (b"" if verbe == "POST" else None)
        demande = urllib.request.Request(self.adresse + chemin, data=donnees, method=verbe,
                                         headers={"Content-Type": "application/json"})
        try:
            with self._ouvreur.open(demande, timeout=delai_s) as reponse:
                texte = reponse.read().decode("utf-8")
        except urllib.error.HTTPError as erreur:  # le programme de fond a répondu par un code d'erreur
            detail = f"code {erreur.code} {erreur.read()[:200].decode('utf-8', 'replace')}".strip()
            if verbe == "GET":  # une LECTURE qui rate : on ne sait plus rien du robot = liaison perdue
                raise ConnectionError(f"le Reachy Mini ne donne pas {chemin} : {detail}") from erreur
            raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse {verbe} {chemin} : {detail}") from erreur
        except (urllib.error.URLError, OSError, http.client.HTTPException) as erreur:  # personne ne répond, ou trop tard
            raise ConnectionError(f"le programme de fond du Reachy Mini ne répond pas à {self.adresse} : {erreur}") from erreur
        try:
            return json.loads(texte) if texte.strip() else None
        except ValueError as erreur:
            raise ConnectionError(f"réponse illisible du Reachy Mini à {chemin}") from erreur

    def get(self, chemin: str) -> Any:
        return self._demander("GET", chemin, None, DELAI_LECTURE_S)

    def post(self, chemin: str, corps: dict | None = None, delai_s: float = DELAI_ORDRE_S) -> Any:
        return self._demander("POST", chemin, corps, delai_s)


class LiaisonReachyMini(LiaisonVide):
    chemin = "sdk"
    # Les deux actions obligatoires, et deux mouvements de tête (15.11.2026), essayés sur faux robot seulement.
    # « rejouer_geste » : oui, non, lever_la_tete, coucher_la_tete.
    # Les arrêts sont des PROPOSITIONS, à confirmer avec le responsable sécurité.
    branchees = frozenset({"arreter", "etat", "regarder", "rejouer_geste"})
    sait_aller_au_lieu = False  # il est posé sur une table : il ne va nulle part
    # Pas pour ce robot (le modèle vide répond « À BRANCHER ») : vitesse (il ne se déplace pas), saisir et poser
    # (ni bras ni pince).

    def __init__(self, kit: Any, simulateur_du_fabricant: bool = False) -> None:
        self.kit = kit
        # Le programme du fabricant a un mode simulé (« --sim », « --mockup-sim »). Branché là-dessus par le vrai client,
        # notre système croirait parler à un VRAI robot et écrirait « testé sur vrai robot ». Donc : refus, sauf pour un
        # essai à la main qui le demande exprès (jamais par le système ni par le test de conformité).
        self.simulateur_du_fabricant = simulateur_du_fabricant
        # Faux ou vrai : décidé par la CLASSE du kit (un faux kit du projet, comme la doublure), jamais par ce que le kit dit.
        # (Avec l'option d'essai à la main « simulateur_du_fabricant », ce n'est PAS un vrai robot non plus.)
        self.vrai_robot = not isinstance(kit, FauxKit) and not simulateur_du_fabricant
        self.repere_du_monde = False  # pas d'odomètre : aucune position n'est donnée au gardien
        self._derniere: tuple[float, list[float]] | None = None  # (heure, positions) de la dernière lecture
        # Un mouvement de tête en cours = une « file » : (génération, cibles pas encore envoyées, vitesse moyenne), et le
        # « dernier » morceau envoyé : (génération, uuid, cible), gardé jusqu'à ce qu'on ait VÉRIFIÉ que la tête est arrivée.
        # La génération avance à chaque arrêt : une file ou un morceau d'avant l'arrêt ne comptent plus et ne partent plus.
        self._generation = 0
        self._file: tuple[int, list[tuple[float, float]], float] | None = None
        self._dernier: tuple[int, str, tuple[float, ...]] | None = None  # cible : (lacet, tangage) ou (lacet, tangage, hauteur)
        self._echec: tuple[float, str] | None = None  # (heure, texte) du dernier mouvement raté
        self._alerte: str | None = None  # un mouvement qu'on n'a pas réussi à annuler : dit jusqu'au prochain arrêt réussi
        self._arrets_en_cours = 0  # tant qu'un arrêt travaille (dans un autre fil), aucun ordre de tête ne part
        self._verrou_arrets = threading.Lock()  # deux arrêts peuvent travailler en même temps, dans deux fils
        # Après un arrêt d'URGENCE : plus aucun ordre de tête, plus aucun rallumage, jusqu'à ce qu'un humain réarme.
        # (L'adaptateur a déjà ce verrou ; la liaison garde le sien, pour le cas où un arrêt passe entre les deux.)
        self._urgence = False
        self._coucher_en_cours = -1  # la génération du « coucher_la_tete » en route : les moteurs seront coupés à la fin
        self._guet_jusqu_a = 0.0  # après un ordre resté sans réponse : jusqu'à cette heure, tic annule ce qui apparaît
        self.lent = False  # mis par adaptateur.py : en mode lent, « regarder » va deux fois moins vite (les gestes aussi)
        self.directions = self._lire_les_directions(DIRECTIONS)

    @staticmethod
    def creer_kit(adresse: str | None = None, **options: Any) -> Any:
        """Créer le client du VRAI robot. Appelé seulement après la confirmation tapée par un humain (feu orange).
        Rien n'est envoyé ici. Le programme de fond du Reachy Mini doit déjà tourner, lancé par un humain, sur un autre
        port que notre écran, SANS son réveil automatique (« --no-wake-up-on-start ») : la tête reste couchée, et c'est
        notre geste « lever_la_tete », accordé par le gardien, qui la lève lentement. Voir docs/projet/BRANCHER_LA_TETE.md.
        Version Lite : rien à régler, c'est http://127.0.0.1:8002. Version Wireless (le programme de fond tourne DANS
        le robot) : un humain donne l'adresse du robot dans REACHY_MINI_ADRESSE, et écrit REACHY_MINI_RESEAU_PRIVE=oui
        pour dire que le réseau est privé (ses adresses n'ont pas de mot de passe). Sans ces deux lignes : refus."""
        adresse = adresse or os.environ.get(ADRESSE_DANS_L_ENVIRONNEMENT) or ADRESSE_PAR_DEFAUT
        return ClientDuProgrammeDeFond(adresse, hors_de_cet_ordinateur=os.environ.get(RESEAU_PRIVE_DIT) == "oui")

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else {"limites": {}, "gestes": []}

    @staticmethod
    def _lire_les_directions(fichier: Path) -> dict[str, tuple[float, float]]:
        """Les directions du fichier, en radians. Une ligne illisible est laissée de côté (elle sera « inconnue »)."""
        try:
            lu = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return {}
        directions = {}
        for nom, angles in (lu.get("directions") or {}).items() if isinstance(lu, dict) else ():
            try:
                lacet, tangage = angles["lacet_deg"], angles["tangage_deg"]
                if isinstance(lacet, bool) or isinstance(tangage, bool):  # « true » n'est pas un angle
                    continue
                lacet, tangage = math.radians(float(lacet)), math.radians(float(tangage))
            except (TypeError, KeyError, ValueError):
                continue
            if math.isfinite(lacet) and math.isfinite(tangage):  # ni « nan » ni « inf » : une telle ligne est inconnue
                directions[str(nom)] = (lacet, tangage)
        return directions

    def _etat_du_fond(self) -> dict[str, Any]:
        """Une lecture. Lève une exception si le programme de fond ou le robot ne sont pas prêts."""
        etat = self.kit.get(ETAT_DU_FOND)
        if not isinstance(etat, dict) or etat.get("state") != EN_MARCHE:
            quoi = etat.get("state") if isinstance(etat, dict) else "réponse illisible"
            pourquoi = etat.get("error") if isinstance(etat, dict) else None
            raise TimeoutError(f"le programme de fond du Reachy Mini n'est pas en marche (état : {quoi}"
                               + (f" ; il dit : {pourquoi})" if pourquoi else ")"))
        if self.vrai_robot and not self.simulateur_du_fabricant and (etat.get("simulation_enabled") or etat.get("mockup_sim_enabled")):
            raise ConnectionError("le programme de fond du Reachy Mini est en MODE SIMULÉ : ce n'est pas un vrai robot. "
                                  "Refus : on ne fait jamais passer du simulé pour du réel. Le relancer sans « --sim » "
                                  "ni « --mockup-sim », robot branché.")
        if self.simulateur_du_fabricant and not (etat.get("simulation_enabled") or etat.get("mockup_sim_enabled")):
            # L'option d'essai à la main ne vaut QUE pour un simulateur : si c'est un vrai robot qui répond, refus.
            raise ConnectionError("l'option d'essai « simulateur_du_fabricant » est mise, mais c'est un VRAI robot qui "
                                  "répond : refus. Un vrai robot ne se commande que par le système (gardien, prise).")
        materiel = etat.get("backend_status") or {}
        if materiel.get("ready") is False:
            raise TimeoutError("le Reachy Mini n'est pas prêt (ses moteurs ne répondent pas à son programme de fond)")
        return etat

    def _mouvements_en_cours(self) -> list[str]:
        lu = self.kit.get(MOUVEMENTS_EN_COURS)
        if not isinstance(lu, list):
            raise ConnectionError("réponse illisible du Reachy Mini : la liste de ses mouvements en cours")
        return [str(mouvement["uuid"]) for mouvement in lu if isinstance(mouvement, dict) and "uuid" in mouvement]

    def _positions(self) -> list[float]:
        lu = self.kit.get(POSITIONS)
        try:
            tete, corps, antennes = lu["head_joints"], lu["body_yaw"], lu["antennas_position"]
            positions = [float(x) for x in tete] + [float(corps)] + [float(x) for x in antennes]
        except (TypeError, KeyError, ValueError) as erreur:
            raise ConnectionError("réponse illisible du Reachy Mini : ses positions") from erreur
        if len(positions) != 10:  # lu : 7 pour la tête, 1 pour le corps, 2 pour les antennes
            raise ConnectionError(f"réponse illisible du Reachy Mini : {len(positions)} positions au lieu de 10")
        return positions

    def _la_tete_bouge(self, frais: bool = False) -> bool:
        """Compare deux lectures de position. `frais` : toujours deux lectures neuves, à 0,06 s d'écart.
        Sinon, la lecture gardée en mémoire sert de point de comparaison si elle a moins d'une seconde."""
        maintenant, positions = time.monotonic(), self._positions()
        avant = None if frais else self._derniere
        if avant is None or maintenant - avant[0] > LECTURE_ENCORE_FRAICHE_S:
            avant = (maintenant, positions)
            time.sleep(ENTRE_DEUX_LECTURES_S)
            maintenant, positions = time.monotonic(), self._positions()
        self._derniere = (maintenant, positions)
        return max(abs(a - b) for a, b in zip(avant[1], positions)) > BOUGE_RAD

    # ---------------------------------------------------------------- la connexion (des lectures, rien ne bouge)
    def ouvrir(self) -> None:
        self._etat_du_fond()

    def fermer(self) -> None:
        return None  # chaque demande web s'ouvre et se ferme toute seule : rien à fermer

    def signe_de_vie(self) -> None:
        self._etat_du_fond()

    def _en_route(self) -> bool:
        """Un mouvement de tête lancé par nous n'est pas fini : il reste des morceaux, ou le dernier n'est pas vérifié."""
        file, dernier = self._file, self._dernier
        return bool((file and file[0] == self._generation) or (dernier and dernier[0] == self._generation))

    def lire_etat(self) -> dict[str, Any]:
        try:
            etat = self._etat_du_fond()
            materiel = etat.get("backend_status") or {}
            mode = materiel.get("motor_control_mode")
            en_cours = self._mouvements_en_cours()
            la_tete_bouge = self._la_tete_bouge()
        except Exception as erreur:
            # Une lecture qui rate : on ne sait plus rien du robot. Plus AUCUN morceau ne partira, et le mouvement en
            # route est dit RATÉ (jamais effacé : sinon un autre lecteur, comme l'écran, avalerait l'échec).
            self._abandonner(f"le mouvement de tête du Reachy Mini est abandonné : une lecture de son état a raté ({erreur})")
            raise
        a_suivre = self._en_route()
        # Dans le doute, le robot est dit EN MOUVEMENT (le sens sûr). Seuil et logique : à vérifier sur le robot.
        # La liste des mouvements en cours ne voit PAS tout (lu) : la mesure des positions la complète.
        bouge = la_tete_bouge or bool(en_cours) or a_suivre or mode not in MODES_CALMES
        erreurs = [f"le Reachy Mini dit : {materiel['error']}"] if materiel.get("error") else []
        echec = self._echec
        echec = echec if echec is not None and time.monotonic() - echec[0] < ECHEC_VISIBLE_S else None
        if echec is not None:
            erreurs.append(echec[1])
        alerte = self._alerte
        if alerte is not None:  # un mouvement pas annulé : on le dit, et le robot est dit en mouvement (le sens sûr)
            erreurs.append(alerte)
            bouge = True
        return {"batterie_pct": None,  # à vérifier : pas vu dans les adresses lues (la version Wireless a une batterie)
                "x": None, "y": None, "cap": None,  # il est posé sur une table
                "en_mouvement": bouge, "occupe": bool(en_cours) or a_suivre,
                "objet_tenu": None, "erreurs": erreurs,
                "arret_urgence": False,  # ce robot n'a pas d'état « arrêt d'urgence » à lui
                # Un mouvement raté en route : dit ici pendant 1,5 s. L'adaptateur, qui attend la fin de l'action,
                # le lit et compte l'action comme RATÉE (jamais « réussie »). Les autres lecteurs n'y perdent rien.
                "echec_action": echec[1] if echec is not None else None,
                "entendu": None}

    # ---------------------------------------------------------------- s'arrêter (PROPOSITIONS, à confirmer avec le responsable sécurité)
    def _plus_rien_a_suivre(self) -> None:
        """Un arrêt : plus aucun morceau de tête ne partira. Fait EN PREMIER, sans rien attendre et sans rien lire."""
        self._generation += 1
        self._file = None
        self._dernier = None
        self._echec = None
        self._coucher_en_cours = -1

    def _abandonner(self, texte: str) -> None:
        """PAS un arrêt demandé : notre mouvement est abandonné en route. Il est dit RATÉ, plus rien ne part, et on
        tente d'annuler le morceau qui joue (sans rien promettre : la liaison vient peut-être de se perdre)."""
        dernier, en_route = self._dernier, self._en_route()
        if not en_route:
            return
        self._echec = (time.monotonic(), texte)  # d'abord l'échec, ensuite « plus occupé » : jamais l'inverse
        self._file, self._dernier = None, None
        if dernier is not None:
            try:
                self.kit.post(ARRETER_UN_MOUVEMENT, {"uuid": dernier[1]}, delai_s=DELAI_ORDRE_TETE_S)
            except Exception:
                pass  # déjà fini, ou robot injoignable : celui qui lit l'état recevra de toute façon l'erreur

    def _annuler_les_mouvements(self) -> None:
        """Demande l'arrêt de chaque mouvement de la liste. Un arrêt qui rate n'empêche pas les suivants
        (lu : arrêter un mouvement déjà fini rend une erreur)."""
        for uuid in self._mouvements_en_cours():
            try:
                self.kit.post(ARRETER_UN_MOUVEMENT, {"uuid": uuid})
            except ActionImpossible:
                continue

    def arreter_mouvement(self) -> None:
        # PROPOSITION : arrêter chaque mouvement en cours, puis VÉRIFIER. Lu : annuler un mouvement arrête la mise à jour
        # de ses cibles ; la tête tient alors sa dernière cible. Lu aussi : la liste ne montre que les mouvements lancés
        # par les adresses web. Un réveil, un geste lancé par le kit du fabricant, le suivi du visage n'y sont pas, et
        # aucune adresse web ne dit « arrête tout ». Donc on regarde si la tête bouge encore, et on le dit.
        debut = time.monotonic()
        self._plus_rien_a_suivre()
        with self._verrou_arrets:
            self._arrets_en_cours += 1  # tant que cet arrêt travaille, aucun ordre de tête ne part (voir _libre_et_pret)
        try:
            self._arreter_et_verifier(debut)
        finally:
            with self._verrou_arrets:
                self._arrets_en_cours -= 1

    def _arreter_et_verifier(self, debut: float) -> None:
        self._annuler_les_mouvements()
        restent = self._mouvements_en_cours()
        if restent:
            raise ActionImpossible("arret_non_confirme", f"{len(restent)} mouvement(s) du Reachy Mini encore en cours")
        # Vu sur le simulateur du fabricant : après l'arrêt, la tête glisse encore un instant. On lui laisse 0,6 s,
        # sans jamais dépasser 0,85 s pour tout l'arrêt (une méthode de liaison rend la main en moins d'1 s).
        fin = min(time.monotonic() + ATTENTE_APRES_ARRET_S, debut + BUDGET_ARRET_S)
        while self._la_tete_bouge(frais=True):
            if time.monotonic() < fin:
                continue
            raise ActionImpossible("arret_non_confirme", "la tête du Reachy Mini bouge encore : un mouvement que notre "
                                   "liaison ne voit pas (un autre programme ?). Couper les moteurs.")
        restent = self._mouvements_en_cours()  # relu à la toute fin : un ordre a pu arriver pendant l'attente
        if restent:
            raise ActionImpossible("arret_non_confirme", f"{len(restent)} mouvement(s) du Reachy Mini encore en cours")
        self._alerte = None  # un arrêt entièrement vérifié : l'alerte d'avant n'a plus lieu d'être

    def arret_urgence(self) -> None:
        # PROPOSITION, à décider avec le responsable sécurité : COUPER LES MOTEURS D'ABORD (plus de force), puis annuler
        # les mouvements (sinon un mouvement en cours continue d'écrire des cibles). Lu : « Limp. No power. »
        # La tête peut s'affaisser (à vérifier). Ce n'est PAS un verrou : un autre programme peut rallumer les moteurs.
        # Il ne remplace JAMAIS le fait de débrancher le robot.
        self._urgence = True  # AVANT tout : plus aucun ordre de tête ni rallumage jusqu'au réarmement par un humain
        self._plus_rien_a_suivre()
        with self._verrou_arrets:
            self._arrets_en_cours += 1
        coupure_ratee = None
        try:
            try:
                self.kit.post(COUPER_LES_MOTEURS)
            except Exception as erreur:  # on essaie quand même d'annuler les mouvements, puis on dit que la coupure a raté
                coupure_ratee = erreur
            try:
                self._annuler_les_mouvements()
                if coupure_ratee is None and not self._mouvements_en_cours():
                    self._alerte = None  # moteurs coupés et plus rien en cours : l'alerte d'avant n'a plus lieu d'être
            except Exception:  # la coupure est déjà partie : une liste illisible ne doit pas la masquer
                pass
        finally:
            with self._verrou_arrets:
                self._arrets_en_cours -= 1
        if coupure_ratee is not None:
            raise coupure_ratee

    def rearmer(self) -> None:
        # Rien n'est envoyé au robot : les moteurs restent coupés. Réarmer (une décision d'humain) lève seulement le
        # verrou d'urgence de la liaison ; rallumer les moteurs est une étape à part : le geste « lever_la_tete »,
        # accordé par le gardien.
        self._urgence = False
        return None

    # ---------------------------------------------------------------- bouger la tête (lentement, de peu)
    # Relu par un relecteur neuf le 15.11.2026 (16 défauts, dont 5 graves) et réécrit. Les règles tenues ici :
    # 1. Un arrêt passe TOUJOURS devant : la génération est lue à la première ligne de regarder() et de geste() ; un ordre
    #    ne part pas si elle a changé, et s'il est parti pendant qu'un arrêt passait, il est annulé tout de suite.
    # 2. Jamais deux mouvements à la fois : rien ne part si quelque chose joue, et APRÈS chaque envoi on vérifie que
    #    notre ordre est bien dans la liste du fabricant (vu : un ordre arrivé pendant un autre est perdu sans le dire).
    # 3. Un mouvement n'est « fini » que si la tête est ARRIVÉE à sa cible (à 4° près). Sinon il est dit raté.
    # 4. Une lecture qui rate, des moteurs coupés, une tête pas en place : plus aucun morceau ne part.
    def _pose(self) -> dict[str, float]:
        """Une lecture : où est la tête (angles en radians, décalages en mètres) et de combien le corps a tourné."""
        lu = self.kit.get(POSE_DE_LA_TETE)
        try:
            tete, antennes = lu["head_pose"], lu["antennas_position"]
            pose = {"lacet": float(tete["yaw"]), "tangage": float(tete["pitch"]), "roulis": float(tete["roll"]),
                    "x": float(tete["x"]), "y": float(tete["y"]), "z": float(tete["z"]), "corps": float(lu["body_yaw"]),
                    "antenne_1": float(antennes[0]), "antenne_2": float(antennes[1])}
        except (TypeError, KeyError, ValueError, IndexError) as erreur:
            raise ConnectionError("réponse illisible du Reachy Mini : la pose de sa tête") from erreur
        if not all(math.isfinite(valeur) for valeur in pose.values()):
            raise ConnectionError("réponse illisible du Reachy Mini : la pose de sa tête")
        return pose

    @staticmethod
    def _tete_en_place(pose: dict[str, float]) -> None:
        """La tête est levée, droite, dans nos petites limites, et le corps est de face. Sinon : refus, rien ne part."""
        if (abs(pose["lacet"]) > LACET_MAX_RAD + MARGE_RAD or abs(pose["tangage"]) > TANGAGE_MAX_RAD + MARGE_RAD
                or abs(pose["roulis"]) > ROULIS_MAX_RAD or abs(pose["corps"]) > CORPS_MAX_RAD
                or max(abs(pose["x"]), abs(pose["y"]), abs(pose["z"])) > DECALAGE_MAX_M):
            raise ActionImpossible("tete_pas_en_place", "la tête du Reachy Mini n'est pas en place (couchée, penchée, trop "
                                   "tournée, ou le corps a tourné). Lui demander d'abord de lever la tête "
                                   "(« réveille-toi ») : le gardien demandera l'accord d'un humain.")

    @staticmethod
    def _morceau(cible: tuple[float, float], duree_s: float) -> dict[str, Any]:
        """Un ordre de tête. Refusé ICI s'il sort de nos petites limites (vu : le fabricant ne refuse pas, il ramène)."""
        lacet, tangage = cible
        if not (math.isfinite(lacet) and math.isfinite(tangage) and math.isfinite(duree_s)):
            raise ActionImpossible("hors_limites", "un angle ou une durée de l'ordre de tête n'est pas un nombre : rien ne part")
        if abs(lacet) > LACET_MAX_RAD + 1e-9 or abs(tangage) > TANGAGE_MAX_RAD + 1e-9:
            raise ActionImpossible("hors_limites", f"la tête du Reachy Mini n'ira pas à {math.degrees(lacet):.0f}° de côté "
                                   f"et {math.degrees(tangage):.0f}° de haut : nos limites sont "
                                   f"{math.degrees(LACET_MAX_RAD):.0f}° et {math.degrees(TANGAGE_MAX_RAD):.0f}°")
        if duree_s > DUREE_MAX_S:  # on ne raccourcit JAMAIS une durée (ce serait aller plus vite) : on refuse
            raise ActionImpossible("trop_loin", f"ce mouvement de tête durerait {duree_s:.0f} s : la tête est trop loin de sa cible")
        return {"head_pose": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": tangage, "yaw": lacet},
                "duration": max(float(duree_s), DUREE_MIN_S)}

    def _moteurs_allumes(self) -> None:
        materiel = self._etat_du_fond().get("backend_status") or {}
        if materiel.get("motor_control_mode") != MOTEURS_ALLUMES:
            raise ActionImpossible("moteurs_coupes", "les moteurs du Reachy Mini ne sont pas allumés (mode : "
                                   f"{materiel.get('motor_control_mode')}). Les rallumer est décidé par un humain.")

    def _libre_et_pret(self) -> None:
        """Avant un nouvel ordre : le robot est prêt, ses moteurs sont allumés, et RIEN ne joue dans ce que nous voyons."""
        if self._urgence:
            raise ActionImpossible("arret_urgence_actif", "arrêt d'urgence : aucun ordre de tête avant qu'un humain réarme")
        if self._arrets_en_cours > 0:
            raise ActionImpossible("arrete", "un arrêt est en cours : l'ordre de tête n'est pas parti")
        self._moteurs_allumes()
        echec = self._echec
        if echec is not None and time.monotonic() - echec[0] < ECHEC_VISIBLE_S:
            raise ActionImpossible("robot_occupe", "le mouvement de tête d'avant vient de rater : attendre un instant")
        if self._alerte is not None:
            raise ActionImpossible("robot_occupe", "un mouvement n'a pas pu être annulé : arrêter le robot d'abord")
        if self._en_route() or self._mouvements_en_cours():
            raise ActionImpossible("robot_occupe", "le Reachy Mini joue déjà un mouvement : un deuxième ordre serait "
                                   "perdu sans le dire (vu sur le simulateur du fabricant). Arrêter d'abord.")

    def _annuler_apres_coup(self, uuid: str | None) -> None:
        """Un ordre est peut-être parti alors qu'il ne fallait pas (un arrêt est passé, ou pas de réponse) : l'annuler,
        et VÉRIFIER. Si on ne peut pas le vérifier, on le dit (jamais de silence)."""
        try:
            if uuid is not None:
                try:
                    self.kit.post(ARRETER_UN_MOUVEMENT, {"uuid": uuid})
                except ActionImpossible:
                    pass  # déjà fini ou déjà annulé : la liste, juste après, le dira
            self._annuler_les_mouvements()
            restent = self._mouvements_en_cours()
        except Exception as erreur:
            self._alerte = "un ordre de tête est peut-être parti et n'a pas pu être annulé : arrêter le robot"
            raise ActionImpossible("arret_non_confirme", f"{self._alerte} ({erreur}). Couper les moteurs.") from erreur
        if restent:
            self._alerte = f"{len(restent)} mouvement(s) du Reachy Mini encore en cours après une annulation : arrêter le robot"
            raise ActionImpossible("arret_non_confirme", f"{self._alerte}. Couper les moteurs.")

    def _envoyer(self, cible: tuple[float, float], pose: dict[str, float], vitesse_rad_s: float, generation: int,
                 debut: float | None = None) -> None:
        """Envoie UN morceau de « regarder » ou de geste, puis vérifie qu'il est bien parti, lui et lui seul."""
        angle = max(abs(cible[0] - pose["lacet"]), abs(cible[1] - pose["tangage"]))
        morceau = self._morceau(cible, angle / vitesse_rad_s)  # la durée vient de la position LUE à l'instant
        self._poster(morceau, cible, generation, debut)

    def _poster(self, morceau: dict[str, Any], cible: tuple[float, ...], generation: int, debut: float | None) -> None:
        """Le seul endroit d'où part un ordre de tête."""
        if generation != self._generation or self._arrets_en_cours > 0 or self._urgence:
            raise ActionImpossible("arrete", "un arrêt est passé : l'ordre de tête n'est pas parti")
        if debut is not None and time.monotonic() - debut > BUDGET_AVANT_ENVOI_S:
            raise ActionImpossible("trop_lent", "le Reachy Mini répond trop lentement : l'ordre de tête n'est pas parti")
        try:
            rendu = self.kit.post(BOUGER_LA_TETE, morceau, delai_s=DELAI_ORDRE_TETE_S)
            uuid = str(rendu["uuid"])
        except ActionImpossible:
            raise  # le programme de fond a dit non : rien n'est parti
        except Exception as erreur:  # pas de réponse, ou une réponse illisible : l'ordre a pu partir quand même…
            # …ou il peut ARRIVER EN RETARD. Donc : annuler ce qu'on voit, et guetter encore 1,5 s dans tic().
            self._guet_jusqu_a = time.monotonic() + GUET_APRES_UN_ORDRE_SANS_REPONSE_S
            self._annuler_apres_coup(None)
            raise ConnectionError(f"le Reachy Mini n'a pas répondu à l'ordre de tête ({erreur}) : ce qui jouait a été "
                                  "annulé, et la liaison guette encore 1,5 s un ordre arrivé en retard") from erreur
        if generation != self._generation or self._arrets_en_cours > 0 or self._urgence:  # un arrêt PENDANT l'envoi : annulé
            self._annuler_apres_coup(uuid)
            raise ActionImpossible("arrete", "un arrêt est passé pendant l'envoi : l'ordre de tête a été annulé")
        if uuid not in self._mouvements_en_cours():  # vu : accepté = dans la liste ; perdu = pas dans la liste
            raise ActionImpossible("ordre_perdu", "le Reachy Mini a perdu l'ordre de tête (un autre mouvement joue, "
                                   "lancé par un autre programme ?) : la tête n'a pas bougé comme demandé")
        self._dernier = (generation, uuid, cible)

    def _recouper(self, pourquoi: str) -> None:
        """Nous venons de rallumer les moteurs et la suite a raté : on les recoupe (la tête est couchée, rien ne tombe).
        Si même cela rate, c'est dit, et ça reste dit."""
        try:
            self.kit.post(COUPER_LES_MOTEURS)
        except Exception as erreur:
            self._alerte = f"les moteurs du Reachy Mini sont peut-être restés allumés ({pourquoi}) : débrancher le robot"
            raise ActionImpossible("arret_non_confirme", f"{self._alerte} ({erreur})") from erreur

    def _allumer_sans_saut(self, generation: int) -> None:
        """Le SEUL endroit qui allume les moteurs. La tête ne doit pas bouger : on le vérifie, sinon on recoupe."""
        avant = self._pose()
        if generation != self._generation or self._arrets_en_cours > 0 or self._urgence:
            raise ActionImpossible("arrete", "un arrêt est passé : les moteurs ne sont pas rallumés")
        try:
            self.kit.post(ALLUMER_LES_MOTEURS, delai_s=DELAI_ORDRE_TETE_S)
        except ActionImpossible:
            raise  # le programme de fond a dit non : rien n'est allumé
        except Exception as erreur:  # pas de réponse : l'ordre a pu arriver quand même
            self._recouper("l'ordre d'allumer est resté sans réponse")
            raise ConnectionError(f"le Reachy Mini n'a pas répondu à l'ordre d'allumer ses moteurs ({erreur}) : ils ont été recoupés") from erreur
        try:
            if generation != self._generation or self._arrets_en_cours > 0 or self._urgence:
                raise ActionImpossible("arrete", "un arrêt est passé pendant le rallumage")
            time.sleep(ATTENTE_APRES_ALLUMAGE_S)
            apres = self._pose()
            saut = max(abs(apres["lacet"] - avant["lacet"]), abs(apres["tangage"] - avant["tangage"]), abs(apres["roulis"] - avant["roulis"]))
            if saut > SAUT_MAX_RAD or abs(apres["z"] - avant["z"]) > SAUT_MAX_M:
                raise ActionImpossible("tete_a_saute", "la tête du Reachy Mini a bougé toute seule quand ses moteurs se sont "
                                       f"allumés ({math.degrees(saut):.0f}°) : ils ont été recoupés. Ne pas réessayer sans un humain.")
            self._moteurs_allumes()  # relu : s'ils ne sont pas allumés, on s'arrête là
        except Exception:
            self._recouper("la suite du rallumage a raté")
            raise

    def _changer_de_posture(self, nom: str, vitesse_relative: float, generation: int, debut: float) -> None:
        """« lever_la_tete » ou « coucher_la_tete » : UN mouvement lent. C'est le seul ordre permis quand la tête n'est
        pas en place, et le seul chemin qui allume les moteurs (pour se lever). Le gardien a déjà dit oui."""
        duree = DUREE_POSTURE_S / min(max(vitesse_relative, VITESSE_RELATIVE_MIN_POSTURE), 1.0)
        if self._urgence:
            raise ActionImpossible("arret_urgence_actif", "arrêt d'urgence : aucun ordre de tête avant qu'un humain réarme")
        if self._arrets_en_cours > 0:
            raise ActionImpossible("arrete", "un arrêt est en cours : l'ordre de tête n'est pas parti")
        echec = self._echec
        if (echec is not None and time.monotonic() - echec[0] < ECHEC_VISIBLE_S) or self._alerte is not None:
            raise ActionImpossible("robot_occupe", "le mouvement de tête d'avant a raté ou n'a pas pu être annulé : arrêter d'abord")
        mode = (self._etat_du_fond().get("backend_status") or {}).get("motor_control_mode")
        if self._en_route() or self._mouvements_en_cours():
            raise ActionImpossible("robot_occupe", "le Reachy Mini joue déjà un mouvement. Arrêter d'abord.")
        pose = self._pose()
        if abs(pose["corps"]) > CORPS_MAX_RAD:
            raise ActionImpossible("tete_pas_en_place", "le corps du Reachy Mini a tourné : un humain le remet de face, moteurs coupés")
        cible = POSTURES[nom]
        if max(abs(cible["antennas"][0] - pose["antenne_1"]), abs(cible["antennas"][1] - pose["antenne_2"])) > TRAJET_MAX_ANTENNE_RAD:
            raise ActionImpossible("tete_pas_en_place", "une antenne du Reachy Mini est tournée trop loin : un humain la remet, moteurs coupés")
        nous_avons_allume = False
        if mode != MOTEURS_ALLUMES:
            if nom != "lever_la_tete" or mode != "disabled":  # se coucher sans moteurs n'a pas de sens ; mode inconnu : doute
                raise ActionImpossible("moteurs_coupes", f"les moteurs du Reachy Mini ne sont pas allumés (mode : {mode})")
            self._allumer_sans_saut(generation)
            nous_avons_allume = True
        morceau = {"head_pose": dict(cible["head_pose"]), "antennas": list(cible["antennas"]), "duration": duree}
        try:
            # (Pas de limite « 0,4 s depuis le début » ici : ce chemin lit plus et attend 0,12 s après l'allumage. Si
            # tout cela dure trop, l'adaptateur le dit « liaison perdue » et envoie un arrêt : le sens sûr.)
            self._poster(morceau, (cible["head_pose"]["yaw"], cible["head_pose"]["pitch"], cible["head_pose"]["z"]), generation, None)
        except Exception:
            if nous_avons_allume:  # le mouvement n'est pas parti : on ne laisse pas des moteurs allumés pour rien
                self._recouper("le mouvement pour se lever n'est pas parti")
            raise
        self._echec = None
        self._coucher_en_cours = generation if nom == "coucher_la_tete" else -1
        self._file = (generation, [], VITESSE_TETE_RAD_S)

    def _lancer(self, cibles: list[tuple[float, float]], vitesse_rad_s: float, generation: int, debut: float) -> None:
        """Le début commun de regarder() et de geste() : tout vérifier, puis envoyer le premier morceau."""
        self._libre_et_pret()
        pose = self._pose()
        self._tete_en_place(pose)
        centre = (min(max(pose["lacet"], -LACET_MAX_RAD), LACET_MAX_RAD), min(max(pose["tangage"], -TANGAGE_MAX_RAD), TANGAGE_MAX_RAD))
        # Une cible relative (un écart autour de la position du moment) est ramenée dans nos limites.
        relatif = not all(absolue for absolue, _ in cibles)
        cibles = [cible if absolue else (min(max(centre[0] + cible[0], -LACET_MAX_RAD), LACET_MAX_RAD),
                                         min(max(centre[1] + cible[1], -TANGAGE_MAX_RAD), TANGAGE_MAX_RAD))
                  for absolue, cible in cibles]
        if relatif and max(max(abs(c[0] - centre[0]), abs(c[1] - centre[1])) for c in cibles) < ECART_MIN_D_UN_GESTE_RAD:
            # Tête au bord de nos limites : le geste ne bougerait pas, et serait compté « fait ». On refuse.
            raise ActionImpossible("trop_pres_du_bord", "la tête du Reachy Mini est au bord de ses limites : ce geste ne "
                                   "bougerait pas. La faire regarder devant d'abord.")
        self._envoyer(cibles[0], pose, vitesse_rad_s, generation, debut)
        self._echec = None
        self._file = (generation, cibles[1:], vitesse_rad_s)  # d'une génération passée, elle ne partira jamais (voir tic)

    def _rater(self, generation: int, texte: str) -> None:
        if generation == self._generation:
            self._echec = (time.monotonic(), texte)  # d'abord l'échec, ensuite « plus occupé » : jamais l'inverse
            self._file = None
            self._dernier = None

    def tic(self) -> None:
        """Toutes les 0,1 s : si notre morceau est fini, vérifier que la tête est ARRIVÉE, puis envoyer le suivant.
        Avant chaque morceau, tout est revérifié (moteurs, tête en place, rien d'autre ne joue)."""
        debut = time.monotonic()
        generation, file, dernier = self._generation, self._file, self._dernier
        file = file if file and file[0] == generation else None
        dernier = dernier if dernier and dernier[0] == generation else None
        if file is None and dernier is None:
            if debut < self._guet_jusqu_a:  # un ordre resté sans réponse peut arriver en retard : on annule ce qui apparaît
                try:
                    self._annuler_les_mouvements()
                except Exception:
                    pass
            return
        try:
            en_cours = self._mouvements_en_cours()
            if dernier is not None and dernier[1] in en_cours:
                return  # notre morceau joue encore
            pose = self._pose()
            if dernier is not None:
                ecart = max(abs(pose["lacet"] - dernier[2][0]), abs(pose["tangage"] - dernier[2][1]))
                if ecart > TOLERANCE_ARRIVEE_RAD:
                    raise ActionImpossible("pas_arrivee", f"la tête s'est arrêtée à {math.degrees(ecart):.0f}° de sa cible")
                if len(dernier[2]) == 3 and abs(pose["z"] - dernier[2][2]) > TOLERANCE_HAUTEUR_M:  # se lever, se coucher
                    raise ActionImpossible("pas_arrivee", "la tête n'est pas arrivée à la hauteur voulue")
            if file is None or not file[1]:
                self._moteurs_allumes()  # coupés tout à la fin : la tête ne tient pas sa place, ce n'est pas « fini »
                if self._coucher_en_cours == generation:
                    # La tête est couchée : comme le fabricant, on coupe les moteurs (ils ne forcent pas contre le socle).
                    self.kit.post(COUPER_LES_MOTEURS)
                if generation == self._generation:
                    self._file, self._dernier, self._coucher_en_cours = None, None, -1  # fini, et vérifié
                return
            if en_cours:
                raise ActionImpossible("robot_occupe", "un autre mouvement joue : le geste s'arrête là")
            self._moteurs_allumes()
            self._tete_en_place(pose)
            self._envoyer(file[1].pop(0), pose, file[2], generation, debut)
        except Exception as erreur:  # le mouvement s'arrête là, et il est dit RATÉ à celui qui attend sa fin
            if isinstance(erreur, ActionImpossible) and erreur.code == "arret_non_confirme":
                self._alerte = str(erreur)  # quel que soit l'arrêt passé entre-temps : un mouvement joue peut-être encore
            self._rater(generation, f"le mouvement de tête du Reachy Mini s'est arrêté en route : {erreur}")

    def geste(self, nom: str, vitesse_relative: float) -> None:
        # PROPOSITION, à vérifier sur le vrai robot : « oui » et « non », de petits mouvements de tête autour de la
        # position du moment. La vitesse demandée ne fait que RALENTIR (0,5 = deux fois plus lent) ; sous 0,25, c'est 0,25.
        generation, debut = self._generation, time.monotonic()  # lus AVANT tout : un arrêt qui passe ensuite gagne
        if nom not in GESTES and nom not in POSTURES:
            raise ActionImpossible("geste_inconnu", f"le Reachy Mini ne connaît pas le geste « {nom} » "
                                   f"(connus : {sorted([*GESTES, *POSTURES])})")
        vitesse_relative = float(vitesse_relative)
        if not math.isfinite(vitesse_relative):
            raise ActionImpossible("hors_limites", "la vitesse demandée pour le geste n'est pas un nombre : rien ne part")
        if nom in POSTURES:
            return self._changer_de_posture(nom, vitesse_relative, generation, debut)
        vitesse = min(max(vitesse_relative, VITESSE_RELATIVE_MIN), 1.0) * VITESSE_GESTE_RAD_S
        ecarts = [(False, (math.radians(lacet), math.radians(tangage))) for lacet, tangage in GESTES[nom]]
        self._lancer(ecarts, vitesse, generation, debut)

    def regarder(self, cible: str) -> None:
        # PROPOSITION, à vérifier sur le vrai robot : tourner LENTEMENT la tête vers une direction du fichier
        # directions.yaml (réglé par l'équipe, sur place). Une cible inconnue ou hors limites est refusée : rien ne part.
        generation, debut = self._generation, time.monotonic()  # lus AVANT tout : un arrêt qui passe ensuite gagne
        if cible not in self.directions:
            raise ActionImpossible("cible_inconnue", f"le Reachy Mini ne sait pas où est « {cible} » "
                                   f"(directions connues : {sorted(self.directions)} — fichier directions.yaml)")
        self._morceau(self.directions[cible], DUREE_MIN_S)  # refuse ici une direction hors limites, avant toute lecture
        vitesse = VITESSE_TETE_RAD_S * (0.5 if self.lent else 1.0)
        self._lancer([(True, self.directions[cible])], vitesse, generation, debut)

    def montrer(self, cible: str) -> None:
        # À BRANCHER : montrer avec la tête et les antennes. Pas branché exprès : « regarder » suffit pour la démonstration.
        raise ABrancher("montrer", "montrer une direction avec la tête (il n'a pas de bras)")

    def parler(self, texte: str, langue: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : son haut-parleur (lu : il en a un). Sinon la voix reste au Mac.
        raise ABrancher("parler", "haut-parleur du Reachy Mini (ou laisser la voix au Mac : brique 4)")

    def ecouter(self, duree_s: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : ses micros (lu : il en a). Sinon l'écoute reste au Mac.
        raise ABrancher("ecouter", "micros du Reachy Mini (ou laisser l'écoute au Mac : brique 4)")
