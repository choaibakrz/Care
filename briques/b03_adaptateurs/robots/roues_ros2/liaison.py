"""ÉBAUCHE de liaison vers un robot à roues qui parle ROS 2.

PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot. Essayée seulement avec une doublure : le faux ROS 2 du projet
(briques/b03_adaptateurs/chemins/ros2/faux_ros2.py). Nous ne savons pas quel robot nous aurons. ROS 2 n'est PAS
installé sur nos ordinateurs (l'installer est un feu orange : dire la taille et la licence, attendre le « oui » de Hiba).

ROS 2 est un langage commun à beaucoup de robots : chaque programme publie des messages sur des canaux nommés
(« sujets ») et lit ceux des autres. Cette ébauche est un petit programme ROS 2 (un « nœud ») qui sait, et rien d'autre
(demande de Hiba, 12.11.2026) :
    recevoir une vitesse → publier un message de vitesse (Twist) sur le canal de vitesse, répété par l'adaptateur
    s'arrêter            → publier une vitesse nulle
    dire sa position     → lire le dernier message de position (Odometry) publié par le robot

LU EN LIGNE (documentation publique, rien cloné, rien installé) :
- github.com/ros2/common_interfaces (Apache-2.0), relu le 12.11.2026 : geometry_msgs/msg/Twist.msg contient
  « Vector3 linear » et « Vector3 angular » ; nav_msgs/msg/Odometry.msg contient header, child_frame_id, pose, twist
  (la position est dans le repère de header.frame_id ; la vitesse dans celui de child_frame_id).
- github.com/ros2/rclpy (Apache-2.0), lu le 11.11.2026 (voir chemins/ros2/liaison_ros2.py) : rclpy.init(), rclpy.ok(),
  rclpy.create_node(nom), rclpy.spin_once(node, timeout_sec=…) ; node.create_publisher(type, sujet, qos),
  node.create_subscription(type, sujet, rappel, qos), node.destroy_node() ; publisher.publish(msg).

À VÉRIFIER SAMEDI (pas lu pour CE robot, donc pas écrit comme un fait) :
- les NOMS des canaux : « /cmd_vel » et « /odom » sont des noms courants, pas garantis ; chaque robot peut avoir les siens ;
- les unités (mètres par seconde et radians par seconde sont l'usage : à vérifier samedi) et le sens des axes ;
- si le robot s'arrête seul quand les messages de vitesse cessent, et en combien de temps ;
- son VRAI arrêt d'urgence : ROS 2 n'en a pas de standard. Ici, l'arrêt logiciel est une vitesse nulle : une PROPOSITION,
  à décider avec le responsable sécurité. Publier ne prouve pas que le robot a reçu ;
- la batterie : aucun canal n'est garanti → l'état rend « inconnu », jamais un chiffre inventé ;
- la version de ROS 2 du robot, son réseau, son numéro de domaine (ROS_DOMAIN_ID), et si tout cela marche depuis un Mac ;
- si un autre programme du robot publie aussi des vitesses (sa navigation, sa manette) : deux pilotes en même temps.
"""
from __future__ import annotations

import math
import threading
import time
from types import SimpleNamespace
from typing import Any

from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import FauxRclpy
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide

# Noms COURANTS, pas garantis : à vérifier samedi pour le robot que nous aurons. Aucun canal inventé.
SUJETS = {"vitesse": "/cmd_vel",     # geometry_msgs/Twist
          "odometrie": "/odom"}      # nav_msgs/Odometry
FRAICHEUR_MAX_S = 1.0  # choix de prudence de l'équipe : sans message de position depuis 1 s, le robot est dit muet
FILE = 10  # taille de la file d'attente des messages (un entier est accepté, lu dans rclpy)
BOUGE = 0.01  # choix de l'équipe : en dessous (m/s ou rad/s, unités à vérifier samedi), on dit que le robot ne bouge pas


def creer_ros2() -> tuple[Any, Any]:
    """Le VRAI ROS 2. Appelé seulement pour le vrai robot, après la confirmation tapée par un humain (feu orange).
    Jamais appelé par les essais. Rien n'est publié ici : le robot ne bouge pas."""
    try:
        import rclpy  # noqa: PLC0415
        from geometry_msgs.msg import Twist  # noqa: PLC0415
        from nav_msgs.msg import Odometry  # noqa: PLC0415
    except ImportError as erreur:
        raise ABrancher("ROS 2", f"pas installé sur cet ordinateur ({erreur}) : l'installer est un feu orange, demander à Hiba") from erreur
    return rclpy, SimpleNamespace(Twist=Twist, Odometry=Odometry)


class LiaisonRouesRos2(LiaisonVide):
    chemin = "ros2"
    branchees = frozenset({"arreter", "etat", "se_deplacer"})  # rien d'autre : ni bras, ni voix, ni geste
    sait_aller_au_lieu = False  # il ne connaît aucun lieu : seulement « avance de tant, à telle vitesse »

    def __init__(self, rclpy: Any, messages: Any, sujets: dict[str, str] | None = None, nom_noeud: str = "leukerbad_pont") -> None:
        self.rclpy, self.msg = rclpy, messages
        self.sujets = {**SUJETS, **(sujets or {})}
        self.nom_noeud = nom_noeud
        # Faux ou vrai : décidé par la CLASSE (le faux ROS 2 du projet), jamais par ce que l'objet dit de lui-même.
        self.vrai_robot = not isinstance(rclpy, FauxRclpy)
        self.repere_du_monde = not self.vrai_robot  # vrai robot : sa position n'est pas calée sur notre plan (à vérifier samedi)
        self._noeud: Any = None
        self._publication: Any = None
        self._position: Any = None
        self._recue_a = 0.0
        self._verrou = threading.Lock()  # le fil de l'arrêt d'urgence publie aussi

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else {"limites": {}, "gestes": []}

    # ---------------------------------------------------------------- la connexion (rien n'est publié)
    def ouvrir(self) -> None:
        if not self.rclpy.ok():
            self.rclpy.init()
        self._noeud = self.rclpy.create_node(self.nom_noeud)
        self._publication = self._noeud.create_publisher(self.msg.Twist, self.sujets["vitesse"], FILE)
        self._noeud.create_subscription(self.msg.Odometry, self.sujets["odometrie"], self._recevoir, FILE)

    def _recevoir(self, message: Any) -> None:
        self._position, self._recue_a = message, time.monotonic()

    def fermer(self) -> None:
        if self._noeud is not None:
            self._noeud.destroy_node()
            self._noeud = None

    def tic(self) -> None:
        if self._noeud is not None:
            with self._verrou:
                self.rclpy.spin_once(self._noeud, timeout_sec=0.0)

    def _fraiche(self) -> Any:
        self.tic()
        if self._position is None or time.monotonic() - self._recue_a > FRAICHEUR_MAX_S:
            raise ConnectionError(f"plus de message du robot sur {self.sujets['odometrie']} depuis plus de {FRAICHEUR_MAX_S:.0f} s")
        return self._position

    def signe_de_vie(self) -> None:
        self._fraiche()

    def lire_etat(self) -> dict[str, Any]:
        odo = self._fraiche()
        p, q = odo.pose.pose.position, odo.pose.pose.orientation
        lin, ang = odo.twist.twist.linear, odo.twist.twist.angular
        return {"batterie_pct": None,  # à vérifier samedi : aucun canal de batterie n'est garanti
                "x": float(p.x), "y": float(p.y),  # à vérifier samedi : unité et repère
                "cap": math.degrees(2 * math.atan2(q.z, q.w)) % 360,  # l'angle autour de l'axe vertical, tiré de l'orientation
                "en_mouvement": math.hypot(lin.x, lin.y) > BOUGE or abs(ang.z) > BOUGE,
                "occupe": False, "objet_tenu": None, "erreurs": [], "arret_urgence": False, "entendu": None}

    # ---------------------------------------------------------------- s'arrêter, recevoir une vitesse
    def _publier(self, vx: float, vy: float, vyaw: float) -> None:
        message = self.msg.Twist()
        message.linear.x, message.linear.y, message.angular.z = float(vx), float(vy), float(vyaw)
        with self._verrou:
            self._publication.publish(message)

    def arreter_mouvement(self) -> None:
        self._publier(0.0, 0.0, 0.0)

    def arret_urgence(self) -> None:
        # PROPOSITION, à décider avec le responsable sécurité : une vitesse nulle. Ce n'est PAS un arrêt confirmé, et
        # il ne remplace JAMAIS le bouton d'arrêt physique (où est-il sur ce robot ? à vérifier samedi).
        self._publier(0.0, 0.0, 0.0)

    def rearmer(self) -> None:
        return None  # une vitesse nulle ne bloque rien dans le robot : rien à lever, rien n'est publié

    def vitesse(self, vx: float, vy: float, vyaw: float) -> None:
        # La vitesse arrive déjà bridée par la carte et par la prise (la plus petite limite gagne).
        self._publier(vx, vy, vyaw)
