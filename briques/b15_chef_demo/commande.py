"""Brique 15 — La commande : python3 lancer.py scenario CHEMIN [options]. Voir GUIDE.md.

    python3 lancer.py scenario briques/b15_chef_demo/scenarios/essai_3_minutes.yaml
    python3 lancer.py scenario essai_3_minutes.yaml --repetition --panne robot@7 --panne voix@3 --acceleration 20
    python3 lancer.py scenario essai_3_minutes.yaml --repetition --pagaille --graine 7
"""
from __future__ import annotations

import argparse
import asyncio
import copy
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def options(p: argparse.ArgumentParser) -> None:
    """Les options de la sous-commande « scenario » (appelé par lancer.py)."""
    p.add_argument("chemin", help="le fichier du scénario (.yaml) ; un nom seul est cherché dans briques/b15_chef_demo/scenarios/")
    p.add_argument("--repetition", action="store_true", help="mode répétition : pannes permises, compte rendu écrit")
    p.add_argument("--panne", action="append", default=[], metavar="NOM@ÉTAPE",
                   help="provoquer une panne pendant une étape : robot@3, voix@2, reseau@4 (répétition)")
    p.add_argument("--pagaille", action="store_true", help="pannes au hasard sur les étapes « dire » (répétition)")
    p.add_argument("--graine", type=int, default=1, help="graine du hasard pour --pagaille (même graine = mêmes pannes)")
    p.add_argument("--acceleration", type=float, default=1.0, help="faux robot et pauses N fois plus vite (faux robot seulement)")
    p.add_argument("--rapport", help="dossier du compte rendu (par défaut : mesures/)")
    p.add_argument("--operateur", choices=["auto", "clavier"],
                   help="main humaine : auto (simulée, faux robot) ou clavier (attendre la touche Entrée)")
    p.add_argument("--robot", choices=["humanoide", "chien", "bras"], help="carte du faux robot (sinon : celle du scénario)")


def main(args: argparse.Namespace, reglages: dict | None = None, dossier_journal: str | Path | None = None) -> int:
    from commun.systeme import Systeme, charger_reglages

    from .chef import ChefDemo, OperateurAutomatique, OperateurClavier, tirer_pagaille
    from .compte_rendu import ecrire
    from .scenario import ScenarioInvalide, charger, lire_pannes

    try:
        sc = charger(args.chemin)
        pannes = lire_pannes(args.panne, sc)
    except (ScenarioInvalide, OSError) as e:
        print(f"  {e}")
        return 2
    if args.pagaille:
        pannes = {**tirer_pagaille(sc, args.graine), **pannes}  # une panne écrite à la main l'emporte
    if pannes and not args.repetition:
        print("  Les pannes ne se provoquent qu'en répétition : ajoutez --repetition.")
        return 2
    r = copy.deepcopy(reglages or charger_reglages())
    faux = r["robot"]["adaptateur"] == "faux_robot" and not r["robot"].get("vrai_robot")
    if not faux:
        # Cette commande n'a ni écran (bouton ARRÊT) ni oreille (« stop » à la voix) : sur un vrai robot, il ne resterait
        # que Ctrl+C et le bouton physique. Pas encore : jouer le scénario depuis l'écran (TACHES.md). Feu orange de toute façon.
        print("  Vrai robot : « lancer.py scenario » refuse pour l'instant (pas d'écran ni de « stop » à la voix ici).\n"
              "  Répéter sur le faux robot ; avec le vrai robot, le jouer à la main depuis l'écran, responsable sécurité\n"
              "  présent, main sur le bouton d'arrêt PHYSIQUE, après le « oui » de Hiba. Rien n'a été lancé.")
        return 2
    carte = args.robot or (sc.robot if faux else None)
    if carte:
        r["robot"]["carte"] = carte
    operateur = None
    if args.operateur == "clavier":
        operateur = OperateurClavier()
    elif args.operateur == "auto":
        operateur = OperateurAutomatique(5.0 / args.acceleration)
    extra = {"dossier_journal": dossier_journal} if dossier_journal else {}
    s = Systeme(r, acceleration=args.acceleration, **extra)

    async def jouer():
        await s.demarrer()
        try:
            chef = ChefDemo(s, sc, repetition=args.repetition, acceleration=args.acceleration, pannes=pannes,
                            operateur=operateur, fichier=str(args.chemin), graine=args.graine if args.pagaille else None,
                            afficher=lambda t: print(t, flush=True))
            return await chef.jouer()
        finally:
            await s.arreter()

    try:
        res = asyncio.run(jouer())
    except ValueError as e:
        print(f"  {e}")
        return 2
    print(f"\n  Fini en {res.duree_s:.2f} s — {res.compter('reussie')} réussies, {res.compter('rattrapee')} rattrapées, "
          f"{res.compter('ratee')} ratées, {res.compter('sautee')} sautées — {res.mention}"
          + (f" (accéléré ×{res.acceleration:g} : pas des temps réels)" if res.acceleration != 1 else ""))
    if res.interrompu:
        print(f"  Interrompu : {res.interrompu}")
    if args.repetition:
        print(f"  Compte rendu : {ecrire(res, args.rapport)}")
    print(f"  Journal : {s.boite_noire.fichier}")
    return 0 if not res.interrompu and res.compter("ratee") == 0 else 1
