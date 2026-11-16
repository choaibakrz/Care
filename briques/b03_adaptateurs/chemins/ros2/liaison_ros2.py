"""Brique 3 — Chemin (b) : ÉBAUCHE d'un PONT vers ROS 2.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot, avec le faux ROS 2 (faux_ros2.py). ROS 2 n'est PAS installé ici.

ROS 2 est un système standard pour faire parler les programmes d'un robot : chaque programme publie des messages sur
des « sujets » (topics : des canaux nommés, ex. /cmd_vel) et lit ceux des autres. Le pont est un petit programme ROS 2
(un « nœud ») qui PUBLIE nos ordres (vitesse, geste, phrase) et LIT l'état du robot (odomètre, batterie).

Ce qui a été lu (11.11.2026, sans copier de code) :
- github.com/ros2/rclpy (Apache-2.0) : rclpy.init(), rclpy.ok(), rclpy.create_node(nom), rclpy.spin_once(node,
  timeout_sec=…), rclpy.shutdown() ; node.create_publisher(type, sujet, qos), node.create_subscription(type, sujet,
  rappel, qos), node.destroy_node() ; publisher.publish(msg). qos peut être un entier (taille de la file).
- github.com/ros2/common_interfaces (Apache-2.0) : geometry_msgs/Twist (linear, angular : Vector3 x, y, z) ;
  nav_msgs/Odometry (header, child_frame_id, pose : PoseWithCovariance, twist : TwistWithCovariance) ;
  geometry_msgs/Pose (position : Point, orientation : Quaternion x, y, z, w) ;
  sensor_msgs/BatteryState (percentage « de 0 à 1 », NaN si non mesuré) ; std_msgs/String (data) — String est
  « deprecated as of Foxy » d'après son fichier : un vrai robot aura ses propres messages (à vérifier).
Ce qui n'est PAS connu : les NOMS des sujets de chaque robot, ses messages à lui, son arrêt d'urgence. Tout ça est
dans SUJETS et dans les lignes « # À BRANCHER (à vérifier dans la doc du fabricant) ».

L'assistant (python3 lancer.py brancher NOM --chemin ros2) copie ce fichier dans robots/NOM/liaison.py.
"""
from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Any

from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide

# À BRANCHER (à vérifier dans la doc du fabricant) : les noms des sujets du robot. Ceux-ci sont des noms COURANTS
# (/cmd_vel, /odom) ou inventés pour le faux ROS 2 (/leukerbad/…), PAS ceux d'un fabricant.
# Lu (unitree_ros2, 11.11.2026) : /sportmodestate, /lowstate, /wirelesscontroller, /lowcmd, /api/sport/request
# (messages unitree_go, unitree_api : à installer, feu orange). /cmd_vel n'est pas dans la liste lue sur cette page.
SUJETS = {
    "vitesse": "/cmd_vel",                     # geometry_msgs/Twist — nom courant, PAS garanti
    "odometrie": "/odom",                      # nav_msgs/Odometry — nom courant, PAS garanti
    "batterie": "/battery_state",              # sensor_msgs/BatteryState — nom courant, PAS garanti
    "etat": "/leukerbad/etat",                 # inventé (faux ROS 2) : JSON occupé, erreurs, arrêt
    "parler": "/leukerbad/parler",             # inventé : la phrase à dire
    "geste": "/leukerbad/geste",               # inventé : le nom du geste
    "regarder": "/leukerbad/regarder",         # inventé
    "montrer": "/leukerbad/montrer",           # inventé
    "ecouter": "/leukerbad/ecouter",           # inventé
    "arret_urgence": "/leukerbad/arret_urgence",  # inventé : un vrai robot a souvent un « service » à lui (à vérifier)
}
FRAICHEUR_MAX_S = 1.0  # plus de message du robot depuis 1 s : liaison perdue
FILE = 10  # qos : taille de la file d'attente des messages


@dataclass
class MessagesROS2:
    """Les types de messages utilisés (vrais, ou ceux du faux ROS 2)."""

    Twist: Any
    Odometry: Any
    BatteryState: Any
    String: Any
    Bool: Any


def creer_ros2() -> tuple[Any, MessagesROS2]:
    """Le VRAI ROS 2. Jamais appelé par les tests. ROS 2 n'est pas installé dans ce projet (l'installer = feu orange)."""
    # À BRANCHER (à vérifier dans la doc du fabricant) : version de ROS 2 (Unitree : foxy ou humble ; Flexiv : humble
    # ou jazzy, lu le 11.11.2026), même ROS_DOMAIN_ID, même DDS (Unitree : CycloneDDS 0.10.2, lu dans unitree_ros2).
    try:
        import rclpy  # noqa: PLC0415
        from geometry_msgs.msg import Twist  # noqa: PLC0415
        from nav_msgs.msg import Odometry  # noqa: PLC0415
        from sensor_msgs.msg import BatteryState  # noqa: PLC0415
        from std_msgs.msg import Bool, String  # noqa: PLC0415
    except ImportError as e:
        raise ABrancher("ROS 2", f"pas installé sur cet ordinateur ({e}) : installer = feu orange, demander à Hiba") from e
    return rclpy, MessagesROS2(Twist=Twist, Odometry=Odometry, BatteryState=BatteryState, String=String, Bool=Bool)


class LiaisonPontROS2(LiaisonVide):  # gabarit:classe
    chemin = "ros2"
    # saisir et poser ne sont pas dans le pont : sur ROS 2, un bras passe souvent par MoveIt (à vérifier, feu orange).
    branchees = frozenset({"se_deplacer", "regarder", "ecouter", "parler", "montrer", "rejouer_geste", "arreter", "etat"})  # gabarit:branchees
    sait_aller_au_lieu = False  # à vérifier : le robot a-t-il une navigation (Nav2) avec une carte du lieu ?

    def __init__(self, rclpy: Any, messages: MessagesROS2, sujets: dict[str, str] | None = None,
                 nom_noeud: str = "leukerbad_pont") -> None:
        self.rclpy = rclpy
        self.msg = messages
        self.sujets = {**SUJETS, **(sujets or {})}
        self.nom_noeud = nom_noeud
        # Faux ou vrai : décidé par la CLASSE (le faux ROS 2 du projet), jamais par ce que l'objet dit de lui-même.
        from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import FauxRclpy  # ici : faux_ros2 importe ce fichier

        self.vrai_robot = type(rclpy) is not FauxRclpy
        self.repere_du_monde = not self.vrai_robot  # vrai robot : repère de l'odomètre à caler (à vérifier)
        self._noeud: Any = None
        self._pub: dict[str, Any] = {}
        self._derniers: dict[str, Any] = {}
        self._heures: dict[str, float] = {}
        self._verrou = threading.Lock()  # le fil de l'arrêt d'urgence publie aussi

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else self.rclpy.infos_simulation()

    # ---------------------------------------------------------------- la connexion
    def ouvrir(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : réseau du robot, ROS_DOMAIN_ID, DDS.
        if not self.rclpy.ok():
            self.rclpy.init()
        self._noeud = self.rclpy.create_node(self.nom_noeud)
        types = {"vitesse": self.msg.Twist, "arret_urgence": self.msg.Bool}
        for cle in ("vitesse", "parler", "geste", "regarder", "montrer", "ecouter", "arret_urgence"):
            self._pub[cle] = self._noeud.create_publisher(types.get(cle, self.msg.String), self.sujets[cle], FILE)
        for cle, genre in (("odometrie", self.msg.Odometry), ("batterie", self.msg.BatteryState), ("etat", self.msg.String)):
            self._noeud.create_subscription(genre, self.sujets[cle], self._rappel(cle), FILE)
        # Rien n'est publié ici : ouvrir ne fait jamais bouger le robot.

    def _rappel(self, cle: str):
        def recevoir(msg: Any) -> None:
            self._derniers[cle], self._heures[cle] = msg, time.monotonic()
        return recevoir

    def fermer(self) -> None:
        if self._noeud is not None:
            self._noeud.destroy_node()
            self._noeud = None

    def tic(self) -> None:
        if self._noeud is not None:
            with self._verrou:
                self.rclpy.spin_once(self._noeud, timeout_sec=0.0)

    def _publier(self, cle: str, msg: Any) -> None:
        with self._verrou:
            self._pub[cle].publish(msg)

    def _texte(self, cle: str, **contenu: Any) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : le vrai message du robot (pas un texte JSON).
        m = self.msg.String()
        m.data = json.dumps(contenu, ensure_ascii=False)
        self._publier(cle, m)

    def _frais(self) -> None:
        """Le robot publie-t-il encore ? Sinon : liaison perdue (exception)."""
        heure = self._heures.get("odometrie")
        if heure is None or time.monotonic() - heure > FRAICHEUR_MAX_S:
            raise ConnectionError(f"plus de message du robot sur {self.sujets['odometrie']} depuis plus de {FRAICHEUR_MAX_S} s")

    def signe_de_vie(self) -> None:
        self.tic()
        self._frais()

    def lire_etat(self) -> dict[str, Any]:
        self.tic()
        self._frais()
        odo = self._derniers["odometrie"]
        p, q = odo.pose.pose.position, odo.pose.pose.orientation
        lin, ang = odo.twist.twist.linear, odo.twist.twist.angular
        etat: dict[str, Any] = {"x": p.x, "y": p.y, "cap": math.degrees(2 * math.atan2(q.z, q.w)) % 360,
                                "en_mouvement": math.hypot(lin.x, lin.y) > 0.01 or abs(ang.z) > 0.01}
        batterie = self._derniers.get("batterie")
        if batterie is not None and isinstance(batterie.percentage, float) and math.isfinite(batterie.percentage):
            etat["batterie_pct"] = round(batterie.percentage * 100, 1)  # de 0 à 1 d'après le message (à vérifier par robot)
        texte = self._derniers.get("etat")
        if texte is not None:
            # À BRANCHER (à vérifier dans la doc du fabricant) : où le robot dit-il qu'il est occupé, en erreur, arrêté ?
            infos = json.loads(texte.data)
            etat.update({k: infos.get(k) for k in ("occupe", "erreurs", "arret_urgence", "objet_tenu", "entendu")})
            etat["en_mouvement"] = etat["en_mouvement"] or bool(infos.get("en_mouvement"))
        return etat

    # ---------------------------------------------------------------- s'arrêter (à brancher EN PREMIER)
    def _twist(self, vx: float, vy: float, vyaw: float) -> Any:
        t = self.msg.Twist()
        t.linear.x, t.linear.y, t.angular.z = float(vx), float(vy), float(vyaw)
        return t

    def arreter_mouvement(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : vitesse nulle ; et arrêter un geste en cours ?
        self._publier("vitesse", self._twist(0.0, 0.0, 0.0))

    def arret_urgence(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : l'arrêt du robot (souvent un service ROS 2 à lui).
        # Publier ne dit pas que le robot a reçu : un vrai arrêt devrait être confirmé (réponse du service, état lu).
        self._publier("vitesse", self._twist(0.0, 0.0, 0.0))
        m = self.msg.Bool()
        m.data = True
        self._publier("arret_urgence", m)

    def rearmer(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : lever le blocage, SANS mouvement.
        m = self.msg.Bool()
        m.data = False
        self._publier("arret_urgence", m)

    # ---------------------------------------------------------------- bouger, parler
    def vitesse(self, vx: float, vy: float, vyaw: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : le robot lit-il un Twist ? sur quel sujet ? l'oublie-t-il
        # seul s'il n'est pas répété (chien de garde) ? Unitree (lu) : passe par /api/sport/request, pas par /cmd_vel.
        self._publier("vitesse", self._twist(vx, vy, vyaw))

    def geste(self, nom: str, vitesse_relative: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : le geste enregistré, par son nom.
        self._texte("geste", nom=nom, vitesse_relative=vitesse_relative)

    def regarder(self, cible: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant)
        self._texte("regarder", cible=cible)

    def montrer(self, cible: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant)
        self._texte("montrer", cible=cible)

    def parler(self, texte: str, langue: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : haut-parleur du robot (sinon : la voix du Mac, brique 4).
        self._texte("parler", texte=texte, langue=langue)

    def ecouter(self, duree_s: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : micros du robot (sinon : le micro du Mac, brique 4).
        self._texte("ecouter", duree_s=duree_s)
