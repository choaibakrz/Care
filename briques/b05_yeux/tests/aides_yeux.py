"""Aides pour les tests des yeux (brique 5) : un système complet avec le faux robot et les yeux allumés."""
from __future__ import annotations

import asyncio
import importlib.util
import time
from types import SimpleNamespace

OPENCV = importlib.util.find_spec("cv2") is not None
RAPIDOCR = importlib.util.find_spec("rapidocr") is not None
MEDIAPIPE = importlib.util.find_spec("mediapipe") is not None


def etat_simule(x: float = 1.0, y: float = 1.0, cap: float = 0.0, simulation: bool = True, objets: dict | None = None,
                tenu: str | None = None):
    """Un état de robot comme celui que donne la prise (seulement ce que lit la caméra simulée)."""
    extra = {"simulation": simulation}
    if objets is not None:
        extra["objets"] = objets
    return SimpleNamespace(position={"x": x, "y": y, "cap": cap}, extra=extra, objet_tenu=tenu)


def reglages_avec_yeux(reglages: dict, carte: str = "humanoide", **yeux) -> dict:
    r = {**reglages, "robot": {**reglages["robot"], "carte": carte}, "ecran": dict(reglages["ecran"]),
         "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    r["yeux"] = {**reglages["yeux"], "actif": True, "periode_s": 0.05, "periode_textes_s": 0.5, **yeux}
    return r


def systeme_avec_yeux(tmp_path, reglages: dict, carte: str = "humanoide", **yeux):
    from commun.systeme import Systeme

    return Systeme(reglages_avec_yeux(reglages, carte, **yeux), dossier_journal=tmp_path / "journal", acceleration=20)


async def attendre(condition, delai_s: float = 5.0, pas_s: float = 0.02) -> bool:
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        if condition():
            return True
        await asyncio.sleep(pas_s)
    return condition()


async def images_neuves(s, n: int = 3, delai_s: float = 5.0) -> None:
    """Attendre que les yeux aient regardé `n` nouvelles images (après un changement dans le faux monde)."""
    depart = s.yeux.images
    assert await attendre(lambda: s.yeux.images >= depart + n, delai_s), "les yeux ne regardent plus"


def evenements_yeux(s, quoi: str | None = None) -> list[dict]:
    return [e.donnees for e in s.bus.historique if e.type == "yeux" and (quoi is None or e.donnees.get("quoi") == quoi)]
