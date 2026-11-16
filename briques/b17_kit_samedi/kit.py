"""Brique 17 — Le kit du samedi matin : du texte du défi à un plan, en une commande, hors ligne.

    python3 lancer.py kit-samedi DEFI.md                       le plan s'affiche dans le terminal
    python3 lancer.py kit-samedi DEFI.md --sortie plan.md      le plan dans plan.md, le scénario dans plan_scenario.yaml
    python3 lancer.py kit-samedi DEFI.txt --scenario demo.yaml le scénario YAML dans demo.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyseur import analyser
from .plan import rendre_plan, rendre_scenario


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python3 lancer.py kit-samedi",
                                description="Lire le texte du défi (hors ligne) et rendre un plan de 48 heures.")
    p.add_argument("defi", help="le texte du défi (.md ou .txt)")
    p.add_argument("--sortie", help="écrire le plan dans ce fichier Markdown (sinon : dans le terminal)")
    p.add_argument("--scenario", help="écrire le brouillon de scénario YAML ici (par défaut : à côté de --sortie)")
    args = p.parse_args(argv)

    chemin = Path(args.defi)
    if not chemin.is_file():
        print(f"  Fichier du défi introuvable : {chemin}", file=sys.stderr)
        return 2
    texte = chemin.read_text(encoding="utf-8", errors="replace")
    if not texte.strip():
        print(f"  Le fichier du défi est vide : {chemin}", file=sys.stderr)
        return 2
    analyse = analyser(texte)

    scenario = Path(args.scenario) if args.scenario else None
    if scenario is None and args.sortie:
        sortie = Path(args.sortie)
        scenario = sortie.with_name(sortie.stem + "_scenario.yaml")
    plan = rendre_plan(analyse, scenario.name if scenario else None)

    if args.sortie:
        Path(args.sortie).write_text(plan, encoding="utf-8")
        print(f"  Plan écrit : {args.sortie}")
    else:
        print(plan)
    if scenario:
        scenario.write_text(rendre_scenario(analyse), encoding="utf-8")
        print(f"  Brouillon de scénario (YAML) : {scenario}", file=sys.stderr if not args.sortie else sys.stdout)
    if args.sortie:
        print("  Fait hors ligne, par mots-clés : à relire par un humain. Testé sur faux robot seulement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
