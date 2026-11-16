"""Brique 4 — La voix : transformer le texte de la réponse en son.

Une seule forme (`Voix.synthetiser`), plusieurs moteurs (voir branchements/) :
- sherpa_piper : voix Piper lues par sherpa-onnx (Apache-2.0). Le chinois marche tel quel (lexique).
  Les autres langues ont besoin d'un « phonémiseur » (espeak-ng, licence GPL-3.0) : décision de Hiba, pas installé.
- mac_say : la voix intégrée du Mac (commande `say`), sans rien télécharger. Mac seulement, non testé.
- texte : pas de son, seulement les sous-titres à l'écran (mode silence, ou si aucune voix ne marche).
Le robot ne reste jamais muet sans le dire : si une langue n'a pas de voix, on bascule sur une autre voix ou sur l'écran.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np
from pydantic import BaseModel, ConfigDict


class VoixIndisponible(Exception):
    """Cette voix ne peut pas parler cette langue (avec la raison)."""


class Son(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    echantillons: np.ndarray
    taux: int
    duree_calcul_ms: float = 0.0
    moteur: str = ""

    @property
    def duree_s(self) -> float:
        return len(self.echantillons) / self.taux if self.taux else 0.0


class Voix(ABC):
    nom = "voix"

    @abstractmethod
    def langues(self) -> set[str]:
        """Les langues que cette voix sait vraiment dire."""

    @abstractmethod
    def _synthetiser(self, texte: str, langue: str, lent: bool) -> tuple[np.ndarray, int]: ...

    def prechauffer(self) -> None:
        """Charger les voix tout de suite (sinon la première réponse attend le chargement)."""
        for lg in sorted(self.langues()):
            try:
                self.synthetiser("ok", lg)
            except Exception:
                pass

    def synthetiser(self, texte: str, langue: str, lent: bool = False) -> Son | None:
        if langue not in self.langues():
            raise VoixIndisponible(f"{self.nom} : pas de voix pour « {langue} »")
        t0 = time.perf_counter()
        ech, taux = self._synthetiser(texte, langue, lent)
        return Son(echantillons=ech, taux=taux, duree_calcul_ms=round((time.perf_counter() - t0) * 1000, 1), moteur=self.nom)


class VoixTexte(Voix):
    """Aucun son : la réponse n'apparaît qu'à l'écran (mode silence)."""

    nom = "texte"

    def langues(self) -> set[str]:
        return {"fr", "de", "gsw", "it", "en", "zh"}

    def _synthetiser(self, texte, langue, lent):
        return np.zeros(0, dtype="float32"), 16000

    def synthetiser(self, texte: str, langue: str, lent: bool = False) -> Son | None:
        return None


class VoixEnCascade(Voix):
    """Essaie les voix dans l'ordre ; si aucune ne sait la langue, rend None (sous-titres seulement)."""

    def __init__(self, voix: list[Voix]) -> None:
        self.voix = voix
        self.nom = " > ".join(v.nom for v in voix)

    def langues(self) -> set[str]:
        return set().union(*(v.langues() for v in self.voix)) if self.voix else set()

    def _synthetiser(self, texte, langue, lent):  # pragma: no cover - non utilisé
        raise NotImplementedError

    def prechauffer(self) -> None:
        for v in self.voix:
            v.prechauffer()

    def synthetiser(self, texte: str, langue: str, lent: bool = False) -> Son | None:
        for v in self.voix:
            if langue in v.langues():
                try:
                    return v.synthetiser(texte, langue, lent)
                except VoixIndisponible:
                    continue
        return None


def creer_voix(reglages: dict) -> Voix:
    """Fabrique la voix d'après reglages.yaml → voix.parole.moteurs (dans l'ordre de préférence)."""
    moteurs = reglages.get("voix", {}).get("parole", {}).get("moteurs", ["sherpa_piper", "mac_say"])
    liste: list[Voix] = []
    for m in moteurs:
        try:
            if m == "sherpa_piper":
                from .branchements.voix_sherpa_piper import VoixSherpaPiper

                liste.append(VoixSherpaPiper())
            elif m == "mac_say":
                from .branchements.voix_mac_say import VoixMacSay

                liste.append(VoixMacSay())
            elif m == "piper_gpl":  # option éteinte par défaut (GPL-3.0) : voir requirements-piper-gpl.txt
                from .branchements.voix_piper_gpl import VoixPiperGPL

                liste.append(VoixPiperGPL())
        except (ImportError, FileNotFoundError, OSError):
            continue  # moteur absent sur cette machine : on passe au suivant
    return VoixEnCascade(liste)
