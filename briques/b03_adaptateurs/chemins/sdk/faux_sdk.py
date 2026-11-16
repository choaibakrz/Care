"""Brique 3 — Un FAUX kit de fabricant (faux SDK), minimal, pour tester le chemin « SDK » sans rien installer.

Testé sur faux robot (c'est lui, le faux robot). Les noms des fonctions ci-dessous sont INVENTÉS pour ce faux kit :
ce ne sont PAS ceux d'un vrai fabricant. Les vrais noms lus dans les docs publiques (Unitree, Flexiv, AGIBOT) sont dans
briques/b03_adaptateurs/fiches/, avec l'adresse et la date de lecture. Les chiffres de limites sont inventés.
La liaison reconnaît ce faux kit à sa CLASSE (type(kit) is FauxKit), jamais à un attribut qu'il dirait de lui-même.

Comme beaucoup de vrais kits (à vérifier pour chacun), ce faux kit :
- rend un code (0 = bien, autre chose = refus) ;
- est appelé depuis un autre fil (thread), avec un temps de trajet réglable (`latence_s`, et `latence_vitesse_s` pour
  les seuls ordres de vitesse : un ordre parti avant un arrêt peut arriver après lui), et peut être lent ou muet ;
- OUBLIE un ordre de vitesse après `duree_ordre_s` s'il n'est pas répété : le chien de garde du fabricant, simulé
  (Unitree G1 : 1 s d'après son code, voir fiches/) ;
- `arret_bloquant=True` : après son arrêt d'urgence, il refuse de bouger jusqu'à lever_arret().
  `arret_bloquant=False` : arrêt qui NE BLOQUE PAS (vitesse nulle, puis il accepte de nouveau les ordres), comme un
  « arrêt de marche » (Unitree StopMove) : le cas le plus dur pour un adaptateur.
"""
from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque

LIMITES_SIMULEES = {"vitesse_max_m_s": 0.5, "portee_max_m": 0.6, "charge_max_kg": 1.0, "force_max_n": 20.0}
GESTES_SIMULES = ["saluer", "applaudir", "incliner"]
PANNES = {
    "coupure": "Le faux kit ne répond plus du tout (câble ou Wi-Fi coupé).",
    "lenteur": "Chaque appel prend 0,3 s de plus.",
    "refus": "Le faux kit refuse tout nouvel ordre de mouvement (code 3).",
    "arret_ignore": "Le faux kit ignore l'arrêt d'urgence logiciel (seul le bouton physique marcherait).",
}
OK, REFUSE, ARRET_ACTIF = 0, 3, 7
DUREES_S = {"parler": 0.4, "geste": 0.6, "regarder": 0.3, "montrer": 0.4, "saisir": 0.5, "poser": 0.4}


class FauxKit:
    """Le faux robot vu à travers un faux kit. L'état est protégé par un verrou : on peut l'appeler de plusieurs fils."""

    def __init__(self, acceleration: float = 1.0, duree_ordre_s: float = 0.3, arret_bloquant: bool = True,
                 latence_s: float = 0.0, latence_vitesse_s: float = 0.0,
                 depart: tuple[float, float, float] = (1.0, 1.0, 0.0)) -> None:
        self._verrou = threading.Lock()
        self.acceleration = acceleration
        self.duree_ordre_s = duree_ordre_s  # chien de garde simulé du fabricant
        self.arret_bloquant = arret_bloquant
        self.latence_s = latence_s  # temps de trajet de chaque appel (réseau), hors du verrou
        # En plus, pour les ordres de vitesse seulement : un ordre parti AVANT un arrêt peut arriver APRÈS lui
        # (autre canal, réessai du réseau…). C'est le cas le plus dur pour l'arrêt d'urgence.
        self.latence_vitesse_s = latence_vitesse_s
        self.x, self.y, self.cap = depart  # même départ que le faux monde (commun/monde.yaml)
        self.batterie = 100.0
        self.connecte = False
        self.arret_actif = False
        self.pannes: set[str] = set()
        self.appels: Counter[str] = Counter()  # pour les tests : combien de fois chaque fonction a été appelée
        self.journal: deque[tuple[float, str]] = deque(maxlen=2000)  # pour les tests : (heure, fonction), ordre d'ARRIVÉE
        self.ordre_en_route = threading.Event()  # pour les tests : levé quand un ordre de vitesse part vers le robot
        self.vitesse_max_vue = 0.0  # pour les tests : la plus grande vitesse demandée (m/s)
        self.objet_tenu: str | None = None
        self.entendu = ""
        self._v = (0.0, 0.0, 0.0)
        self._fin_ordre = 0.0
        self._tache: tuple[str, float, str] | None = None  # (genre, heure de fin, détail)
        self._heure = time.monotonic()

    # ---------------------------------------------------------------- pannes (tests et entraînement)
    def provoquer_panne(self, nom: str) -> None:
        if nom not in PANNES:
            raise ValueError(f"Panne inconnue : {nom}. Connues : {list(PANNES)}")
        self.pannes.add(nom)

    def reparer(self) -> None:
        self.pannes.clear()

    def infos_simulation(self) -> dict:
        return {"limites": dict(LIMITES_SIMULEES), "gestes": list(GESTES_SIMULES)}

    # ---------------------------------------------------------------- simulation
    def _trajet(self) -> None:
        """Le trajet de l'appel vers le robot (hors du verrou)."""
        if "coupure" in self.pannes:
            raise ConnectionError("faux kit : liaison coupée (panne provoquée)")
        time.sleep(self.latence_s + (0.3 if "lenteur" in self.pannes else 0.0))

    def _arrivee(self, nom: str) -> None:
        """L'appel arrive au robot (sous le verrou)."""
        self.appels[nom] += 1
        self.journal.append((time.monotonic(), nom))
        self._avancer()

    def _avancer(self) -> None:
        maintenant = time.monotonic()
        precedent, self._heure = self._heure, maintenant
        dt = max(0.0, min(maintenant, self._fin_ordre) - precedent) * self.acceleration  # on bouge jusqu'à l'expiration
        vx, vy, vyaw = self._v
        if maintenant > self._fin_ordre:
            self._v = (0.0, 0.0, 0.0)  # ordre expiré : le chien de garde du « fabricant » arrête le robot
        if vx or vy or vyaw:
            r = math.radians(self.cap)
            self.x += (vx * math.cos(r) - vy * math.sin(r)) * dt
            self.y += (vx * math.sin(r) + vy * math.cos(r)) * dt
            self.cap = (self.cap + math.degrees(vyaw * dt)) % 360
            self.batterie = max(0.0, self.batterie - 0.01 * dt)
        if self._tache and maintenant >= self._tache[1]:
            genre, _, detail = self._tache
            if genre == "saisir":
                self.objet_tenu = detail
            elif genre == "poser":
                self.objet_tenu = None
            elif genre == "ecouter":
                self.entendu = "(faux micro : rien entendu)"
            self._tache = None

    def _bouger_permis(self) -> int:
        if self.arret_actif:
            return ARRET_ACTIF
        if "refus" in self.pannes:
            return REFUSE
        return OK

    def _lancer(self, genre: str, duree_s: float, detail: str = "") -> int:
        code = self._bouger_permis()
        if code == OK:
            self._tache = (genre, time.monotonic() + duree_s / self.acceleration, detail)
        return code

    def _tout_stopper(self) -> None:
        self._avancer()
        self._v, self._tache, self._fin_ordre = (0.0, 0.0, 0.0), None, 0.0

    # ---------------------------------------------------------------- le « kit » (noms inventés)
    def ouvrir_liaison(self) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("ouvrir_liaison")
            self.connecte = True
            return OK

    def fermer(self) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("fermer")
            self.connecte = False
            return OK

    def ping(self) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("ping")
            return OK

    def lire(self) -> dict:
        self._trajet()
        with self._verrou:
            self._arrivee("lire")
            bouge = any(self._v) or (self._tache is not None and self._tache[0] in ("geste", "montrer", "saisir", "poser"))
            return {"batterie_pct": round(self.batterie, 1), "x": self.x, "y": self.y, "cap": self.cap,
                    "en_mouvement": bouge, "occupe": self._tache is not None, "objet_tenu": self.objet_tenu,
                    "erreurs": [], "arret_urgence": self.arret_actif, "entendu": self.entendu}

    def vitesse(self, vx: float, vy: float, vyaw: float) -> int:
        self.ordre_en_route.set()
        time.sleep(self.latence_vitesse_s)
        self._trajet()
        with self._verrou:
            self._arrivee("vitesse")
            code = self._bouger_permis()
            if code == OK:
                self._v = (float(vx), float(vy), float(vyaw))
                self._fin_ordre = time.monotonic() + self.duree_ordre_s
                self.vitesse_max_vue = max(self.vitesse_max_vue, math.hypot(vx, vy))
            return code

    def stop(self) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("stop")
            self._tout_stopper()
            return OK

    def arreter_en_urgence(self) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("arreter_en_urgence")
            if "arret_ignore" not in self.pannes:
                self._tout_stopper()
                self.arret_actif = self.arret_bloquant
            return OK

    def lever_arret(self) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("lever_arret")
            self.arret_actif = False
            return OK

    def dire(self, texte: str, langue: str) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("dire")
            return self._lancer("parler", DUREES_S["parler"], texte)

    def ecouter(self, duree_s: float) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("ecouter")
            self.entendu = ""
            return self._lancer("ecouter", duree_s)

    def tourner_tete(self, cible: str) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("tourner_tete")
            return self._lancer("regarder", DUREES_S["regarder"], cible)

    def pointer(self, cible: str) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("pointer")
            return self._lancer("montrer", DUREES_S["montrer"], cible)

    def jouer_geste(self, nom: str, vitesse_relative: float) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("jouer_geste")
            return self._lancer("geste", DUREES_S["geste"] / max(vitesse_relative, 0.1), nom)

    def prendre(self, objet: str, force_n: float) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("prendre")
            return self._lancer("saisir", DUREES_S["saisir"], objet)

    def lacher(self, lieu: str) -> int:
        self._trajet()
        with self._verrou:
            self._arrivee("lacher")
            return self._lancer("poser", DUREES_S["poser"], lieu)
