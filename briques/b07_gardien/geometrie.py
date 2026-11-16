"""Brique 7 — Un peu de géométrie, vue de dessus, en mètres.

Le chemin du robot est un segment de droite (du point de départ au point d'arrivée). C'est simple et prudent pour
un robot qui va en ligne droite. Un robot qui contourne les obstacles peut passer ailleurs : à vérifier sur chaque robot.
Les zones sont des cercles (autour d'un lieu) ou des rectangles. Toutes sont convexes (sans creux) : un segment qui
part de l'intérieur ne peut sortir qu'une fois.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]


def distance_point_segment(p: Point, a: Point, b: Point) -> float:
    """La plus petite distance entre le point p et le segment [a, b]."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    longueur2 = dx * dx + dy * dy
    if longueur2 == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / longueur2))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def arrivee_relative(depart: tuple[float, float, float], dx: float, dy: float) -> Point:
    """Où arrive le robot s'il avance de dx (devant) et dy (à gauche), cap en degrés (même calcul que le faux robot)."""
    x, y, cap = depart
    rad = math.radians(cap)
    return (x + dx * math.cos(rad) - dy * math.sin(rad), y + dx * math.sin(rad) + dy * math.cos(rad))


@dataclass(frozen=True)
class Cercle:
    centre: Point
    rayon: float

    def contient(self, p: Point) -> bool:
        return math.dist(p, self.centre) <= self.rayon

    def coupe(self, a: Point, b: Point) -> bool:
        return distance_point_segment(self.centre, a, b) <= self.rayon


@dataclass(frozen=True)
class Rectangle:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def contient(self, p: Point) -> bool:
        return self.x_min <= p[0] <= self.x_max and self.y_min <= p[1] <= self.y_max

    def coupe(self, a: Point, b: Point) -> bool:
        """Le segment [a, b] touche-t-il le rectangle ? (méthode de Liang et Barsky : on coupe le segment aux 4 bords)"""
        if self.contient(a) or self.contient(b):
            return True
        t0, t1 = 0.0, 1.0
        dx, dy = b[0] - a[0], b[1] - a[1]
        for p, q in ((-dx, a[0] - self.x_min), (dx, self.x_max - a[0]), (-dy, a[1] - self.y_min), (dy, self.y_max - a[1])):
            if p == 0:
                if q < 0:
                    return False  # parallèle au bord et dehors
                continue
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
        return True
