"""Brique 14 — La commande : python3 lancer.py porte-agents [options]. Voir GUIDE.md.

Dans UN seul programme : le système sur le FAUX robot, l'écran (pour voir, et pour qu'un humain accepte les
demandes du gardien), et le serveur MCP sur stdio (l'agent lance cette commande et lui parle par l'entrée et la
sortie standard). Les messages pour les humains vont sur la sortie d'erreur : la sortie standard est aux messages MCP.

    python3 lancer.py porte-agents --agent assistant
    python3 lancer.py porte-agents --agent assistant --sans-ecran --cerveau regles
"""
from __future__ import annotations

import argparse
import os
import asyncio
import copy
import socket
import sys
from contextlib import asynccontextmanager


def options(p: argparse.ArgumentParser) -> None:
    """Les options de la sous-commande « porte-agents » (appelé par lancer.py)."""
    p.add_argument("--agent", default="agent", help="nom de l'agent dans la boîte noire (« agent:NOM »), ex. assistant")
    p.add_argument("--robot", choices=["humanoide", "chien", "bras"], help="carte du faux robot")
    p.add_argument("--port", type=int, help="port de l'écran (sinon reglages.yaml → porte_agents → port_ecran, 8001)")
    p.add_argument("--sans-ecran", action="store_true", help="pas d'écran (alors personne ne peut accepter une demande)")
    p.add_argument("--cerveau", choices=["regles", "cascade"], help="remplace reglages.yaml → cerveau → choix")
    p.add_argument("--acceleration", type=float, default=1.0, help="faux robot N fois plus vite (essais)")
    p.add_argument("--journal", help="dossier de la boîte noire (par défaut : journal/)")


def _dire(texte: str) -> None:
    print(f"  {texte}", file=sys.stderr, flush=True)  # jamais sur la sortie standard : elle est au protocole MCP


def _port_libre(hote: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((hote, port))
            return True
        except OSError:
            return False


async def _lancer_ecran(systeme, hote: str, port: int):
    """L'écran de la brique 13, sur le MÊME système (sans son propre démarrage : c'est la commande qui démarre)."""
    import uvicorn

    from briques.b13_ecran.serveur import creer_app

    if not _port_libre(hote, port):
        _dire(f"Écran NON lancé : le port {port} est déjà pris. Essayer --port {port + 1}. "
              "Sans écran, personne ne peut accepter une demande du gardien.")
        return None
    serveur = uvicorn.Server(uvicorn.Config(creer_app(systeme), host=hote, port=port, log_level="warning",
                                            access_log=False, lifespan="off"))
    tache = asyncio.create_task(serveur.serve())
    for _ in range(200):
        if serveur.started or tache.done():
            break
        await asyncio.sleep(0.05)
    if not serveur.started:
        _dire("Écran NON lancé (voir le message plus haut).")
        return None
    _dire(f"Écran : http://localhost:{port}/jury  et  http://localhost:{port}  (demandes à accepter : « aides »)")
    return serveur, tache


def main(args: argparse.Namespace, reglages: dict | None = None) -> int:
    from commun.systeme import Systeme, charger_reglages

    from .porte import NOM_PERMIS, PorteDesAgents, ReglagesPorte
    from .serveur_mcp import creer_serveur

    r = copy.deepcopy(reglages or charger_reglages())
    if args.robot:
        r["robot"]["carte"] = args.robot
    if args.cerveau:
        r["cerveau"]["choix"] = args.cerveau
    if r["robot"]["adaptateur"] != "faux_robot" or r["robot"].get("vrai_robot"):
        _dire("Vrai robot : la porte des agents ne se lance que sur le FAUX robot pour l'instant "
              "(feu orange : décision de Hiba). Rien n'a été lancé.")
        return 2
    # Relecture du lot C : l'agent tourne sur CET ordinateur ; sans code, il pourrait appuyer lui-même sur les boutons des
    # humains (accepter sa demande, réarmer). L'écran de la porte exige donc le code d'équipe, même en local.
    from briques.b13_ecran.serveur import code_equipe_de

    r.setdefault("ecran", {})["local_sans_code"] = False
    if not code_equipe_de(r):
        _dire("Pas de code d'équipe : refusé. Sans lui, l'agent pourrait accepter lui-même ses demandes ou réarmer le "
              "robot. Donner le code par la variable LEUKERBAD_CODE_EQUIPE (mieux que reglages.yaml, qu'un agent peut "
              "lire). Rien n'a été lancé.")
        return 2
    _dire("ATTENTION : un agent qui a un terminal ou l'accès aux fichiers de cet ordinateur peut trouver le code "
          "d'équipe (dans reglages.yaml, ou dans la variable LEUKERBAD_CODE_EQUIPE d'un programme) et accepter lui-même "
          "ses demandes. La vraie garde : un agent SANS terminal ni accès aux fichiers ici (réglage de l'assistant de code : "
          "feu orange, décision de Hiba). Et l'écran principal : ecran.local_sans_code: false dans reglages.yaml.")
    if not NOM_PERMIS.match(args.agent):  # avant le système : pas de journal vide pour rien
        _dire(f"nom d'agent « {args.agent} » : lettres minuscules, chiffres, - ou _ (30 au plus). Rien n'a été lancé.")
        return 2
    try:
        reglages_porte = ReglagesPorte.depuis(r)
        systeme = Systeme(r, acceleration=args.acceleration, **({"dossier_journal": args.journal} if args.journal else {}))
        porte = PorteDesAgents(systeme, nom=args.agent, reglages=reglages_porte)
    except ValueError as e:
        _dire(str(e))
        return 2
    if systeme.prise.carte().vrai_robot:
        _dire("La carte dit « vrai robot » : refusé (faux robot seulement). Rien n'a été lancé.")
        return 2

    @asynccontextmanager
    async def cycle():
        await systeme.demarrer()
        ecran = None
        try:
            await porte.ouvrir("stdio")
            if not args.sans_ecran:
                ecran = await _lancer_ecran(systeme, r["ecran"]["hote"], args.port or reglages_porte.port_ecran)
            _dire(f"Porte des agents ouverte pour « {porte.source} » — {systeme.prise.carte().mention_test()}. "
                  f"Accord d'un humain : {'oui' if porte.accord_humain else 'non'} ; "
                  f"{reglages_porte.ordres_par_minute} ordres par minute au plus.")
            yield
        finally:
            if ecran:
                ecran[0].should_exit = True
                await ecran[1]
            await systeme.arreter()

    try:
        asyncio.run(creer_serveur(porte, cycle).run_stdio_async())
    except KeyboardInterrupt:
        pass
    _dire(f"Porte fermée. Journal : {systeme.boite_noire.fichier}")
    return 0
