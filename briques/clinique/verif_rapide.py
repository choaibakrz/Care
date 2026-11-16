"""La vérification rapide : toutes les vérifications courtes, de l'ossature et de la clinique (cahier, partie 8).

    python3 lancer.py verif-rapide            tout, sauf les essais longs
    python3 lancer.py verif-rapide briques/clinique      un dossier seulement (options de pytest permises)

Elle doit durer moins de deux minutes. Elle finit par : « VÉRIFICATION RAPIDE : 58 réussies, 0 ratée ».
Les essais longs (1,5 seconde ou plus, mesurés) sont dans essais_longs.txt : ils restent dans
« python3 lancer.py tests », qui lance tout. Aucun essai de la clinique n'a le droit d'être dans cette liste.
Aucun modèle n'est appelé : les essais se servent du cerveau à règles et de réponses fixes.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
LISTE = Path(__file__).resolve().parent / "essais_longs.txt"
LIMITE_SECONDES = 120


@dataclass(frozen=True)
class Bilan:
    reussies: int
    ratees: int  # ratées + fichiers illisibles
    sautees: int
    laissees: int  # les essais longs, laissés de côté


def essais_longs() -> list[str]:
    lignes = LISTE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lignes if l.strip() and not l.startswith("#")]


def lire_bilan(derniere_ligne: str) -> Bilan:
    def nombre(mot: str) -> int:
        trouve = re.search(rf"(\d+) {mot}", derniere_ligne)
        return int(trouve.group(1)) if trouve else 0

    reussies, ratees = nombre("passed"), nombre("failed") + nombre("errors?")
    if not re.search(r"\d+ (passed|failed|errors?|skipped|deselected)", derniere_ligne):
        ratees = max(ratees, 1)  # pas de bilan lisible : on ne dit jamais « 0 ratée » sans preuve
    return Bilan(reussies, ratees, nombre("skipped"), nombre("deselected"))


def ligne_finale(bilan: Bilan) -> str:
    return (f"VÉRIFICATION RAPIDE : {bilan.reussies} réussie{'s' if bilan.reussies > 1 else ''}, "
            f"{bilan.ratees} ratée{'s' if bilan.ratees > 1 else ''}")


def main(reste: list[str] | None = None) -> int:
    commande = [sys.executable, "-m", "pytest", "-q", *(reste or [])]
    for essai in essais_longs():
        commande += ["--deselect", essai]
    debut = time.monotonic()
    sortie = subprocess.run(commande, cwd=RACINE, capture_output=True, text=True)
    duree = time.monotonic() - debut
    lignes = [l for l in sortie.stdout.splitlines() if l.strip()]
    bilan = lire_bilan(lignes[-1] if lignes else "")
    if sortie.returncode != 0 and bilan.ratees == 0:
        bilan = Bilan(bilan.reussies, 1, bilan.sautees, bilan.laissees)
    if bilan.ratees:
        print(sortie.stdout[-6000:])
        print(sortie.stderr[-2000:], file=sys.stderr)
    print(f"Sautées : {bilan.sautees} (pièces absentes de cette machine). "
          f"Laissées de côté car longues : {bilan.laissees}. Durée : {duree:.0f} s.")
    if duree > LIMITE_SECONDES:
        print(f"ATTENTION : plus de {LIMITE_SECONDES} secondes. Mettre les essais longs de l'ossature dans essais_longs.txt.")
    print(ligne_finale(bilan))
    return 0 if bilan.ratees == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
