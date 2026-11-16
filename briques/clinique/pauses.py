"""La pause : la main des soignants (avenant jury, tâche J05 ; première moitié : J05a).

Depuis sa tablette, un soignant met en pause une chose que font les robots à son étage : rouler dans le couloir, parler,
livrer, entrer dans une chambre. Il choisit une durée, et une raison dans une courte liste.

    pauses = Pauses(porte, carnet, horloge, bus=bus)
    pauses.mettre(badge_soignant, "rouler", 30, "soin en cours")   # trente minutes de l'horloge de démonstration
    pauses.lever(badge_soignant, numero)                           # ou elle finit seule, à l'heure dite

C'est le GARDIEN qui applique la pause : chaque pause devient des règles que le gardien de l'ossature relit (comme les
cartes de rôle, par `cartes_gardien.py`). La brique 7 n'est pas modifiée.
- rouler dans le couloir : le robot ne va à aucun lieu de l'étage (le gardien dit non) ;
- entrer dans une chambre : le robot ne va dans aucune chambre de l'étage (le gardien dit non) ;
- livrer : le robot ne touche aucun objet de la réserve (le gardien dit non) ;
- parler : le gardien n'a pas de règle « ne parle pas » ; il a « demander d'abord à un humain » : pendant la pause, le
  robot ne parle donc pas sans l'accord d'un humain, et il dit que c'est en pause.
Le refus dit qui a mis la pause et jusqu'à quand. Chaque pause (mise, levée, finie seule) va au carnet et dans la boîte noire.

DIRE VRAI : essayé sur le FAUX ROBOT. Une pause s'applique au robot branché, au prochain geste qu'il demande. Les robots
simulés ne sont pas encore concernés. Une tâche mise en attente par une pause ne repart pas toute seule.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import dossier
from .carnet import Carnet
from .horloge import HorlogeDeDemonstration, _en_clair, _en_minutes
from .porte import Badge, PorteDeLecture

GENRE = "pause"
SOURCE = "clinique"
CHOSES = {"rouler": "rouler dans le couloir", "parler": "parler", "livrer": "livrer", "chambre": "entrer dans une chambre"}
RAISONS = ("soin en cours", "repos", "visite", "autre")
MINUTES_MAX = 240
RAYON_M = 0.3


class Refus(ValueError):
    """Cette pause n'est pas possible. Le message dit pourquoi."""


def _mot(texte: str) -> str:
    sans = "".join(c for c in unicodedata.normalize("NFKD", texte.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sans).strip("_")


def _heure_dite(heure: str) -> str:
    return f"{int(heure[:2])} h {heure[3:]}"


class Pauses:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet, horloge: HorlogeDeDemonstration, bus=None) -> None:
        self.porte, self.carnet, self.horloge, self.bus = porte, carnet, horloge, bus
        self._pauses: list[dict[str, Any]] = []
        self._a_noter: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ l'heure
    def _maintenant(self) -> int:
        etat = self.horloge.etat()
        return _en_minutes(etat["jour"], etat["heure"])

    @staticmethod
    def _quand(minutes: int) -> str:
        clair = _en_clair(minutes)
        return f"jour {clair['jour']}, {clair['heure']}"

    def _noter(self, evenement: str, pause: dict[str, Any], par: str) -> None:
        self._a_noter.append({"quoi": "pause", "evenement": evenement, "numero": pause["numero"], "chose": pause["chose"],
                              "etage": pause["etage"], "par": par, "raison": pause["raison"],
                              "jusqu_a": self._quand(pause["fin"]), "heure": self._quand(self._maintenant())})

    async def ecrire_dans_la_boite(self) -> int:
        """Écrit dans la boîte noire ce qui est arrivé aux pauses et n'y est pas encore. Rend le nombre de notes."""
        self.actives()
        a_ecrire, self._a_noter = self._a_noter, []
        if self.bus is not None:
            for note in a_ecrire:
                await self.bus.emettre("note", SOURCE, **note)
        return len(a_ecrire)

    # ------------------------------------------------------------------ mettre, lever
    def _soignant(self, badge: Badge, quoi: str) -> None:
        if badge.role != "soignant" or badge.etage is None:
            self.porte.refuser(badge, quoi, "seul un soignant met ou lève une pause, pour son étage")

    def mettre(self, badge: Badge, chose: str, minutes: int, raison: str) -> dict[str, Any]:
        self._soignant(badge, "mettre une pause")
        if chose not in CHOSES:
            raise Refus(f"on ne met pas « {chose} » en pause (possibles : {', '.join(CHOSES.values())})")
        if raison not in RAISONS:
            raise Refus(f"raison inconnue « {raison} » (raisons : {', '.join(RAISONS)})")
        if not isinstance(minutes, int) or not 1 <= minutes <= MINUTES_MAX:
            raise Refus(f"la durée va de 1 à {MINUTES_MAX} minutes")
        fin = self._maintenant() + minutes
        clair = _en_clair(fin)
        pause = {"numero": f"pause-{len(self._pauses) + 1}", "chose": chose, "etage": badge.etage, "par": badge.id, "raison": raison,
                 "minutes": minutes, "fin": fin, "jusqu_a": clair, "etat": "en cours"}
        pause["dit"] = (f"en pause : {CHOSES[chose]}, étage {badge.etage} — mise par {badge.id} jusqu'à "
                        f"{_heure_dite(clair['heure'])} ({raison})")
        self._pauses.append(pause)
        self.carnet.ecrire(badge, GENRE, {c: v for c, v in pause.items() if c != "fin"}, valide_par_un_humain=True)
        self._noter("mise", pause, badge.id)
        return dict(pause)

    def lever(self, badge: Badge, numero: str) -> dict[str, Any]:
        self._soignant(badge, "lever une pause")
        pause = next((p for p in self.actives(vue=False) if p["numero"] == numero), None)
        if pause is None:
            raise Refus("cette pause n'existe pas, ou elle est déjà finie")
        if pause["etage"] != badge.etage:
            self.porte.refuser(badge, "lever une pause", "cette pause est celle d'un autre étage")
        pause["etat"] = "levée"
        self.carnet.ecrire(badge, GENRE, {c: v for c, v in pause.items() if c != "fin"}, valide_par_un_humain=True)
        self._noter("levée", pause, badge.id)
        return dict(pause)

    def actives(self, vue: bool = True) -> list[dict[str, Any]]:
        """Les pauses en cours. Une pause dont l'heure est passée finit seule, et c'est noté."""
        maintenant = self._maintenant()
        for pause in self._pauses:
            if pause["etat"] == "en cours" and maintenant >= pause["fin"]:
                pause["etat"] = "finie seule"
                self._noter("finie seule", pause, "l'horloge")
        en_cours = [p for p in self._pauses if p["etat"] == "en cours"]
        return [dict(p) for p in en_cours] if vue else en_cours

    def signature(self) -> tuple[str, ...]:
        return tuple(p["numero"] for p in self.actives())

    # ------------------------------------------------------------------ pour le gardien
    def regles(self, monde) -> list[dict[str, Any]]:
        """Les pauses en cours, en règles que le gardien lit. Chaque phrase dit qui a mis la pause et jusqu'à quand."""
        plan = dossier.charger()
        regles: list[dict[str, Any]] = []
        for p in self.actives():
            tete = (f"Pause ({CHOSES[p['chose']]}) mise par {p['par']} jusqu'à {_heure_dite(p['jusqu_a']['heure'])}, "
                    f"raison : {p['raison']}")
            lieux = [l["nom"] for l in plan.lieux["lieux"] if l["etage"] == p["etage"] and monde.lieu(l["nom"]) is not None]
            if p["chose"] == "chambre":
                lieux = [l for l in lieux if l.startswith("Chambre")]
            if p["chose"] in ("rouler", "chambre"):
                regles += [{"id": f"{p['numero'].replace('-', '_')}_{_mot(lieu)}", "sorte": "zone_interdite", "en_direct": False,
                            "valeurs": {"lieu": lieu, "rayon_m": RAYON_M},
                            "phrase": f"{tete} : le robot ne va pas à « {lieu} »."} for lieu in lieux]
            elif p["chose"] == "livrer":
                objets = [o["nom"] for o in plan.reserve if monde.objet(o["nom"]) is not None]
                regles.append({"id": f"{p['numero'].replace('-', '_')}_objets", "sorte": "objets_interdits", "en_direct": False,
                               "valeurs": {"objets": objets},
                               "phrase": f"{tete} : le robot ne touche pas : {', '.join(objets)}."})
            else:  # parler : le gardien demande d'abord l'accord d'un humain
                regles.append({"id": f"{p['numero'].replace('-', '_')}_parler", "sorte": "demander_humain", "en_direct": False,
                               "valeurs": {"actions": ["parler"]},
                               "phrase": f"{tete} : pour parler, le robot demande d'abord à un humain."})
        return regles

    def dire_pour(self, regles: list[str | None]) -> str | None:
        """Le gardien a refusé à cause de ces règles : si l'une vient d'une pause, la phrase qui dit qui et jusqu'à quand."""
        for ident in regles:
            for p in self._pauses:
                if ident and ident.startswith(p["numero"].replace("-", "_") + "_"):
                    return p["dit"]
        return None
