"""Banc d'essai des yeux : temps par image et mémoire, pour chaque outil, sur CET ordinateur.

    .venv/bin/python -m briques.b05_yeux.banc_yeux [--images 30] [--taille 320x240]

Images : dessinées par la caméra simulée (le robot fait le tour du faux monde). Pour RapidOCR : un panneau écrit.
La mémoire est mesurée « en plus », dans l'ordre de chargement (un outil qui réutilise OpenCV déjà chargé coûte moins).
Le résultat dit sur quelle machine il a été mesuré : un chiffre mesuré sur Linux ne vaut pas pour un Mac.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _rss_mo() -> float:
    import psutil

    return psutil.Process().memory_info().rss / 1e6


def _poses(n: int) -> list[tuple[float, float, float]]:
    import math

    return [(5 + 3 * math.cos(2 * math.pi * i / n), 3 + 1.8 * math.sin(2 * math.pi * i / n),
             (360 * i / n + 150) % 360) for i in range(n)]


def mesurer(n_images: int = 30, largeur: int = 320, hauteur: int = 240) -> dict:
    from types import SimpleNamespace

    import numpy as np

    from commun.monde import Monde

    from .branchements import fabriquer
    from .camera_simulee import CameraSimulee
    from .marqueurs import ListeMarqueurs
    from .prise_yeux import ImageCamera, Yeux

    monde, marqueurs = Monde.charger(), ListeMarqueurs.charger()
    depart = _rss_mo()
    resultats: dict = {"machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} cœurs, Python {platform.python_version()}",
                       "date": datetime.now().isoformat(timespec="seconds"), "images": n_images,
                       "taille": f"{largeur}x{hauteur}", "memoire_depart_mo": round(depart, 1), "outils": {}}
    cam = CameraSimulee(monde, largeur=largeur, hauteur=hauteur)
    t0 = time.monotonic()
    images = [cam.lire(SimpleNamespace(position={"x": x, "y": y, "cap": c}, extra={"simulation": True}, objet_tenu=None))
              for x, y, c in _poses(n_images)]
    resultats["outils"]["camera_simulee (dessin)"] = _ligne(depart, (time.monotonic() - t0) / n_images * 1000, None, "")
    texte = np.full((hauteur, largeur, 3), 255, np.uint8)
    try:
        import cv2

        cv2.putText(texte, "CUISINE", (largeur // 8, hauteur // 2), cv2.FONT_HERSHEY_SIMPLEX, largeur / 320, (0, 0, 0), 2)
    except ImportError:
        pass
    for nom in ("simule", "aruco", "mediapipe", "rapidocr"):
        avant = _rss_mo()
        b = fabriquer([nom], monde, marqueurs)[0]
        t1 = time.monotonic()
        try:
            raison = b.preparer()
        except Exception as e:  # noqa: BLE001
            raison = f"{type(e).__name__}: {e}"
        charge_s = time.monotonic() - t1
        if raison:
            resultats["outils"][nom] = {"mesure": False, "raison": raison}
            continue
        jeu = images if nom != "rapidocr" else [ImageCamera(pixels=texte, heure=time.monotonic(), source="banc")] * min(n_images, 10)
        yeux = Yeux([b])
        yeux.voir(jeu[0])  # première image (préchauffe) non comptée
        durees = []
        for im in jeu:
            t2 = time.monotonic()
            yeux.voir(im)
            durees.append((time.monotonic() - t2) * 1000)
        resultats["outils"][nom] = _ligne(avant, statistics.median(durees), max(durees), f"chargement {charge_s:.2f} s",
                                          p90=sorted(durees)[int(0.9 * (len(durees) - 1))])
    resultats["memoire_fin_mo"] = round(_rss_mo(), 1)
    return resultats


def _ligne(avant: float, mediane_ms: float, max_ms: float | None, note: str, p90: float | None = None) -> dict:
    return {"mesure": True, "ms_par_image_mediane": round(mediane_ms, 1), "ms_p90": None if p90 is None else round(p90, 1),
            "ms_max": None if max_ms is None else round(max_ms, 1), "memoire_en_plus_mo": round(_rss_mo() - avant, 1),
            "note": note}


def en_tableau(r: dict) -> str:
    lignes = [f"Mesuré sur {r['machine']} le {r['date']} — **mesuré sur Linux, pas sur Mac** si la machine dit Linux.",
              f"Images {r['taille']}, {r['images']} images (dessinées par la caméra simulée). Mémoire au départ : "
              f"{r['memoire_depart_mo']} Mo ; à la fin : {r['memoire_fin_mo']} Mo.", "",
              "| Outil | ms par image (médiane) | 90 % des images en moins de | mémoire en plus | remarque |",
              "|---|---|---|---|---|"]
    for nom, d in r["outils"].items():
        if d.get("mesure"):
            lignes.append(f"| {nom} | {d['ms_par_image_mediane']} | {d['ms_p90'] if d['ms_p90'] is not None else '—'} | "
                          f"{d['memoire_en_plus_mo']} Mo | {d['note']} |")
        else:
            lignes.append(f"| {nom} | non mesuré | — | — | {d['raison']} |")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Banc d'essai des yeux (brique 5).")
    p.add_argument("--images", type=int, default=30)
    p.add_argument("--taille", default="320x240")
    p.add_argument("--json", action="store_true", help="écrire aussi le résultat dans mesures/ (hors du dépôt)")
    args = p.parse_args(argv)
    largeur, hauteur = (int(v) for v in args.taille.lower().split("x"))
    r = mesurer(args.images, largeur, hauteur)
    print(en_tableau(r))
    if args.json:
        dossier = RACINE / "mesures"
        dossier.mkdir(exist_ok=True)
        f = dossier / f"yeux_{datetime.now():%Y%m%d_%H%M%S}.json"
        f.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nÉcrit : {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
