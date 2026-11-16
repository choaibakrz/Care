"""Brique 3 — Un FAUX ROS 2, minimal, pour tester le pont sans rien installer.

Testé sur faux robot (c'est lui, le faux robot). Il imite le petit morceau de rclpy dont le pont a besoin
(init, ok, create_node, spin_once, shutdown ; create_publisher, create_subscription, publish, destroy_node),
avec les mêmes noms et arguments que github.com/ros2/rclpy (Apache-2.0, lu le 11.11.2026). Aucun code copié.
Les messages imitent les champs lus dans github.com/ros2/common_interfaces (Twist, Odometry, BatteryState…).

Le pont reconnaît ce faux ROS 2 à sa CLASSE (type(rclpy) is FauxRclpy), jamais à un attribut.
Le faux robot ROS 2 :
- lit les Twist sur /cmd_vel et les OUBLIE après `duree_ordre_s` s'ils ne sont pas répétés (chien de garde simulé) ;
- publie son odomètre, sa batterie et un petit état JSON à chaque spin_once ;
- après son arrêt d'urgence (Bool True), refuse de bouger jusqu'au Bool False ;
- pannes : « muet » (ne publie plus rien : liaison perdue), « arret_ignore ».
Les sujets inventés (/leukerbad/…) n'existent que dans ce faux ROS 2.
"""
from __future__ import annotations

import json
import math
import threading
import time
from collections import Counter
from typing import Any, Callable

from .liaison_ros2 import SUJETS, MessagesROS2

LIMITES_SIMULEES = {"vitesse_max_m_s": 0.5, "portee_max_m": 0.0, "charge_max_kg": 0.0, "force_max_n": 0.0}
GESTES_SIMULES = ["saluer", "applaudir", "incliner"]
PANNES = {"muet": "Le faux robot ne publie plus rien (liaison perdue).",
          "arret_ignore": "Le faux robot ignore l'arrêt d'urgence logiciel."}
DUREES_S = {"geste": 0.6, "parler": 0.4, "regarder": 0.3, "montrer": 0.4}


# ---------------------------------------------------------------- les messages (champs lus dans common_interfaces)
class Vector3:
    def __init__(self) -> None:
        self.x = self.y = self.z = 0.0


class Twist:
    def __init__(self) -> None:
        self.linear, self.angular = Vector3(), Vector3()


class Point(Vector3):
    pass


class Quaternion:
    def __init__(self) -> None:
        self.x = self.y = self.z = 0.0
        self.w = 1.0


class Pose:
    def __init__(self) -> None:
        self.position, self.orientation = Point(), Quaternion()


class PoseWithCovariance:
    def __init__(self) -> None:
        self.pose = Pose()


class TwistWithCovariance:
    def __init__(self) -> None:
        self.twist = Twist()


class Odometry:
    def __init__(self) -> None:
        self.child_frame_id = ""
        self.pose, self.twist = PoseWithCovariance(), TwistWithCovariance()


class BatteryState:
    def __init__(self) -> None:
        self.voltage = 0.0
        self.percentage = math.nan  # de 0 à 1 ; NaN si non mesuré
        self.present = True


class String:
    def __init__(self) -> None:
        self.data = ""


class Bool:
    def __init__(self) -> None:
        self.data = False


MESSAGES = MessagesROS2(Twist=Twist, Odometry=Odometry, BatteryState=BatteryState, String=String, Bool=Bool)


# ---------------------------------------------------------------- le faux robot ROS 2
class FauxRobotROS2:
    def __init__(self, acceleration: float = 1.0, duree_ordre_s: float = 0.3,
                 depart: tuple[float, float, float] = (1.0, 1.0, 0.0)) -> None:
        self.acceleration = acceleration
        self.duree_ordre_s = duree_ordre_s
        self.x, self.y, self.cap = depart
        self.batterie = 1.0
        self.arret_actif = False
        self.pannes: set[str] = set()
        self.recus: Counter[str] = Counter()  # pour les tests : messages reçus par sujet
        self.vitesse_max_vue = 0.0  # pour les tests : la plus grande vitesse demandée (m/s)
        self._v = (0.0, 0.0, 0.0)
        self._fin_ordre = 0.0
        self._tache: tuple[str, float] | None = None
        self._heure = time.monotonic()

    def recevoir(self, sujet: str, msg: Any) -> None:
        self.recus[sujet] += 1
        maintenant = time.monotonic()
        if sujet == SUJETS["arret_urgence"]:
            if msg.data and "arret_ignore" not in self.pannes:
                self.arret_actif, self._v, self._tache = True, (0.0, 0.0, 0.0), None
            elif not msg.data:
                self.arret_actif = False
        elif self.arret_actif:
            return  # arrêt d'urgence : tout ordre est ignoré
        elif sujet == SUJETS["vitesse"]:
            self._v = (msg.linear.x, msg.linear.y, msg.angular.z)
            self._fin_ordre = maintenant + self.duree_ordre_s
            self.vitesse_max_vue = max(self.vitesse_max_vue, math.hypot(msg.linear.x, msg.linear.y))
        else:
            for genre, duree in DUREES_S.items():
                if sujet == SUJETS[genre]:
                    self._tache = (genre, maintenant + duree / self.acceleration)

    def avancer(self) -> None:
        maintenant = time.monotonic()
        precedent, self._heure = self._heure, maintenant
        dt = max(0.0, min(maintenant, self._fin_ordre) - precedent) * self.acceleration  # on bouge jusqu'à l'expiration
        vx, vy, vyaw = (0.0, 0.0, 0.0) if self.arret_actif else self._v
        if self.arret_actif or maintenant > self._fin_ordre:
            self._v = (0.0, 0.0, 0.0)
        r = math.radians(self.cap)
        self.x += (vx * math.cos(r) - vy * math.sin(r)) * dt
        self.y += (vx * math.sin(r) + vy * math.cos(r)) * dt
        self.cap = (self.cap + math.degrees(vyaw * dt)) % 360
        if self._tache and maintenant >= self._tache[1]:
            self._tache = None

    def publications(self) -> list[tuple[str, Any]]:
        if "muet" in self.pannes:
            return []
        odo = Odometry()
        odo.pose.pose.position.x, odo.pose.pose.position.y = self.x, self.y
        odo.pose.pose.orientation.z = math.sin(math.radians(self.cap) / 2)
        odo.pose.pose.orientation.w = math.cos(math.radians(self.cap) / 2)
        odo.twist.twist.linear.x, odo.twist.twist.linear.y, odo.twist.twist.angular.z = self._v
        bat = BatteryState()
        bat.percentage = self.batterie
        etat = String()
        bouge = self._tache is not None and self._tache[0] in ("geste", "montrer")
        etat.data = json.dumps({"occupe": self._tache is not None, "erreurs": [], "arret_urgence": self.arret_actif,
                                "en_mouvement": bouge})
        return [(SUJETS["odometrie"], odo), (SUJETS["batterie"], bat), (SUJETS["etat"], etat)]


# ---------------------------------------------------------------- le faux rclpy
class FauxPublication:
    def __init__(self, rclpy: "FauxRclpy", sujet: str) -> None:
        self._rclpy, self.sujet = rclpy, sujet

    def publish(self, msg: Any) -> None:
        with self._rclpy.verrou:
            self._rclpy.robot.recevoir(self.sujet, msg)


class FauxNoeud:
    def __init__(self, rclpy: "FauxRclpy", nom: str) -> None:
        self._rclpy, self.nom = rclpy, nom
        self.abonnements: dict[str, list[Callable[[Any], None]]] = {}
        self.detruit = False

    def create_publisher(self, msg_type: Any, topic: str, qos_profile: Any) -> FauxPublication:
        return FauxPublication(self._rclpy, topic)

    def create_subscription(self, msg_type: Any, topic: str, callback: Callable[[Any], None], qos_profile: Any) -> object:
        self.abonnements.setdefault(topic, []).append(callback)
        return object()

    def destroy_node(self) -> None:
        self.detruit = True


class FauxRclpy:
    """Se présente comme le module rclpy (le petit morceau utilisé par le pont)."""

    def __init__(self, robot: FauxRobotROS2 | None = None, acceleration: float = 1.0) -> None:
        self.robot = robot or FauxRobotROS2(acceleration=acceleration)
        self.verrou = threading.Lock()
        self._ok = False
        self.noeuds: list[FauxNoeud] = []

    def infos_simulation(self) -> dict:
        return {"limites": dict(LIMITES_SIMULEES), "gestes": list(GESTES_SIMULES)}

    def init(self, *, args: Any = None, context: Any = None, domain_id: Any = None,
             signal_handler_options: Any = None) -> None:
        self._ok = True

    def ok(self, *, context: Any = None) -> bool:
        return self._ok

    def shutdown(self, *, context: Any = None, uninstall_handlers: Any = None) -> None:
        self._ok = False

    def create_node(self, node_name: str, **_: Any) -> FauxNoeud:
        noeud = FauxNoeud(self, node_name)
        self.noeuds.append(noeud)
        return noeud

    def spin_once(self, node: FauxNoeud, *, executor: Any = None, timeout_sec: float | None = None) -> None:
        with self.verrou:
            self.robot.avancer()
            messages = self.robot.publications()
        for sujet, msg in messages:
            for rappel in node.abonnements.get(sujet, []):
                rappel(msg)
