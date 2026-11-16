"""Brique 5 — La prise des yeux : une seule forme, plusieurs « branchements ».

    vue = yeux.voir(image)      → Vue : personnes, objets nommés, marqueurs ArUco, textes lus

Un branchement = un outil qui regarde l'image (MediaPipe, ArUco, RapidOCR, ou la vérité de la caméra simulée).
Un branchement absent (paquet pas installé, modèle manquant) ou en panne : la vue le dit, et les autres continuent.

Positions :
- dans l'image, en pixels (une « boîte » = un rectangle autour de la chose) ;
- au sol, en mètres, si la caméra est calibrée (geometrie.py). Repère « robot » : x devant le robot, y à sa gauche.
  Repère « monde » : celui de commun/monde.yaml (caméra fixe dans la halle).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from .geometrie import Calibration


@dataclass
class ImageCamera:
    """Une image de la caméra. `pixels` : tableau hauteur × largeur × 3, couleurs dans l'ordre rouge, vert, bleu."""

    pixels: np.ndarray
    heure: float  # time.monotonic() au moment de la prise de vue : la fraîcheur se compte depuis là
    source: str  # « camera_simulee », « opencv:0 », « fichier:photo.png »…
    verite: list[dict] | None = None  # caméra SIMULÉE seulement : ce qui a été dessiné (jamais avec une vraie caméra)
    pose: tuple[float, float, float] | None = None  # position du robot (x, y, cap) à la prise de vue, si connue
    photo_fixe: bool = False  # une image lue dans un fichier : vieille, jamais « ce qui est là maintenant »

    @property
    def largeur(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def hauteur(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def simulee(self) -> bool:
        return self.verite is not None


class Boite(BaseModel):
    """Un rectangle dans l'image, en pixels : coin en haut à gauche, largeur, hauteur."""

    x: float
    y: float
    largeur: float
    hauteur: float

    def bas_milieu(self) -> tuple[float, float]:
        """Le point où la chose touche le sol (les pieds d'une personne)."""
        return (self.x + self.largeur / 2, self.y + self.hauteur)

    def milieu(self) -> tuple[float, float]:
        return (self.x + self.largeur / 2, self.y + self.hauteur / 2)


class PointSol(BaseModel):
    x: float
    y: float


class Personne(BaseModel):
    boite: Boite
    confiance: float
    source: str
    sol: PointSol | None = None  # au sol (repère de la calibration) ; None = caméra non calibrée ou point impossible
    pieds_coupes: bool = False  # la boîte touche le bas de l'image : la personne est plus près que ce qu'on voit


class Objet(BaseModel):
    etiquette: str  # le nom donné par l'outil (« bottle »)
    nom: str | None = None  # l'objet du monde (« bouteille »), si on le reconnaît
    boite: Boite
    confiance: float
    source: str
    sol: PointSol | None = None


class Marqueur(BaseModel):
    """Un marqueur ArUco : un carré noir et blanc imprimé, avec un numéro, très facile à retrouver dans une image."""

    numero: int
    coins: list[tuple[float, float]]  # 4 coins dans l'image, dans l'ordre du marqueur (haut-gauche d'abord)
    sorte: Literal["calibration", "lieu", "objet", "inconnu"] = "inconnu"
    nom: str | None = None  # lieu ou objet du monde
    sol: PointSol | None = None

    def centre(self) -> tuple[float, float]:
        c = np.asarray(self.coins, dtype=float)
        return (float(c[:, 0].mean()), float(c[:, 1].mean()))


class Texte(BaseModel):
    texte: str
    boite: Boite
    confiance: float
    lieu: str | None = None  # le texte est le nom d'un lieu du monde (« CUISINE » → cuisine)


class EtatBranchement(BaseModel):
    nom: str
    etat: Literal["ok", "absent", "en_panne", "sans_objet"]
    raison: str = ""
    duree_ms: float = 0.0


class Trouvailles(BaseModel):
    """Ce qu'un branchement a trouvé dans une image."""

    personnes: list[Personne] = Field(default_factory=list)
    objets: list[Objet] = Field(default_factory=list)
    marqueurs: list[Marqueur] = Field(default_factory=list)
    textes: list[Texte] = Field(default_factory=list)


class Vue(Trouvailles):
    heure: float
    source: str
    largeur: int
    hauteur: int
    simulee: bool = False
    photo_fixe: bool = False
    branchements: list[EtatBranchement] = Field(default_factory=list)
    # Vrai seulement si un branchement qui sait voir les personnes a marché sur CETTE image. Sinon, « personne vue »
    # ne veut rien dire : on ne dit rien au gardien (qui demandera un humain).
    personnes_fiables: bool = False
    calibree: bool = False
    repere: str | None = None  # « robot » ou « monde » : le repère des points au sol
    duree_ms: float = 0.0

    def etat(self, nom: str) -> EtatBranchement | None:
        return next((b for b in self.branchements if b.nom == nom), None)


class BranchementInutile(Exception):
    """Ce branchement ne sert à rien pour cette image (ex. la vérité du dessin avec une vraie caméra)."""


class Branchement:
    """Un outil qui regarde l'image. À écrire pour chaque outil (voir branchements/)."""

    nom = "branchement"
    voit_les_personnes = False  # sait repérer les personnes (utile au gardien)
    voit_les_objets = False  # sait trouver un objet nommé (utile au cerveau)
    rapide = True  # assez rapide pour chaque image (sinon : de temps en temps, ex. lire un texte)

    def preparer(self) -> str | None:
        """Charger l'outil. Rend None si tout va bien, sinon la raison (en français simple) de son absence."""
        return None

    def analyser(self, image: ImageCamera) -> Trouvailles:  # pragma: no cover - à écrire par chaque branchement
        raise NotImplementedError


class Yeux:
    """La prise des yeux : passe l'image à chaque branchement prêt, rassemble, et met au sol si la caméra est calibrée."""

    def __init__(self, branchements: list[Branchement], calibration: Calibration | None = None) -> None:
        self.branchements = list(branchements)
        self.calibration = calibration
        self._absents: dict[str, str] = {}
        self._prepares = False

    def preparer(self) -> dict[str, str]:
        """Préparer chaque branchement une fois. Rend {nom: raison} pour ceux qui manquent (le reste continue)."""
        if not self._prepares:
            for b in self.branchements:
                try:
                    raison = b.preparer()
                except Exception as e:  # noqa: BLE001 - un outil cassé ne doit jamais arrêter les yeux
                    raison = f"ne démarre pas : {type(e).__name__}: {e}"
                if raison:
                    self._absents[b.nom] = raison
            self._prepares = True
        return dict(self._absents)

    def prets(self, seulement_rapides: bool | None = None) -> list[Branchement]:
        self.preparer()
        return [b for b in self.branchements if b.nom not in self._absents
                and (seulement_rapides is None or b.rapide == seulement_rapides)]

    def voir(self, image: ImageCamera, rapides: bool | None = None) -> Vue:
        """Regarder une image. `rapides` : True = seulement les branchements rapides, False = seulement les lents,
        None = tous. Ne lève jamais d'erreur à cause d'un branchement : il est noté « en_panne » et on continue."""
        self.preparer()
        t0 = time.monotonic()
        vue = Vue(heure=image.heure, source=image.source, largeur=image.largeur, hauteur=image.hauteur,
                  simulee=image.simulee, photo_fixe=image.photo_fixe)
        for b in self.branchements:
            if rapides is not None and b.rapide != rapides:
                continue
            if b.nom in self._absents:
                vue.branchements.append(EtatBranchement(nom=b.nom, etat="absent", raison=self._absents[b.nom]))
                continue
            t1 = time.monotonic()
            try:
                trouve = b.analyser(image)
            except BranchementInutile as e:
                vue.branchements.append(EtatBranchement(nom=b.nom, etat="sans_objet", raison=str(e)))
                continue
            except Exception as e:  # noqa: BLE001
                vue.branchements.append(EtatBranchement(nom=b.nom, etat="en_panne", raison=f"{type(e).__name__}: {e}",
                                                        duree_ms=_ms(t1)))
                continue
            vue.branchements.append(EtatBranchement(nom=b.nom, etat="ok", duree_ms=_ms(t1)))
            vue.personnes += trouve.personnes
            vue.objets += trouve.objets
            vue.marqueurs += trouve.marqueurs
            vue.textes += trouve.textes
            if b.voit_les_personnes:
                vue.personnes_fiables = True
        self._mettre_au_sol(vue)
        vue.duree_ms = _ms(t0)
        return vue

    def _mettre_au_sol(self, vue: Vue) -> None:
        cal = self.calibration
        for p in vue.personnes:
            p.pieds_coupes = p.boite.y + p.boite.hauteur >= vue.hauteur - 2
        if cal is None:
            return
        vue.calibree, vue.repere = True, cal.repere
        for p in vue.personnes:  # une personne lointaine compte aussi (position moins précise, mais jamais oubliée)
            p.sol = cal.vers_sol(*p.boite.bas_milieu(), vue.largeur, vue.hauteur, limiter=False)
        for o in vue.objets:
            o.sol = cal.vers_sol(*o.boite.bas_milieu(), vue.largeur, vue.hauteur)
        for m in vue.marqueurs:
            m.sol = cal.vers_sol(*m.centre(), vue.largeur, vue.hauteur)


def _ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000, 1)


def normaliser(texte: str) -> str:
    """« Entrée » → « entree » : pour comparer un texte lu avec les noms du monde."""
    import unicodedata

    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if c.isalnum() or c == " ").strip()
