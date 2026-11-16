"""Brique 7 — Ce que le gardien sait autour du robot : où est le robot, où sont les personnes.

- La position du robot vient de la prise (état du robot), en lecture seulement.
- Les personnes :
  * faux robot : personnes SIMULÉES (commun/monde.yaml → personnes, ou placer_personne() dans les tests) ;
  * vrai robot : la brique 5 (« yeux ») appelle annoncer_personnes(). Sans nouvelles depuis `fraicheur_max_s`,
    le gardien considère qu'il ne sait PAS où sont les personnes (et demande à un humain avant de bouger).
Jamais de personnes simulées avec un vrai robot : placer_personne() refuse.

Correction après relecture (brique 5) : « pas vue » ne veut pas dire « pas là ». Celui qui annonce des personnes dit
aussi la ZONE qu'il a vue (`zone`, obligatoire) ; hors de cette zone, le gardien ne sait pas (zone_couvre).
"""
from __future__ import annotations

import math
import time
from typing import Any, Awaitable, Callable, Iterable

from pydantic import BaseModel

AVANCE_MAX_S = 0.1  # une heure de photo plus loin que ça dans le futur est fausse (ex. mauvaise horloge) : refusée


class PersonneVue(BaseModel):
    id: str
    x: float
    y: float
    source: str = "simulation"


class _Partout:
    """La zone « tout le sol » : seulement pour une source qui voit vraiment toute la halle (ou les tests)."""

    def voit(self, x: float, y: float) -> bool:
        return True

    def __repr__(self) -> str:
        return "PARTOUT"


PARTOUT = _Partout()


class Vue(BaseModel):
    position: tuple[float, float, float] | None = None  # x, y (m), cap (degrés) ; None = on ne sait pas
    liaison_ok: bool = True
    personnes: list[PersonneVue] | None = None  # None = on ne sait pas où sont les personnes
    source_personnes: str = "aucune"
    # Brique 5 : la zone du sol vue (objet avec voit(x, y) -> bool, repère du monde). None = personnes simulées.
    zone_vue: Any = None


def zone_couvre(zone, depart: tuple[float, float], fin: tuple[float, float], marge_m: float, pas_m: float = 0.05) -> bool:
    """Tout le sol à moins de `marge_m` du chemin (départ → fin ; un point pour un geste) est-il dans la zone vue ?
    On vérifie le bord d'une bande un peu plus large (+ 10 cm) et le chemin lui-même, tous les `pas_m`. La zone vue
    par une caméra est d'un seul tenant et convexe (sans trou) : si ce bord est vu, l'intérieur l'est aussi."""
    if zone is None:
        return True
    r = marge_m + 0.1
    (x0, y0), (x1, y1) = depart, fin
    longueur = math.hypot(x1 - x0, y1 - y0)
    ux, uy = ((x1 - x0) / longueur, (y1 - y0) / longueur) if longueur > 1e-9 else (1.0, 0.0)
    nx, ny = -uy, ux
    points = []
    n = max(1, math.ceil(longueur / pas_m))
    for i in range(n + 1):
        t = i / n
        px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        points += [(px, py), (px + nx * r, py + ny * r), (px - nx * r, py - ny * r)]
    k = max(8, math.ceil(math.pi * r / pas_m))
    base = math.atan2(uy, ux)
    for i in range(k + 1):  # demi-cercle derrière le départ, demi-cercle devant l'arrivée
        a = base + math.pi / 2 + math.pi * i / k
        points.append((x0 + r * math.cos(a), y0 + r * math.sin(a)))
        points.append((x1 - r * math.cos(a), y1 - r * math.sin(a)))
    return all(zone.voit(x, y) for x, y in points)


class Perception:
    def __init__(self, lire_etat: Callable[[], Awaitable[object]] | None = None, simulation: bool = False,
                 personnes: Iterable = (), fraicheur_max_s: float = 2.0) -> None:
        self._lire_etat = lire_etat
        self.simulation = simulation
        self.fraicheur_max_s = fraicheur_max_s
        self._personnes: dict[str, PersonneVue] = {}
        self._heure_annonce: float | None = None
        self._zone: Any = None
        self._source = "simulation" if simulation else "aucune"
        for p in personnes:  # personnes simulées du monde (objets avec id et position)
            self.placer_personne(p.id, p.position.x, p.position.y)

    # ---------- faux robot et tests ----------
    def placer_personne(self, ident: str, x: float, y: float) -> None:
        if not self.simulation:
            raise ValueError("Personnes simulées interdites avec un vrai robot : ce sont les yeux (brique 5) qui les donnent.")
        self._personnes[ident] = PersonneVue(id=ident, x=float(x), y=float(y), source="simulation")

    def retirer_personne(self, ident: str) -> None:
        if not self.simulation:
            raise ValueError("Personnes simulées interdites avec un vrai robot.")
        self._personnes.pop(ident, None)

    # ---------- vrai robot : la brique 5 donne les personnes qu'elle voit ----------
    def annoncer_personnes(self, personnes: Iterable[PersonneVue], source: str = "yeux", heure: float | None = None,
                           *, zone) -> None:
        """Toutes les personnes vues en ce moment (positions dans le repère du monde, en mètres), et la `zone` du sol
        vue (objet avec voit(x, y) -> bool ; PARTOUT seulement si la source voit vraiment toute la halle).
        Liste vide = personne DANS la zone ; hors de la zone, on ne sait pas.
        `heure` (facultatif) : time.monotonic() de la PRISE DE VUE ; la fraîcheur se compte depuis la photo. Une heure
        qui n'est pas un nombre, ou dans le futur (mauvaise horloge) : on ne sait plus où sont les personnes."""
        maintenant = time.monotonic()
        if heure is not None and not (isinstance(heure, (int, float)) and not isinstance(heure, bool)
                                      and math.isfinite(heure) and heure <= maintenant + AVANCE_MAX_S):
            self._personnes, self._heure_annonce, self._zone = {}, None, None  # rien de sûr : « personnes inconnues »
            self._source = f"{source} (heure de photo refusée)"
            return
        if zone is None or not callable(getattr(zone, "voit", None)):
            raise ValueError("annoncer_personnes : il faut la zone vue (objet avec voit(x, y)), ou PARTOUT.")
        self._personnes = {p.id: p for p in personnes}
        self._heure_annonce = min(float(heure), maintenant) if heure is not None else maintenant
        self._zone = zone
        self._source = source

    # ---------- pour le gardien ----------
    async def vue(self) -> Vue:
        position, liaison = None, True
        if self._lire_etat is not None:
            try:
                etat = await self._lire_etat()
            except Exception:
                etat = None
            if etat is None:
                liaison = False
            else:
                liaison = bool(getattr(etat, "liaison_ok", True))
                p = getattr(etat, "position", {}) or {}
                x, y, cap = p.get("x"), p.get("y"), p.get("cap", 0.0)
                if all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, cap)):
                    position = (float(x), float(y), float(cap))
        zone = None
        if self.simulation:
            personnes = list(self._personnes.values())
        elif self._heure_annonce is not None and time.monotonic() - self._heure_annonce <= self.fraicheur_max_s:
            personnes, zone = list(self._personnes.values()), self._zone
        else:
            personnes = None  # pas de nouvelles des yeux : on ne sait pas
        return Vue(position=position, liaison_ok=liaison, personnes=personnes, source_personnes=self._source,
                   zone_vue=zone)
