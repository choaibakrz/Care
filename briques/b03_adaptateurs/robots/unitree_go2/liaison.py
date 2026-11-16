"""ÉBAUCHE de liaison vers un Unitree Go2 programmable, par le kit Python public du fabricant.

PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot. Essayée seulement avec une doublure (doublure.py).
Personne de l'équipe n'a vu ce robot. Le kit du fabricant n'est PAS installé sur nos ordinateurs (l'installer est un
feu orange : dire la taille et la licence, attendre le « oui » de Hiba).

Ce que cette ébauche sait faire, et rien d'autre (demande de Hiba, 12.11.2026) :
    se lever            → StandUp()                 (un geste nommé « se_lever », demandé par la prise, jamais tout seul)
    avancer à une vitesse donnée → Move(vx, vy, vyaw), répété par l'adaptateur toutes les 0,1 s
    s'arrêter           → StopMove()
    dire son état       → le dernier message d'état reçu (position, vitesse, code d'erreur)

LU EN LIGNE, le 12.11.2026 (documentation publique, rien cloné, rien installé) :
- github.com/unitreerobotics/unitree_sdk2_python — unitree_sdk2py/go2/sport/sport_client.py :
  la classe SportClient ; StandUp(), StopMove(), Move(vx: float, vy: float, vyaw: float) ; chacune fait « return code ».
- même dépôt — example/go2/high_level/go2_sport_client.py :
  ChannelFactoryInitialize(0, <carte réseau>) ; SportClient() ; SetTimeout(10.0) ; Init() ;
  et l'avertissement du fabricant : « WARNING: Please ensure there are no obstacles around the robot while running this example. »
- même dépôt — unitree_sdk2py/idl/unitree_go/msg/dds_/_SportModeState_.py : le message d'état a les champs
  error_code, mode, progress, position (3 nombres), velocity (3 nombres), yaw_speed (et d'autres).
- même dépôt — example/go2/low_level/go2_stand_example.py : ChannelSubscriber("rt/lowstate", LowState_) (forme d'un abonnement).
- licence du kit : BSD-3-Clause (fiche du 11.11.2026, briques/b03_adaptateurs/fiches/unitree_go2.md).

À VÉRIFIER SAMEDI (pas lu, donc pas écrit comme un fait) :
- le nom du sujet de l'état (« rt/sportmodestate » : à vérifier samedi) et la façon exacte de s'y abonner ;
- les unités et le repère de position et de velocity ; le sens des codes de error_code et de mode ;
- la batterie en pour cent, et le cap du robot : pas lus → l'état rend « inconnu », jamais un chiffre inventé ;
- si le chien s'arrête seul quand les ordres Move() cessent, et en combien de temps (Move() n'a pas de durée) ;
- combien de temps il met à se lever, et s'il faut un autre appel avant de marcher (BalanceStand() existe : à vérifier samedi) ;
- l'arrêt d'urgence logiciel : StopMove() (il reste debout) est une PROPOSITION ; le choix se fait avec le responsable
  sécurité. StopMove() ne bloque pas le chien : c'est l'adaptateur qui bloque nos ordres ;
- la version du robot (faut-il la version pour développeurs ?), la carte réseau, et si le kit marche depuis un Mac.
"""
from __future__ import annotations

import math
import time
from typing import Any

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import LiaisonVide

SUJET_ETAT = "rt/sportmodestate"  # à vérifier samedi : pas lu dans le kit Python (« rt/lowstate » lu pour l'autre état)
ETAT_VIEUX_S = 1.0  # choix de prudence de l'équipe : sans message d'état depuis 1 s, le robot est dit muet
DELAI_MARCHE_S, DELAI_ARRET_S = 10.0, 0.5  # 10 s : lu dans l'exemple ; 0,5 s pour l'arrêt : choix de l'équipe, à vérifier samedi
BOUGE_M_S = 0.02  # choix de l'équipe : en dessous, on dit que le robot ne bouge pas
GESTES = ("se_lever",)  # le seul geste de la carte ; il appelle StandUp(). Rien d'autre : ni saut, ni salto, ni danse.


class _VraiKit:
    """Le vrai kit, rangé comme la doublure : un client de marche, un client des arrêts, le dernier état reçu."""

    def __init__(self, sport: Any, arret: Any) -> None:
        self.sport, self.arret = sport, arret
        self._message: Any = None
        self._recu_a = 0.0

    def recevoir(self, message: Any) -> None:
        self._message, self._recu_a = message, time.monotonic()

    def dernier_etat(self) -> tuple[Any, float]:
        return self._message, (time.monotonic() - self._recu_a) if self._message is not None else math.inf

    def occupe(self) -> bool:
        return False  # à vérifier samedi : comment le robot dit qu'il a fini de se lever (champs mode, progress ?)


class LiaisonUnitreeGo2(LiaisonVide):
    chemin = "sdk"
    # Les actions de la prise branchées dans cette ébauche. « rejouer_geste » ne sert qu'au geste « se_lever ».
    branchees = frozenset({"arreter", "etat", "se_deplacer", "rejouer_geste"})
    sait_aller_au_lieu = False  # il ne connaît aucun lieu : seulement « avance de tant, à telle vitesse »

    def __init__(self, kit: Any) -> None:
        self.kit = kit
        # Faux ou vrai : décidé par la CLASSE du kit (un faux kit du projet, comme la doublure), jamais par ce que le kit dit.
        self.vrai_robot = not isinstance(kit, FauxKit)
        self.repere_du_monde = False  # la position du chien n'est pas calée sur notre plan : jamais donnée au gardien
        self._ouverte = False

    @staticmethod
    def creer_kit(carte_reseau: str | None = None, **options: Any) -> Any:
        """Créer les clients du VRAI kit. Appelé seulement pour le vrai robot, après la confirmation tapée par un humain
        (feu orange). Le kit s'importe ICI : le projet tourne sans lui. Rien ne bouge : ni StandUp(), ni Move()."""
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber  # lu le 12.11.2026
            from unitree_sdk2py.go2.sport.sport_client import SportClient  # lu le 12.11.2026
            from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_  # lu le 12.11.2026
        except ImportError as erreur:
            raise RuntimeError("le kit du fabricant (unitree_sdk2py) n'est pas installé sur cet ordinateur : l'installer est "
                               "un feu orange (taille, licence BSD-3-Clause, « oui » de Hiba)") from erreur
        if carte_reseau:
            ChannelFactoryInitialize(0, carte_reseau)  # lu : ChannelFactoryInitialize(0, sys.argv[1])
        else:
            ChannelFactoryInitialize(0)  # lu : la forme sans carte réseau existe dans l'exemple
        sport, arret = SportClient(), SportClient()
        sport.SetTimeout(DELAI_MARCHE_S)
        sport.Init()
        arret.SetTimeout(DELAI_ARRET_S)  # un client à part pour les arrêts, avec un délai court : à vérifier samedi
        arret.Init()
        kit = _VraiKit(sport, arret)
        abonnement = ChannelSubscriber(SUJET_ETAT, SportModeState_)  # forme lue pour « rt/lowstate » ; ce sujet : à vérifier samedi
        abonnement.Init(kit.recevoir, 10)  # à vérifier samedi : la forme exacte de Init(fonction, taille de file) n'a pas été lue
        kit.abonnement = abonnement
        return kit

    @staticmethod
    def _ok(code: Any, quoi: str, arret: bool = False) -> None:
        """Lu : chaque fonction du client fait « return code ». 0 = bien : à vérifier samedi pour chaque fonction.
        Pour un ARRÊT, pas de code du tout = arrêt NON confirmé."""
        if arret and code is None:
            raise ActionImpossible("arret_non_confirme", f"{quoi} : le kit ne rend aucun code, arrêt non confirmé")
        if code not in (0, None):
            raise ActionImpossible("robot_refuse", f"{quoi} : le robot répond le code {code}")

    def _etat_frais(self) -> Any:
        message, age = self.kit.dernier_etat()
        if message is None or age > ETAT_VIEUX_S:
            raise TimeoutError(f"le robot ne donne plus son état (aucun message depuis plus de {ETAT_VIEUX_S:.0f} s)")
        return message

    # ---------------------------------------------------------------- la connexion (rien ne bouge)
    def ouvrir(self) -> None:
        self._etat_frais()  # le robot répond : on a reçu son état. Aucun ordre n'est envoyé. Il ne se lève pas.
        self._ouverte = True

    def fermer(self) -> None:
        self._ouverte = False  # à vérifier samedi : le kit a-t-il une fermeture à appeler ? (rien lu)

    def signe_de_vie(self) -> None:
        self._etat_frais()

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else {"limites": {}, "gestes": list(GESTES)}

    def lire_etat(self) -> dict[str, Any]:
        m = self._etat_frais()
        vx, vy = float(m.velocity[0]), float(m.velocity[1])
        return {"batterie_pct": None,  # à vérifier samedi : pas lu dans la documentation
                "x": float(m.position[0]), "y": float(m.position[1]),  # à vérifier samedi : unité et repère
                "cap": None,  # à vérifier samedi : pas lu
                "en_mouvement": math.hypot(vx, vy) > BOUGE_M_S or abs(float(m.yaw_speed)) > BOUGE_M_S,
                "occupe": bool(self.kit.occupe()), "objet_tenu": None,
                "erreurs": [f"code d'erreur du robot : {m.error_code} (sens à vérifier samedi)"] if m.error_code else [],
                "arret_urgence": False, "entendu": None}

    # ---------------------------------------------------------------- s'arrêter
    def arreter_mouvement(self) -> None:
        self._ok(self.kit.sport.StopMove(), "StopMove", arret=True)

    def arret_urgence(self) -> None:
        # PROPOSITION, à décider avec le responsable sécurité : l'arrêt de marche, par le client au délai court.
        # Il ne remplace JAMAIS le bouton d'arrêt physique (où est-il sur ce chien ? à vérifier samedi).
        self._ok(self.kit.arret.StopMove(), "arrêt d'urgence (StopMove)", arret=True)

    def rearmer(self) -> None:
        return None  # StopMove() ne bloque rien dans le robot : rien à lever. Aucun mouvement, le robot n'est pas relevé.

    # ---------------------------------------------------------------- bouger
    def vitesse(self, vx: float, vy: float, vyaw: float) -> None:
        # Lu : Move(vx, vy, vyaw). L'exemple appelle Move(0.3,0,0) pour « move forward » : ce n'est pas une limite.
        # La vitesse arrive déjà bridée par la carte et par la prise (la plus petite limite gagne).
        self._ok(self.kit.sport.Move(float(vx), float(vy), float(vyaw)), "Move")

    def geste(self, nom: str, vitesse_relative: float) -> None:
        if nom not in GESTES:
            raise ActionImpossible("geste_inconnu", f"« {nom} » : cette ébauche ne sait que « se_lever »")
        self._ok(self.kit.sport.StandUp(), "StandUp")  # écrit en clair ; sans réglage de vitesse (rien lu)
