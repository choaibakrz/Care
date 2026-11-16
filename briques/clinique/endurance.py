"""L'endurance (avenant 2, tâche K02 ; seconde moitié) : rejouer le scénario en boucle, pendant une durée.

    python3 lancer.py endurance --duree 1m        (ou 90s, 5m, 2h)

La commande rejoue la grande répétition, passage après passage, sur le faux robot. Elle s'arrête au premier arrêt
imprévu (une étape ratée, une pièce qui casse). Elle écrit : la durée tenue, le nombre de passages, la cause de l'arrêt
(ou « aucun arrêt »). Chaque mesure s'ajoute à `journal/endurance.jsonl` ; rien n'est effacé.
Le troisième chiffre, « plus longue durée sans arrêt », est la meilleure de ces mesures.

DIRE VRAI : c'est le FAUX ROBOT, sur des données inventées. Un passage n'est pas coupé en route : la durée tenue peut
dépasser un peu la durée demandée. La durée tenue ne compte que des passages entiers et réussis.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from briques.b12_boite_noire.journal import DOSSIER_DEFAUT

from . import aide_humaine, chef_clinique, repetition

FICHIER = "endurance.jsonl"
ETIQUETTE = "FAUX ROBOT"
AUCUN_ARRET = "aucun arrêt"
UNITES = {"": 1, "s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600}


def lire_duree(texte: str) -> int:
    """« 60 », « 90s », « 5m », « 1 min », « 2h » → des secondes."""
    trouve = re.fullmatch(r"\s*(\d+)\s*([a-z]*)\s*", str(texte).lower())
    if not trouve or trouve.group(2) not in UNITES or int(trouve.group(1)) <= 0:
        raise ValueError(f"durée « {texte} » : écrire par exemple 90s, 5m ou 2h")
    return int(trouve.group(1)) * UNITES[trouve.group(2)]


def texte_duree(secondes: float) -> str:
    s = int(round(secondes))
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    if h:
        return f"{h} h {m:02d} min {s:02d} s"
    return f"{m} min {s:02d} s" if m else f"{s} s"


def tenir(duree_s: float, controles: dict[int, Callable] | None = None, ecrire: Callable[[str], None] = print,
          dossier: str | Path = DOSSIER_DEFAUT, montre: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Rejoue le scénario jusqu'à la durée demandée, ou jusqu'au premier arrêt imprévu. Écrit et rend la mesure."""
    quand = datetime.now()
    ecrire(f"L'ENDURANCE — la clinique en boîte — {ETIQUETTE} — {quand.strftime('%d.%m.%Y, %H:%M')} — DONNÉES INVENTÉES")
    ecrire(f"Durée demandée : {texte_duree(duree_s)}. Le scénario est rejoué en boucle. Arrêt au premier arrêt imprévu.")
    debut = montre()
    passages, tenue, arret, aides = 0, 0.0, AUCUN_ARRET, 0
    while True:
        sortie: list[str] = []
        seances: list[repetition.Seance] = []
        cause = None
        with aide_humaine.compter() as compte:
            try:
                code = chef_clinique.jouer(controles, ecrire=sortie.append, garder=seances)
            except Exception as erreur:  # la répétition elle-même a cassé : c'est un arrêt imprévu
                code, cause = 1, f"le programme de la répétition s'est arrêté ({type(erreur).__name__} : {erreur})"
        aides += len(compte.aides)
        maintenant = montre()
        if code != 0 and cause is None:
            ratees = [n for n, issue in sorted(seances[0].issues.items()) if issue != "reussie"] if seances else []
            lignes = [next((l for l in sortie if l.startswith(f"{n:>2}. ")), "").strip()[:300] for n in ratees]
            cause = " ; ".join(f"étape {n} ratée — {l}" for n, l in zip(ratees, lignes)) or "la répétition n'a pas réussi"
        if cause is not None:
            arret = f"arrêt au passage {passages + 1} : {cause}"
            break
        passages += 1
        tenue = maintenant - debut
        ecrire(f"  passage {passages} : réussi — durée tenue {texte_duree(tenue)}")
        if tenue >= duree_s:
            break
    mesure = {"etiquette": ETIQUETTE, "date": quand.isoformat(timespec="seconds"), "duree_demandee_s": float(duree_s),
              "duree_tenue_s": round(tenue, 1), "passages": passages, "arret": arret, "aides_humaines": aides,
              "marque": "données inventées"}
    Path(dossier).mkdir(parents=True, exist_ok=True)
    with open(Path(dossier) / FICHIER, "a", encoding="utf-8") as f:
        f.write(json.dumps(mesure, ensure_ascii=False) + "\n")
    ecrire(f"Pendant l'endurance : {aides} aide{'s' if aides > 1 else ''} humaine{'s' if aides > 1 else ''}")
    ecrire(f"ENDURANCE : durée tenue {texte_duree(tenue)} ; {passages} passages ; {arret} [{ETIQUETTE}]")
    return {**mesure, "code": 0 if arret == AUCUN_ARRET else 1}


def mesures(dossier: str | Path = DOSSIER_DEFAUT) -> list[dict[str, Any]]:
    fichier = Path(dossier) / FICHIER
    if not fichier.exists():
        return []
    lues = []
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        try:
            lues.append(json.loads(ligne))
        except ValueError:
            continue
    return [m for m in lues if isinstance(m, dict) and isinstance(m.get("duree_tenue_s"), (int, float))]


def plus_longue(dossier: str | Path = DOSSIER_DEFAUT) -> dict[str, Any] | None:
    """La mesure d'endurance qui a tenu le plus longtemps. None : jamais mesuré."""
    toutes = mesures(dossier)
    return max(toutes, key=lambda m: m["duree_tenue_s"]) if toutes else None


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print) -> int:
    p = argparse.ArgumentParser(prog="lancer.py endurance", description="La clinique en boîte : l'endurance sur le faux robot")
    p.add_argument("--duree", help="la durée : 90s, 5m, 2h…")
    a = p.parse_args(reste or [])
    if not a.duree:
        ecrire("Donner une durée : python3 lancer.py endurance --duree 5m   (90s, 5m, 2h…)")
        return 2
    try:
        duree = lire_duree(a.duree)
    except ValueError as erreur:
        ecrire(str(erreur))
        return 2
    return tenir(duree, ecrire=ecrire)["code"]
