"""L'horloge de démonstration : le prototype a sa propre heure, et elle peut sauter (cahier 5.3).

    h = HorlogeDeDemonstration(bus=bus)
    await h.sauter("le soir")                 # jour 1, 19 h 00
    await h.sauter("le lendemain matin")      # jour 2, 7 h 30
    h.etat()                                  # ce que chaque écran affiche : jour, heure, marque « temps accéléré »

- Entre deux sauts, elle avance comme une vraie horloge.
- Elle ne revient jamais en arrière.
- Dès le premier saut, la marque « temps accéléré » s'affiche, et elle reste jusqu'à la fin de la séance.
- Chaque saut part sur le bus (événement « note », source « horloge_clinique ») : la boîte noire l'écrit, et la
  fiche de vérité de la clinique (fiche.py) le compte.
Pourquoi : montrer en cinq minutes une question posée le soir et un résumé lu le lendemain.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import yaml

FICHIER_HEURES = Path(__file__).resolve().parent / "heures_scenario.yaml"
MARQUE = "temps accéléré"
SOURCE = "horloge_clinique"
MINUTES_PAR_JOUR = 24 * 60


class SautRefuse(ValueError):
    """Le saut demandé n'est pas possible (repère inconnu, ou retour en arrière)."""


def _heures() -> dict[str, Any]:
    return yaml.safe_load(FICHIER_HEURES.read_text(encoding="utf-8"))


def reperes() -> dict[str, dict[str, Any]]:
    """Les heures du scénario : nom → {jour, heure}."""
    return {r["nom"]: {"jour": r["jour"], "heure": r["heure"]} for r in _heures()["reperes"]}


def _en_minutes(jour: int, heure: str) -> int:
    h, m = heure.split(":")
    return jour * MINUTES_PAR_JOUR + int(h) * 60 + int(m)


def _en_clair(minutes: int) -> dict[str, Any]:
    jour, reste = divmod(minutes, MINUTES_PAR_JOUR)
    return {"jour": jour, "heure": f"{reste // 60:02d}:{reste % 60:02d}"}


class HorlogeDeDemonstration:
    def __init__(self, bus=None, jour: int | None = None, heure: str | None = None,
                 temps: Callable[[], float] = time.monotonic) -> None:
        donnees = _heures()
        self.bus = bus
        self._temps = temps
        self._base = _en_minutes(jour if jour is not None else donnees["depart"]["jour"],
                                 heure or donnees["depart"]["heure"])  # l'heure du prototype au dernier réglage
        self._t0 = temps()  # le temps réel au dernier réglage
        self._le_soir, self._le_matin = donnees["le_soir"], donnees["le_lendemain_matin"]
        self.sauts: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ lire l'heure
    def _minutes(self) -> int:
        return self._base + int((self._temps() - self._t0) // 60)

    def jour(self) -> int:
        """Le jour de la démonstration (1, 2…). La porte de lecture s'en sert pour « les arrivées du jour »."""
        return self._minutes() // MINUTES_PAR_JOUR

    def etat(self) -> dict[str, Any]:
        """Ce que chaque écran affiche."""
        clair = _en_clair(self._minutes())
        h, m = clair["heure"].split(":")
        texte = f"Jour {clair['jour']} — {int(h)} h {m}"
        accelere = bool(self.sauts)
        return {**clair, "texte": texte + (f" · {MARQUE.upper()}" if accelere else ""), "temps_accelere": accelere,
                "marque": MARQUE if accelere else "", "sauts": len(self.sauts)}

    # ------------------------------------------------------------------ sauter
    def _cible(self, repere: str) -> int:
        maintenant = self._minutes()
        jour = maintenant // MINUTES_PAR_JOUR
        if repere == "le soir":
            cible = _en_minutes(jour, self._le_soir)
            return cible if cible > maintenant else cible + MINUTES_PAR_JOUR
        if repere == "le lendemain matin":
            return _en_minutes(jour + 1, self._le_matin)
        connus = reperes()
        if repere not in connus:
            raise SautRefuse(f"repère inconnu « {repere} ». Connus : le soir, le lendemain matin, " + ", ".join(connus))
        return _en_minutes(connus[repere]["jour"], connus[repere]["heure"])

    async def sauter(self, repere: str) -> dict[str, Any]:
        """Fait sauter l'heure jusqu'à un repère. Rend le nouvel état. Refuse de revenir en arrière."""
        maintenant, cible = self._minutes(), self._cible(repere)
        if cible <= maintenant:
            raise SautRefuse(f"« {repere} » est déjà passé : l'horloge ne revient pas en arrière")
        saut = {"repere": repere, "de": _en_clair(maintenant), "vers": _en_clair(cible), "etiquette": MARQUE}
        self._base, self._t0 = cible, self._temps()
        self.sauts.append(saut)
        if self.bus is not None:
            await self.bus.emettre("note", SOURCE, quoi="saut_horloge", **saut)
        return self.etat()
