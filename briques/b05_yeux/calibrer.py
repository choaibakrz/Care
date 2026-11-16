"""Calibrer la caméra au sol avec des marqueurs ArUco (samedi, GUIDE.md). Ne fait que LIRE la caméra : aucun ordre au robot.

    .venv/bin/python -m briques.b05_yeux.calibrer --essai                     (caméra simulée : voir que tout marche)
    .venv/bin/python -m briques.b05_yeux.calibrer --camera opencv:0 --photo vue.png   (une photo, marqueurs entourés)
    .venv/bin/python -m briques.b05_yeux.calibrer --camera opencv:0           (3 marqueurs aux places par défaut)
    .venv/bin/python -m briques.b05_yeux.calibrer --camera opencv:0 --marqueur 0:1.5:0 --marqueur 1:2.5:0.8 \\
        --marqueur 2:2.5:-0.8 --taille 0.28

Un marqueur = NUMÉRO:X:Y[:CAP] en mètres, depuis le CENTRE du robot : X devant, Y à gauche (négatif = à droite).
CAP = direction du haut du marqueur (0 = le haut vers l'avant, le marqueur se lit depuis le robot).
Repère « monde » (caméra fixe dans la halle) : X, Y du monde (commun/monde.yaml), avec --repere monde.
Le résultat est écrit dans briques/b05_yeux/calibration.yaml (ou --sortie), lu par les yeux au démarrage.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from .camera_simulee import CameraEnPanne, CameraSimulee
from .geometrie import Calibration, PlacementMarqueur, calibrer
from .marqueurs import ListeMarqueurs
from .prise_yeux import Marqueur

RACINE = Path(__file__).resolve().parents[2]
SORTIE = RACINE / "briques" / "b05_yeux" / "calibration.yaml"
PLACES_DEFAUT = ["0:1.5:0", "1:2.5:0.8", "2:2.5:-0.8"]


def lire_placement(texte: str, taille: float) -> PlacementMarqueur:
    morceaux = texte.replace(",", ".").split(":")
    if len(morceaux) not in (3, 4):
        raise ValueError(f"« {texte} » : écrire NUMÉRO:X:Y ou NUMÉRO:X:Y:CAP (ex. 0:1.5:0)")
    n, x, y = int(morceaux[0]), float(morceaux[1]), float(morceaux[2])
    cap = float(morceaux[3]) if len(morceaux) == 4 else 0.0
    return PlacementMarqueur(numero=n, x=x, y=y, taille_m=taille, cap_deg=cap)


def coins_moyens(vues: list[list[Marqueur]]) -> list[Marqueur]:
    """Les coins de chaque marqueur, moyennés sur plusieurs images (moins de tremblement)."""
    par_numero: dict[int, list[np.ndarray]] = {}
    for vus in vues:
        for m in vus:
            par_numero.setdefault(m.numero, []).append(np.asarray(m.coins, dtype=float))
    return [Marqueur(numero=n, coins=[tuple(c) for c in np.mean(liste, axis=0).tolist()], sorte="calibration")
            for n, liste in sorted(par_numero.items())]


def calibrer_camera(camera, placements: list[PlacementMarqueur], marqueurs: ListeMarqueurs, images: int = 10,
                    repere: str = "robot", essai: bool = False) -> Calibration:
    from .branchements.aruco import BranchementAruco

    aruco = BranchementAruco(marqueurs)
    raison = aruco.preparer()
    if raison:
        raise RuntimeError(raison)
    attendus = {p.numero for p in placements}
    vues, largeur, hauteur = [], 0, 0
    for _ in range(images):
        image = camera.image_de_calibration(placements) if essai else camera.lire()
        largeur, hauteur = image.largeur, image.hauteur
        vus = [m for m in aruco.analyser(image).marqueurs if m.numero in attendus]
        if vus:
            vues.append(vus)
        if not essai:
            time.sleep(0.1)
    if not vues:
        raise ValueError(f"Aucun marqueur de calibration vu (attendus : {sorted(attendus)}). Lumière ? Marqueur en "
                         "entier dans l'image ? Bon numéro ? (voir GUIDE.md)")
    meilleurs = max(len(v) for v in vues)
    retenues = [v for v in vues if len(v) == meilleurs]  # les images où l'on voit le plus de marqueurs
    source = f"{getattr(camera, 'source', 'caméra')} ; {len(retenues)} image(s)"
    return calibrer(coins_moyens(retenues), placements, largeur, hauteur, repere=repere, source=source)


def decrire(cal: Calibration, attendus: int) -> list[str]:
    """Ce que la calibration permet de voir, en mots simples, et les alertes."""
    lignes = [f"Marqueurs utilisés : {[m.numero for m in cal.marqueurs]} sur {attendus}."]
    if cal.erreur_m is None:
        lignes.append("Un seul marqueur : pas de contrôle de l'erreur. Mieux : 3 marqueurs (GUIDE.md).")
    else:
        lignes.append(f"Erreur moyenne sur les coins : {cal.erreur_m * 100:.1f} cm"
                      + (" (bien)." if cal.erreur_m < 0.03 else " : TROP GRANDE, re-mesurer les places des marqueurs."))
    if cal.repere == "robot":
        import math

        bas = cal.vers_sol(cal.largeur / 2, cal.hauteur - 1)
        milieu = cal.vers_sol(cal.largeur / 2, cal.hauteur / 2, limiter=False)
        if bas is None:
            lignes.append("ALERTE : le bas de l'image ne tombe pas sur le sol. Les places des marqueurs sont-elles justes ?")
        else:
            lignes.append(f"Le bas de l'image voit le sol à {math.hypot(bas.x, bas.y):.2f} m du centre du robot : plus "
                          "près, la caméra ne voit pas (une personne plus proche sera comptée « collée au robot »).")
            if bas.x < 0:
                lignes.append("ALERTE : la caméra regarde vers l'arrière du robot. Les X sont-ils mesurés vers l'avant ?")
        if milieu is not None:
            lignes.append(f"Le milieu de l'image voit le sol à {math.hypot(milieu.x, milieu.y):.2f} m.")
    return lignes


def photo(camera, marqueurs: ListeMarqueurs, chemin: Path) -> int:
    """Une photo de la caméra, les marqueurs vus entourés et numérotés : pour vérifier le cadrage et la lumière."""
    import cv2

    from .branchements.aruco import BranchementAruco

    try:
        image = camera.lire()
    except CameraEnPanne as e:
        print(f"Pas d'image : {e}")
        return 1
    finally:
        camera.fermer()
    aruco = BranchementAruco(marqueurs)
    vus = [] if aruco.preparer() else aruco.analyser(image).marqueurs
    dessin = cv2.cvtColor(image.pixels, cv2.COLOR_RGB2BGR)
    for m in vus:
        coins = np.asarray(m.coins, dtype=np.int32)
        cv2.polylines(dessin, [coins], True, (0, 0, 255), 2)
        cv2.putText(dessin, str(m.numero), tuple(int(v) for v in coins[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.imwrite(str(chemin), dessin)
    print(f"Photo {image.largeur}×{image.hauteur} écrite : {chemin}. Marqueurs vus : {[m.numero for m in vus] or 'aucun'}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Calibrer la caméra au sol avec des marqueurs ArUco (brique 5).")
    p.add_argument("--camera", default="opencv:0", help="opencv:0, opencv:URL, fichier:photo.png")
    p.add_argument("--marqueur", action="append", help="NUMÉRO:X:Y[:CAP] en mètres (répéter pour chaque marqueur)")
    p.add_argument("--taille", type=float, help="côté du carré noir imprimé, en mètres (défaut : marqueurs.yaml)")
    p.add_argument("--repere", choices=["robot", "monde"], default="robot")
    p.add_argument("--images", type=int, default=10)
    p.add_argument("--sortie", type=Path, default=SORTIE)
    p.add_argument("--essai", action="store_true", help="caméra SIMULÉE (faux robot) : pour voir que tout marche")
    p.add_argument("--genre", default="humanoide", help="avec --essai : humanoide, chien, bras")
    p.add_argument("--photo", type=Path, help="seulement prendre une photo (marqueurs vus entourés) et l'écrire ici")
    args = p.parse_args(argv)

    marqueurs = ListeMarqueurs.charger()
    taille = args.taille or marqueurs.calibration.taille_m
    if args.essai:
        from commun.monde import Monde

        camera = CameraSimulee(Monde.charger(), genre=args.genre)
        placements = ([lire_placement(t, taille) for t in args.marqueur] if args.marqueur
                      else camera.placements_de_calibration(marqueurs.calibration.numeros, taille))
        print("ESSAI sur la caméra SIMULÉE (faux robot) : rien n'est écrit.")
    else:
        from .camera import ouvrir_camera

        camera = ouvrir_camera(args.camera, None, args.genre, faux_robot=False)
        if camera is None:
            print("Pas de caméra choisie (--camera).")
            return 1
        placements = [lire_placement(t, taille) for t in (args.marqueur or PLACES_DEFAUT)]
        if args.photo:
            return photo(camera, marqueurs, args.photo)
    for pl in placements:
        print(f"  marqueur n° {pl.numero} : X = {pl.x} m, Y = {pl.y} m, côté {pl.taille_m} m, cap {pl.cap_deg}°")
    try:
        cal = calibrer_camera(camera, placements, marqueurs, args.images, args.repere, essai=args.essai)
    except (ValueError, RuntimeError, CameraEnPanne) as e:
        print(f"Calibration impossible : {e}")
        return 1
    finally:
        camera.fermer()
    for ligne in decrire(cal, len(placements)):
        print("  " + ligne)
    if args.essai:
        exacte = camera.homographie_exacte()
        from .geometrie import appliquer

        pix = [(u, v) for u in np.linspace(20, 300, 8) for v in np.linspace(80, 235, 8)]
        a, ok_a = appliquer(cal.matrice(), pix)
        b, ok_b = appliquer(exacte, pix)
        ok = ok_a & ok_b
        e = np.hypot(*(a[ok] - b[ok]).T)[np.hypot(*b[ok].T) < 3]
        print(f"  Comparée à la vraie (connue en simulation) : {e.mean() * 100:.1f} cm en moyenne jusqu'à 3 m.")
        return 0
    print(f"Écrit : {cal.enregistrer(args.sortie)}. Refaire si la caméra bouge par rapport au robot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
