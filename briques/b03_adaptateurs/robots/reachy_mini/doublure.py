"""Une DOUBLURE à la place du Reachy Mini : un faux programme de fond, pour essayer l'ébauche sans robot et sans kit.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot (c'est elle, le faux robot).

C'est le FAUX KIT du projet (briques/b03_adaptateurs/chemins/sdk/faux_sdk.py), habillé avec les ADRESSES WEB du
programme de fond du Reachy Mini, lues en ligne le 14.11.2026 (github.com/pollen-robotics/reachy_mini,
src/reachy_mini/daemon/app/routers/) : /api/daemon/status, /api/move/running, /api/state/full, /api/move/stop,
/api/motors/set_mode/disabled, /api/motors/set_mode/enabled, /api/move/goto. Elle répond par get() et post(), comme
le petit client web de la liaison.
Elle imite ce qui a été lu chez le fabricant :
- /api/state/full ne rend les articulations de la tête que si on les demande (« with_head_joints=true ») ;
- la liste des mouvements en cours ne montre PAS tous les mouvements (`mouvement_invisible`) ;
- arrêter un mouvement déjà fini rend une erreur ; une adresse inconnue rend une erreur ;
- couper les moteurs n'enlève pas les mouvements de la liste.
Elle imite aussi ce qui a été VU le 15.11.2026 sur le programme du fabricant en mode simulé (version 1.14.0) :
- un ordre de tête (/api/move/goto) rend un « uuid » et dure le temps demandé ; il est dans la liste tant qu'il joue ;
- un ordre de tête envoyé pendant qu'un autre joue est PERDU SANS LE DIRE (un « uuid » est rendu quand même) ;
- une cible trop loin n'est pas refusée : elle est ramenée à 67° de côté et 34° de haut-bas ;
- une durée nulle est acceptée ; arrêter un mouvement le fige à peu près sur place.
Tout le reste est INVENTÉ et ne dit rien du vrai robot : elle répond tout de suite, sa tête ne s'affaisse pas, elle
avance en ligne droite, et, moteurs coupés, sa tête ne bouge plus (le faux robot du fabricant, lui, bouge quand même).
La liaison reconnaît la doublure à sa CLASSE (un faux kit du projet), jamais à ce qu'elle dit.
"""
from __future__ import annotations

import time
import urllib.parse
import uuid as module_uuid
from typing import Any

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit


class DoublureReachyMini(FauxKit):
    def __init__(self, acceleration: float = 1.0) -> None:
        super().__init__(acceleration=acceleration)
        self.appels_du_kit: list[tuple[str, str, Any]] = []  # pour les essais : (GET ou POST, adresse, corps), dans l'ordre
        self.etat_du_fond: Any = "running"  # pour les essais : not_initialized, starting, running, stopping, stopped, error (lu)
        self.erreur_du_fond: str | None = None
        self.erreur_du_materiel: str | None = None
        self.pret = True  # pour les essais : les moteurs répondent-ils au programme de fond ?
        self.mode: Any = "enabled"  # pour les essais : enabled, disabled, gravity_compensation (lu)
        self.mouvements: list[str] = []  # pour les essais : les « uuid » des mouvements que la liste montre
        self.mouvement_invisible = False  # pour les essais : un mouvement que la liste ne montre pas (lu : réveil, geste du kit…)
        self.tete = [0.0] * 7  # sept articulations de la tête (lu : 7 nombres)
        self.corps, self.antennes = 0.0, [0.0, 0.0]
        self.pas = 0.01  # de combien la tête avance à chaque lecture quand un mouvement est en cours (inventé)
        self.pousse = 0.0  # pour les essais : quelqu'un pousse la tête à la main, de tant à chaque lecture
        self.lacet, self.tangage = 0.0, 0.0  # où regarde la tête, en radians (tête droite au départ : inventé)
        self.roulis, self.hauteur = 0.0, 0.0  # pour les essais : une tête penchée, ou couchée (z en mètres)
        self.glisse_s = 0.0  # pour les essais : après un arrêt, la tête glisse encore pendant ce temps (vu : un instant)
        self._glisse_jusqu_a = 0.0
        self.ordres_de_tete: list[dict] = []  # pour les essais : chaque ordre de tête VRAIMENT joué (cible, durée)
        self.ordres_perdus = 0  # pour les essais : les ordres de tête arrivés pendant qu'un autre jouait (vu : perdus)
        self.refuser_la_tete = False  # pour les essais : le programme de fond refuse l'ordre de tête (code 500)
        self._ordre: dict | None = None  # l'ordre de tête en cours : uuid, départ, cible, heures de début et de fin
        self.refuser_d_allumer = False  # pour les essais : le programme de fond n'allume pas les moteurs

    def endormir(self) -> None:
        """Pour les essais : la tête couchée, moteurs coupés, comme au démarrage du programme du fabricant SANS réveil
        (pose vue sur son simulateur le 15.11.2026 ; les moteurs coupés au démarrage : lu dans son code, à vérifier)."""
        self.lacet, self.tangage, self.roulis, self.hauteur = -0.0047, 0.538, 0.0013, -0.0504
        self.antennes, self.mode = [-3.05, 3.05], "disabled"

    saut_a_l_allumage = 0.0  # pour les essais : de combien la tête saute quand on rallume (lu : possible chez le fabricant)

    def _la_tete_avance(self) -> None:
        autres = [uuid for uuid in self.mouvements if not (self._ordre and uuid == self._ordre["uuid"])]
        if self.mode != "disabled" and (autres or self.mouvement_invisible or time.monotonic() < self._glisse_jusqu_a):
            self.tete[0] += self.pas
        self.tete[0] += self.pousse

    def _l_ordre_avance(self) -> None:
        """L'ordre de tête en cours avance avec l'heure (en ligne droite : inventé). Fini : il sort de la liste."""
        ordre = self._ordre
        if ordre is None:
            return
        maintenant = time.monotonic()
        part = 1.0 if ordre["fin"] <= ordre["debut"] else min(1.0, (maintenant - ordre["debut"]) / (ordre["fin"] - ordre["debut"]))
        if self.mode != "disabled":  # inventé : moteurs coupés, la tête ne suit plus l'ordre
            self.lacet, self.tangage, self.roulis, self.hauteur = (
                depart + (cible - depart) * part for depart, cible in zip(ordre["depart"], ordre["cible"]))
            if part >= 1.0 and ordre.get("antennes") is not None:
                self.antennes = list(ordre["antennes"])
        if part >= 1.0:
            if ordre["uuid"] in self.mouvements:
                self.mouvements.remove(ordre["uuid"])
            self._ordre = None

    def get(self, chemin: str) -> Any:
        self._trajet()  # une panne « coupure » du faux kit lève ConnectionError, comme un robot injoignable
        adresse, _, question = chemin.partition("?")
        self.appels_du_kit.append(("GET", adresse, None))
        with self._verrou:
            self._arrivee("lire")
            if adresse == "/api/daemon/status":  # lu : répond même si le robot n'est pas démarré
                return {"state": self.etat_du_fond, "error": self.erreur_du_fond, "simulation_enabled": True,
                        "backend_status": {"ready": self.pret, "motor_control_mode": self.mode, "last_alive": 0.0,
                                           "error": self.erreur_du_materiel}}
            if not self.pret:
                raise ConnectionError(f"le Reachy Mini ne donne pas {adresse} : code 503 Backend not running")
            self._l_ordre_avance()
            if adresse == "/api/move/running":
                return [{"uuid": uuid} for uuid in self.mouvements]
            if adresse == "/api/state/full":
                demande = urllib.parse.parse_qs(question)
                avec_la_tete = demande.get("with_head_joints", ["false"])[0] == "true"  # lu : absent par défaut
                avec_la_pose = demande.get("with_head_pose", ["true"])[0] == "true"  # lu : présente par défaut
                self._la_tete_avance()
                articulations = [self.tete[0] + self.lacet, self.tete[1] + self.tangage] + list(self.tete[2:])
                pose = {"x": 0.0, "y": 0.0, "z": self.hauteur, "roll": self.roulis, "pitch": self.tangage, "yaw": self.lacet}
                return {"control_mode": self.mode, "head_pose": pose if avec_la_pose else None,
                        "head_joints": articulations if avec_la_tete else None,
                        "body_yaw": self.corps, "antennas_position": list(self.antennes)}
        raise ConnectionError(f"le Reachy Mini ne donne pas {adresse} : code 404")

    def post(self, chemin: str, corps: dict | None = None, delai_s: float | None = None) -> Any:
        self._trajet()
        adresse = chemin.split("?")[0]
        self.appels_du_kit.append(("POST", adresse, corps))
        self._l_ordre_avance()
        if adresse == "/api/move/goto":
            if not self.pret:
                raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 503")
            if self.refuser_la_tete or "refus" in self.pannes:
                raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 500")
            try:
                duree = float((corps or {})["duration"])
                pose = (corps or {}).get("head_pose") or {}
                cible = (float(pose.get("yaw", 0.0)), float(pose.get("pitch", 0.0)), float(pose.get("roll", 0.0)),
                         float(pose.get("z", 0.0)))
                antennes = (corps or {}).get("antennas")
            except (TypeError, KeyError, ValueError):
                raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 422") from None
            nouveau = str(module_uuid.uuid4())
            # Vu : un ordre arrivé pendant qu'un autre joue est perdu sans le dire. Lu : aussi quand l'autre mouvement
            # vient d'un autre chemin que les adresses web, et que la liste ne le montre pas (`mouvement_invisible`).
            if self.mouvements or self._ordre or self.mouvement_invisible:
                self.ordres_perdus += 1
                return {"uuid": nouveau}
            cible = (min(max(cible[0], -1.178), 1.178), min(max(cible[1], -0.589), 0.589), cible[2], cible[3])  # vu : ramené
            maintenant = time.monotonic()
            self._ordre = {"uuid": nouveau, "depart": (self.lacet, self.tangage, self.roulis, self.hauteur), "cible": cible,
                           "antennes": antennes, "debut": maintenant, "fin": maintenant + max(0.0, duree) / self.acceleration}
            self.mouvements.append(nouveau)
            self.ordres_de_tete.append({"lacet": cible[0], "tangage": cible[1], "hauteur": cible[3], "duree_s": duree})
            return {"uuid": nouveau}
        if adresse == "/api/move/stop":
            uuid = (corps or {}).get("uuid")
            if uuid not in self.mouvements:  # lu : un mouvement déjà fini rend une erreur
                raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 500")
            self.mouvements.remove(uuid)
            if self._ordre and self._ordre["uuid"] == uuid:
                self._ordre = None  # vu : arrêté, il se fige à peu près sur place
                self._glisse_jusqu_a = time.monotonic() + self.glisse_s / self.acceleration
            self.stop()  # l'arrêt normal du faux kit
            return {"message": f"Stopped move with UUID: {uuid}"}
        if adresse == "/api/motors/set_mode/enabled":
            if not self.pret or self.refuser_d_allumer:
                raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 503")
            if not self.refuser_d_allumer:
                self.mode = "enabled"  # lu : les moteurs tiennent la position du moment, la tête ne saute pas
                self.tangage -= self.saut_a_l_allumage
            return {"status": "ok"}
        if adresse == "/api/motors/set_mode/disabled":
            if not self.pret:
                raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 503")
            self.mode = "disabled"  # lu : les mouvements restent dans la liste ; les moteurs n'ont plus de force
            self.arreter_en_urgence()  # l'arrêt d'urgence du faux kit
            return {"status": "ok"}
        raise ActionImpossible("robot_refuse", f"le Reachy Mini refuse POST {adresse} : code 404")
