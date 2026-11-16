"""Brique 5 — Du pixel au sol : la calibration.

Une « homographie » est un tableau de 3 × 3 nombres qui transforme un point de l'image (pixels) en un point d'un plan
(ici le sol, en mètres). Elle n'est juste que pour ce qui TOUCHE le sol (les pieds, un marqueur posé par terre) et
seulement tant que la caméra ne bouge pas par rapport au robot (une tête qui tourne = calibration fausse).

On la calcule avec un ou plusieurs marqueurs ArUco posés au sol à un endroit mesuré (calibrer.py, GUIDE.md).
Calcul en numpy seulement : pas besoin d'OpenCV ici.
"""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import yaml
from pydantic import BaseModel, Field

EPS = 1e-9


def homographie(points_image: Iterable, points_sol: Iterable) -> np.ndarray:
    """L'homographie qui envoie les points de l'image sur les points du sol (au moins 4, jamais 3 alignés).
    Méthode « DLT normalisée » (transformation linéaire directe) : un petit calcul d'algèbre, sans OpenCV."""
    src = np.asarray(list(points_image), dtype=float).reshape(-1, 2)
    dst = np.asarray(list(points_sol), dtype=float).reshape(-1, 2)
    if len(src) != len(dst) or len(src) < 4:
        raise ValueError("Il faut au moins 4 points dans l'image et autant au sol.")
    if not (np.isfinite(src).all() and np.isfinite(dst).all()):
        raise ValueError("Un point n'est pas un nombre valable.")
    ts, td = _normalisation(src), _normalisation(dst)
    ps, pd = _appliquer_brut(ts, src), _appliquer_brut(td, dst)
    lignes = []
    for (x, y), (u, v) in zip(ps, pd):
        lignes.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        lignes.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, valeurs, vt = np.linalg.svd(np.asarray(lignes))
    if valeurs[-2] < 1e-8 * valeurs[0]:
        raise ValueError("Points mal placés (alignés ou confondus) : impossible de calibrer.")
    h = np.linalg.inv(td) @ vt[-1].reshape(3, 3) @ ts
    h = h / (np.linalg.norm(h) or 1.0)
    w = (h @ np.c_[src, np.ones(len(src))].T)[2]
    if np.median(w) < 0:  # le signe est libre : on le choisit pour que les points du sol soient « devant »
        h = -h
    return h


def _normalisation(p: np.ndarray) -> np.ndarray:
    c = p.mean(axis=0)
    d = float(np.sqrt(((p - c) ** 2).sum(axis=1)).mean())
    s = math.sqrt(2) / d if d > EPS else 1.0
    return np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])


def _appliquer_brut(h: np.ndarray, p: np.ndarray) -> np.ndarray:
    q = h @ np.c_[p, np.ones(len(p))].T
    return (q[:2] / q[2]).T


def appliquer(h: np.ndarray, points: Iterable) -> tuple[np.ndarray, np.ndarray]:
    """Rend (points transformés, valables). Un point de l'image au-dessus de l'horizon ne touche pas le sol :
    il est marqué non valable (et vaut NaN)."""
    p = np.asarray(list(points) if not isinstance(points, np.ndarray) else points, dtype=float).reshape(-1, 2)
    q = h @ np.c_[p, np.ones(len(p))].T
    valables = q[2] > EPS
    sortie = np.full((len(p), 2), np.nan)
    sortie[valables] = (q[:2, valables] / q[2, valables]).T
    return sortie, valables


def robot_vers_monde(pose: tuple[float, float, float], x: float, y: float) -> tuple[float, float]:
    """Un point du repère du robot (x devant, y à gauche) vers le monde (pose = x, y, cap en degrés du robot)."""
    px, py, cap = pose
    c, s = math.cos(math.radians(cap)), math.sin(math.radians(cap))
    return (px + x * c - y * s, py + x * s + y * c)


def monde_vers_robot(pose: tuple[float, float, float], x: float, y: float) -> tuple[float, float]:
    px, py, cap = pose
    c, s = math.cos(math.radians(cap)), math.sin(math.radians(cap))
    dx, dy = x - px, y - py
    return (dx * c + dy * s, -dx * s + dy * c)


class PlacementMarqueur(BaseModel):
    """Où un marqueur de calibration est posé au sol (mesuré au mètre ruban).
    Repère « robot » : x = devant le robot (depuis son centre), y = vers sa gauche. `cap_deg` = direction vers
    laquelle pointe le HAUT du marqueur imprimé (0 = vers l'avant du robot, le texte du numéro lisible depuis le robot)."""

    numero: int
    x: float
    y: float = 0.0
    taille_m: float = Field(0.20, gt=0)
    cap_deg: float = 0.0

    def coins(self) -> list[tuple[float, float]]:
        """Les 4 coins au sol, dans l'ordre d'ArUco : haut-gauche, haut-droit, bas-droit, bas-gauche."""
        a = (math.cos(math.radians(self.cap_deg)), math.sin(math.radians(self.cap_deg)))  # vers le haut du marqueur
        d = (a[1], -a[0])  # vers la droite du marqueur (vu de dessus)
        h = self.taille_m / 2
        return [(self.x + h * a[0] + s * h * d[0], self.y + h * a[1] + s * h * d[1]) for s in (-1, 1)] + \
               [(self.x - h * a[0] + s * h * d[0], self.y - h * a[1] + s * h * d[1]) for s in (1, -1)]


class Calibration(BaseModel):
    """Ce qu'il faut pour passer du pixel au sol. Enregistrée en YAML (lisible)."""

    repere: Literal["robot", "monde"] = "robot"
    homographie: list[list[float]]
    largeur: int  # taille de l'image au moment de la calibration
    hauteur: int
    portee_m: float = 6.0  # au-delà (repère robot), un point au sol n'est pas assez précis : ignoré
    source: str = ""
    date: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    erreur_m: float | None = None  # erreur moyenne sur les coins des marqueurs (None = un seul marqueur : pas de contrôle)
    marqueurs: list[PlacementMarqueur] = Field(default_factory=list)

    def matrice(self) -> np.ndarray:
        return np.asarray(self.homographie, dtype=float)

    def _echelle(self, largeur: int, hauteur: int) -> tuple[float, float]:
        return (self.largeur / largeur if largeur else 1.0, self.hauteur / hauteur if hauteur else 1.0)

    def vers_sol(self, u: float, v: float, largeur: int | None = None, hauteur: int | None = None,
                 limiter: bool = True):
        """Un pixel → un point au sol (PointSol), ou None (au-dessus de l'horizon, valeur fausse, et, si `limiter`,
        plus loin que la portée). Sans limite : un point lointain est rendu quand même (peu précis)."""
        from .prise_yeux import PointSol

        sx, sy = self._echelle(largeur or self.largeur, hauteur or self.hauteur)
        if not (math.isfinite(u) and math.isfinite(v)):
            return None
        pts, ok = appliquer(self.matrice(), [(u * sx, v * sy)])
        if not ok[0]:
            return None
        x, y = float(pts[0, 0]), float(pts[0, 1])
        if self.repere == "robot" and limiter and math.hypot(x, y) > self.portee_m:
            return None  # trop loin : pas assez précis (derrière la caméra : déjà exclu, le point ne touche pas le sol)
        return PointSol(x=round(x, 3), y=round(y, 3))

    def vers_image(self, x: float, y: float, largeur: int | None = None, hauteur: int | None = None):
        """Un point au sol → le pixel où on le voit, ou None s'il est derrière la caméra."""
        sx, sy = self._echelle(largeur or self.largeur, hauteur or self.hauteur)
        pts, ok = appliquer(np.linalg.inv(self.matrice()), [(x, y)])
        if not ok[0]:
            return None
        return (float(pts[0, 0]) / sx, float(pts[0, 1]) / sy)

    def voit(self, x: float, y: float, marge_bord: float = 0.0) -> bool:
        """Ce point du sol est-il dans le champ de la caméra (et assez près) ? Utile pour savoir ce qu'elle NE voit PAS.
        Derrière la caméra, à côté, et l'angle mort au pied de la caméra (sous le bas de l'image) : non.
        `marge_bord` : part de l'image retirée sur les côtés et en bas (une personne au bord peut être manquée)."""
        if self.repere == "robot" and math.hypot(x, y) > self.portee_m:
            return False
        pixel = self.vers_image(x, y)
        if pixel is None:
            return False
        u, v = pixel
        mx, my = self.largeur * marge_bord, self.hauteur * marge_bord
        if not (mx <= u < self.largeur - mx and 0 <= v < self.hauteur - my):
            return False
        retour = self.vers_sol(u, v)  # le point de l'image redonne-t-il bien un point du sol (pas au-dessus de l'horizon) ?
        return retour is not None and math.hypot(retour.x - x, retour.y - y) < 0.05 + 0.02 * math.hypot(x, y)

    def enregistrer(self, chemin: str | Path) -> Path:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        entete = ("# Calibration des yeux (brique 5) : du pixel au sol. Écrite par briques/b05_yeux/calibrer.py.\n"
                  "# Refaire si la caméra bouge par rapport au robot, ou si on change de caméra.\n")
        chemin.write_text(entete + yaml.safe_dump(self.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8")
        return chemin

    @classmethod
    def charger(cls, chemin: str | Path) -> "Calibration":
        cal = cls.model_validate(yaml.safe_load(Path(chemin).read_text(encoding="utf-8")))
        m = cal.matrice()
        if m.shape != (3, 3) or not np.isfinite(m).all() or abs(np.linalg.det(m)) < 1e-15:
            raise ValueError(f"Calibration abîmée : {chemin}")
        return cal


def calibrer(marqueurs_vus: Iterable, placements: Iterable[PlacementMarqueur], largeur: int, hauteur: int,
             repere: Literal["robot", "monde"] = "robot", source: str = "", portee_m: float = 6.0) -> Calibration:
    """Calcule la calibration à partir des marqueurs vus dans une image (leurs 4 coins) et de leur place au sol.
    Un marqueur suffit (4 coins) ; avec deux ou plus, on mesure aussi l'erreur (en mètres)."""
    places = {p.numero: p for p in placements}
    img, sol, utilises = [], [], []
    for m in marqueurs_vus:
        p = places.get(m.numero)
        if p is None:
            continue
        img += [tuple(c) for c in m.coins]
        sol += p.coins()
        utilises.append(p)
    if not utilises:
        attendus = ", ".join(str(n) for n in places) or "aucun"
        raise ValueError(f"Aucun marqueur de calibration vu (attendus : {attendus}). Le marqueur est-il en entier dans l'image ?")
    h = homographie(img, sol)
    erreur = None
    if len(utilises) > 1:
        calcule, ok = appliquer(h, img)
        erreur = float(np.nanmean(np.hypot(*(calcule - np.asarray(sol)).T))) if ok.all() else float("inf")
    return Calibration(repere=repere, homographie=h.tolist(), largeur=largeur, hauteur=hauteur, portee_m=portee_m,
                       source=source or f"marqueurs {', '.join(str(p.numero) for p in utilises)}",
                       erreur_m=None if erreur is None else round(erreur, 4), marqueurs=utilises)
