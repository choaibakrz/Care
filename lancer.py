#!/usr/bin/env python3
"""UNE commande pour tout lancer.

    python3 lancer.py                 lance l'écran + le faux robot (http://<cet-ordinateur>:8000)
    python3 lancer.py --robot bras    même chose avec le faux bras (ou chien, humanoide)
    python3 lancer.py tests           lance tous les tests, Internet coupé pour le programme
    python3 lancer.py demo            petite démonstration dans le terminal, puis la fiche de vérité
    python3 lancer.py rejouer [FICHIER]   rejoue un journal de la boîte noire
    python3 lancer.py micro           parler au faux robot avec le micro du Mac (écran sur http://localhost:8000)
    python3 lancer.py micro --declenchement bouton   (touche Entrée = « je parle »)
    python3 lancer.py banc-voix       mesurer l'écoute (calme / foule) et le temps de réponse
    python3 lancer.py enregistrer gsw enregistrer des ordres en suisse allemand pour le banc d'essai
    python3 lancer.py cerveau         lancer Apertus (8B, et 4B au besoin) sur cet ordinateur ; --partager pour l'autre Mac
    python3 lancer.py banc-cerveau    30 demandes × 6 langues pour chaque cerveau (bonnes actions, temps)
    python3 lancer.py scenario FICHIER [--repetition] [--panne robot@3] [--acceleration 20]   jouer une démonstration
    python3 lancer.py kit-samedi DEFI.md --sortie plan.md   lire le défi (hors ligne) et rendre un plan de 48 h
    python3 lancer.py porte-agents --agent assistant   un agent d'IA parle au faux robot (MCP sur stdio), sous le gardien
    python3 lancer.py brancher NOM --genre chien --chemin sdk   créer l'adaptateur d'un vrai robot (BRANCHER_UN_ROBOT.md)
    python3 lancer.py verif-rapide    la clinique en boîte : les vérifications courtes (moins de deux minutes)
    python3 lancer.py repetition      la clinique en boîte : la grande répétition, quatorze étapes sur le faux robot
    python3 lancer.py essais          la clinique en boîte : les essais comptés, vingt fois le scénario (long)
    python3 lancer.py brancher-carte CARTE [--je-commence]  la clinique en boîte : une carte sur le faux robot, chronomètre en main
    python3 lancer.py apertus-essai                 la clinique en boîte : un essai du vrai Apertus sur cet ordinateur, mesuré (faux robot)
    python3 lancer.py resume-apertus                la clinique en boîte : le résumé du médecin écrit par le vrai Apertus, mesuré
    python3 lancer.py papiers-apertus               la clinique en boîte : le rangement des papiers par le vrai Apertus, mesuré
    python3 lancer.py tirage-apertus 1              la clinique en boîte : le tirage, chaque demande comprise par le vrai Apertus, mesuré
    python3 lancer.py chaine-mesure                 la clinique en boîte : l'écoute, le vrai Apertus et la voix ensemble, temps et mémoire
    python3 lancer.py interprete-mesure             la clinique en boîte : le mode interprète, dix phrases françaises → anglais (écran et voix), mesuré
    python3 lancer.py panne-reprise                 la clinique en boîte : une panne de robot, la reprise par le plus proche (robots simulés)
    python3 lancer.py a-vous [--langue de] [--point 5] [--objet "une guitare"]   la clinique en boîte : « À vous », le jury change le scénario
    python3 lancer.py seance-unique [--vite]        la clinique en boîte : les scènes jouées d'un seul trait par le chef de démonstration
    python3 lancer.py concours [--court]            la clinique en boîte : les sept contrôles du concours, sur le faux robot
    python3 lancer.py preuves [--court]             la clinique en boîte : les huit preuves du jury, jouées sur le faux robot
    python3 lancer.py telephones                    la clinique en boîte : chaque écran ouvert par l'adresse du Wi-Fi, comme un téléphone
    python3 lancer.py rejeu-autonome [DOSSIER]      la clinique en boîte : une répétition, puis un dossier de pages qui la rejouent (double-clic)
    python3 lancer.py invite-essai                  la clinique en boîte : les quatre boutons de l'invité dans six ordres, et la taille du texte
    python3 lancer.py tirage 1 2 3                  la clinique en boîte : des demandes tirées au hasard, et « gestes interdits exécutés »
    python3 lancer.py endurance --duree 5m          la clinique en boîte : le scénario en boucle, jusqu'au premier arrêt imprévu
    python3 lancer.py cartes                        la clinique en boîte : les cartes de rôle des robots
    python3 lancer.py monde-robots                  la clinique en boîte : plusieurs faux robots dans le même monde (simulé, sans physique)
    python3 lancer.py accueil-voix --essai          la clinique en boîte : l'accueil du hall à la voix (écoute, réponse dite, plan B)
    python3 lancer.py ecoute-mesure [--phrases N]   la clinique en boîte : mesurer l'écoute sur les vraies voix du dépôt (une minute)
    python3 lancer.py papiers-images [--fabriquer]  la clinique en boîte : lire les papiers depuis une image (sur un Mac)
    python3 lancer.py moments [FICHIER]  la clinique en boîte : les moments marquants d'une séance (échecs, refus, pannes)
    python3 lancer.py pannes [NOM]    la clinique en boîte : les pannes provoquées (la liste, ou une panne sur le faux robot)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
VENV_PY = RACINE / ".venv" / "bin" / "python"


def _dans_le_venv() -> None:
    """Relance automatiquement dans l'environnement Python du projet s'il existe."""
    if VENV_PY.exists() and Path(sys.prefix).resolve() != (RACINE / ".venv").resolve():
        os.execv(str(VENV_PY), [str(VENV_PY), *sys.argv])


def _reglages(robot: str | None) -> dict:
    from commun.systeme import charger_reglages

    r = charger_reglages()
    if robot:
        r["robot"]["carte"] = robot
    return r


def serveur(args) -> int:
    import uvicorn

    from briques.b13_ecran.serveur import creer_app
    from commun.systeme import Systeme

    reglages = _reglages(args.robot)
    from briques.clinique.coursier import monde_de_la_clinique
    from briques.clinique.table_des_robots import ajouter_les_directions
    # Le monde de l'ossature, plus le plan de la clinique, plus les directions que la tête du robot connaît (s'il en a).
    systeme = Systeme(reglages, monde=ajouter_les_directions(monde_de_la_clinique(), reglages["robot"]["adaptateur"]))
    app = creer_app(systeme)
    # La clinique en boîte : ses écrans s'ajoutent à l'écran de l'ossature (pages /clinique). Voir DECISIONS.md.
    from briques.clinique.ecrans import adresse_du_reseau_local, brancher_ecrans
    from briques.clinique.horloge import HorlogeDeDemonstration
    brancher_ecrans(app, horloge=HorlogeDeDemonstration(bus=systeme.bus), systeme=systeme)
    hote, port = reglages["ecran"]["hote"], args.port or reglages["ecran"]["port"]
    adresse = adresse_du_reseau_local() or "<adresse-de-cet-ordinateur>"
    print(f"\n  Écran : http://localhost:{port}   (depuis un autre ordinateur du Wi-Fi : http://{adresse}:{port})")
    print(f"  Clinique en boîte (données inventées) : http://{adresse}:{port}/clinique")
    carte = systeme.prise.carte()  # la mention vient de la carte du robot, jamais d'un texte fixe
    print(f"  Robot : {carte.id} — {carte.mention_test()}. Ctrl+C pour arrêter.\n")
    uvicorn.run(app, host=hote, port=port, log_level="warning")
    return 0


def tests(args) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "-q", *args.reste], cwd=RACINE)


def demo(args) -> int:
    from briques.b12_boite_noire.fiche import calculer
    from commun.systeme import Systeme

    async def jouer() -> None:
        s = Systeme(_reglages(args.robot), acceleration=10)
        await s.demarrer()
        phrases = [("Va à la cuisine", "fr"), ("Geh zum Tisch", "de"), ("Go to the stage", "en"), ("去入口", "zh"),
                   ("Va à la cuisine à 5 mètres par seconde", "fr"), ("va", "fr"), ("Salue", "fr"), ("Batterie ?", "fr")]
        for texte, langue in phrases:
            r = await s.chaine.traiter(texte, langue)
            print(f"  [{langue}] {texte!r:42} → {' / '.join(r.reponses)}")
        await s.arreter()
        print(f"\n  Journal : {s.boite_noire.fichier}")
        print(calculer(s.bus.historique).model_dump_json(indent=2))

    asyncio.run(jouer())
    return 0


def banc_voix(args) -> int:
    from briques.b04_oreilles_voix.banc_voix import main

    return main(args.reste)


def banc_cerveau(args) -> int:
    from briques.b06_cerveau.banc_cerveau import main

    return main(args.reste)


def cerveau(args) -> int:
    """Lancer les modèles (Apertus) de reglages.yaml sur cet ordinateur et attendre (Ctrl+C pour arrêter).
    Deux Mac : sur l'iMac, « python3 lancer.py cerveau --partager » les rend joignables depuis le MacBook."""
    import time

    from commun.systeme import charger_reglages, creer_serveurs

    reglages = charger_reglages()
    serveurs = creer_serveurs(reglages)
    # Seulement les « toujours » : le 4B (« au besoin ») n'est lancé que si le 8B tombe (mémoire).
    noms = args.noms.split(",") if args.noms else [n for n, s in serveurs.items() if s.demarrage == "toujours"]
    for nom in noms:
        s = serveurs[nom]
        if args.partager:
            s.hote = "0.0.0.0"
        if not s.modele.exists():
            print(f"  {nom} : modèle absent ({s.modele}) — outils/telecharger.py")
            continue
        s.lancer()
        print(f"  {nom} : démarrage sur le port {s.port}…", flush=True)
        print(f"  {nom} : {'prêt' if s.attendre(180) else 'NE DÉMARRE PAS'}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        for s in serveurs.values():
            s.eteindre()
    return 0


def micro(args) -> int:
    from briques.b04_oreilles_voix.micro_direct import main

    return main(args)


def enregistrer(args) -> int:
    from briques.b04_oreilles_voix.enregistrer import main

    return main(args.langue, args.prenom)


def scenario(args) -> int:
    from briques.b15_chef_demo.commande import main

    return main(args)


def rejouer(args) -> int:
    from briques.b12_boite_noire.rejeu import main

    return main([args.fichier] if args.fichier else [])


def kit_samedi(args) -> int:
    from briques.b17_kit_samedi.kit import main

    options = (["--sortie", args.sortie] if args.sortie else []) + (["--scenario", args.scenario] if args.scenario else [])
    return main([args.defi, *options])


def porte_agents(args) -> int:
    from briques.b14_porte_agents.commande import main

    return main(args)
def brancher(args) -> int:
    from briques.b03_adaptateurs.assistant import main

    return main(args.reste)


def verif_rapide(args) -> int:
    from briques.clinique.verif_rapide import main

    return main(args.reste)


def repetition(args) -> int:
    from briques.clinique.repetition import main

    return main(args.reste)


def essais(args) -> int:
    from briques.clinique.essais import main

    return main(args.reste)


def pannes(args) -> int:
    from briques.clinique.pannes import main

    return main(args.reste)


def moments(args) -> int:
    from briques.clinique.moments import main

    return main(args.reste)


def brancher_carte(args) -> int:
    from briques.clinique.brancher import main

    return main(args.reste)


def papiers_images(args) -> int:
    from briques.clinique.papiers_images import main

    return main(args.reste)


def ecoute_mesure(args) -> int:
    from briques.clinique.ecoute import main

    return main(args.reste)


def apertus_essai(args) -> int:
    from briques.clinique.apertus_essai import main

    return main(args.reste)


def resume_apertus(args) -> int:
    from briques.clinique.resume_apertus import main

    return main(args.reste)


def papiers_apertus(args) -> int:
    from briques.clinique.papiers_apertus import main

    return main(args.reste)


def tirage_apertus(args) -> int:
    from briques.clinique.tirage_apertus import main

    return main(args.reste)


def chaine_mesure(args) -> int:
    from briques.clinique.chaine_mesure import main

    return main(args.reste)


def interprete_mesure(args) -> int:
    from briques.clinique.interprete import main

    return main(args.reste)


def seance_unique(args) -> int:
    """La clinique en boîte : la répétition d'un seul trait, jouée par le chef de démonstration (N03)."""
    from briques.clinique.seance_unique import main

    return main(args.reste)


def concours(args) -> int:
    """La clinique en boîte : la commande du concours (avenant 2, partie 6)."""
    from briques.clinique.concours import main

    return main(args.reste)


def preuves(args) -> int:
    """La clinique en boîte : la commande des preuves (avenant jury, J07)."""
    from briques.clinique.preuves import main

    return main(args.reste)


def telephones(args) -> int:
    """La clinique en boîte : les écrans ouverts par l'adresse du Wi-Fi (T30)."""
    from briques.clinique.reseau_local import main

    return main(args.reste)


def rejeu_autonome(args) -> int:
    """La clinique en boîte : le rejeu autonome d'une répétition (cahier 5.11)."""
    from briques.clinique.rejeu_autonome import main

    return main(args.reste)


def invite_essai(args) -> int:
    """La clinique en boîte : l'invité aux commandes, essayé dans six ordres (avenant 2, K07)."""
    from briques.clinique.invite_essai import main

    return main(args.reste)


def a_vous(args) -> int:
    """La clinique en boîte : « À vous » — le jury change le scénario sans toucher au code (cahier 4.3)."""
    from briques.clinique import a_vous as piece

    return piece.main(args.reste)


def panne_reprise(args) -> int:
    from briques.clinique.panne_reprise import main

    return main(args.reste)


def tirage(args) -> int:
    from briques.clinique.tirage import main

    return main(args.reste)


def endurance(args) -> int:
    from briques.clinique.endurance import main

    return main(args.reste)


def cartes(args) -> int:
    from briques.clinique.cartes import main

    return main(args.reste)


def monde_robots(args) -> int:
    from briques.clinique.monde_robots import main

    return main(args.reste)


def accueil_voix(args) -> int:
    from briques.clinique.accueil_voix import main

    return main(args.reste)


def main() -> int:
    _dans_le_venv()
    sys.path.insert(0, str(RACINE))
    from commun.systeme import preparer_reglages

    if preparer_reglages():
        print("  reglages.yaml créé à partir de l'exemple. Pensez à y écrire le code d'équipe (ecran.code_equipe).",
              file=sys.stderr)  # sortie d'erreur : la sortie standard de « porte-agents » est au protocole MCP
    p = argparse.ArgumentParser(description="Carnaval : lancer l'ossature")
    p.add_argument("--robot", choices=["humanoide", "chien", "bras"], help="carte du faux robot")
    p.add_argument("--port", type=int)
    sous = p.add_subparsers(dest="commande")
    t = sous.add_parser("tests"); t.add_argument("reste", nargs=argparse.REMAINDER)
    sous.add_parser("demo")
    r = sous.add_parser("rejouer"); r.add_argument("fichier", nargs="?")
    b = sous.add_parser("banc-voix"); b.add_argument("reste", nargs=argparse.REMAINDER)
    m = sous.add_parser("micro", help="parler au faux robot avec le micro du Mac")
    m.add_argument("--declenchement", choices=["toujours", "mot_d_appel", "bouton"])
    m.add_argument("--langue", help="forcer une langue (fr, de, gsw, it, en, zh)")
    m.add_argument("--fichier", help="un enregistrement .wav à la place du micro (pour essayer sans parler)")
    m.add_argument("--sans-ecran", action="store_true")
    m.add_argument("--robot", choices=["humanoide", "chien", "bras"])
    sous.add_parser("banc-cerveau", help="30 demandes × 6 langues pour chaque cerveau")
    c = sous.add_parser("cerveau", help="lancer les modèles Apertus de reglages.yaml sur cet ordinateur")
    c.add_argument("--noms", help="ex. apertus_8b"); c.add_argument("--partager", action="store_true")
    e = sous.add_parser("enregistrer", help="enregistrer des ordres pour le banc d'essai")
    e.add_argument("langue"); e.add_argument("--prenom", default="equipe")
    from briques.b15_chef_demo.commande import options
    options(sous.add_parser("scenario", help="jouer un scénario de démonstration, avec plans B (brique 15)"))
    k = sous.add_parser("kit-samedi", help="lire le texte du défi (hors ligne) et rendre un plan de 48 heures")
    k.add_argument("defi"); k.add_argument("--sortie"); k.add_argument("--scenario")
    from briques.b14_porte_agents.commande import options as options_porte
    options_porte(sous.add_parser("porte-agents", help="un agent d'IA parle au faux robot (MCP), sous le gardien"))
    sous.add_parser("brancher", help="créer et tester l'adaptateur d'un vrai robot (brique 3, BRANCHER_UN_ROBOT.md)")
    sous.add_parser("verif-rapide", help="la clinique en boîte : les vérifications courtes")
    sous.add_parser("repetition", help="la clinique en boîte : la grande répétition")
    sous.add_parser("essais", help="la clinique en boîte : les essais comptés (vingt fois le scénario)")
    sous.add_parser("pannes", help="la clinique en boîte : les pannes provoquées")
    sous.add_parser("moments", help="la clinique en boîte : les moments marquants d'une séance")
    sous.add_parser("brancher-carte", help="la clinique en boîte : une carte sur le faux robot, test de conformité et chronomètre")
    sous.add_parser("papiers-images", help="la clinique en boîte : lire les papiers depuis une image, mesurer l'erreur de lecture")
    sous.add_parser("ecoute-mesure", help="la clinique en boîte : mesurer l'écoute sur les vraies voix du dépôt")
    sous.add_parser("apertus-essai", help="la clinique en boîte : un essai du vrai Apertus, mesuré (faux robot)")
    sous.add_parser("resume-apertus", help="la clinique en boîte : le résumé du médecin écrit par le vrai Apertus, mesuré")
    sous.add_parser("papiers-apertus", help="la clinique en boîte : le rangement des papiers par le vrai Apertus, mesuré")
    sous.add_parser("tirage-apertus", help="la clinique en boîte : le tirage compris par le vrai Apertus, mesuré (faux robot)")
    sous.add_parser("chaine-mesure", help="la clinique en boîte : l'écoute, le vrai Apertus et la voix ensemble, mesurés")
    sous.add_parser("interprete-mesure", help="la clinique en boîte : le mode interprète (français dit → anglais affiché et dit), mesuré")
    sous.add_parser("seance-unique", help="la clinique en boîte : les scènes jouées d'un seul trait par le chef de démonstration")
    sous.add_parser("concours", help="la clinique en boîte : les sept contrôles du concours, sur le faux robot")
    sous.add_parser("preuves", help="la clinique en boîte : les huit preuves du jury, jouées sur le faux robot")
    sous.add_parser("telephones", help="la clinique en boîte : chaque écran ouvert par l'adresse du Wi-Fi, comme un téléphone")
    sous.add_parser("rejeu-autonome", help="la clinique en boîte : une répétition, puis un dossier de pages qui la rejouent")
    sous.add_parser("invite-essai", help="la clinique en boîte : les quatre boutons de l'invité dans six ordres, et la taille du texte")
    sous.add_parser("a-vous", help="la clinique en boîte : « À vous », le jury change la langue, le point oublié ou l'objet")
    sous.add_parser("panne-reprise", help="la clinique en boîte : une panne de robot et la reprise par le plus proche (robots simulés)")
    sous.add_parser("tirage", help="la clinique en boîte : trente demandes tirées au hasard (un ou plusieurs numéros de tirage)")
    sous.add_parser("endurance", help="la clinique en boîte : rejouer le scénario en boucle pendant une durée (--duree 5m)")
    sous.add_parser("cartes", help="la clinique en boîte : les cartes de rôle des robots (lieux, vitesse, voix, actions)")
    sous.add_parser("monde-robots", help="la clinique en boîte : plusieurs faux robots dans le même monde (simulé, sans physique)")
    sous.add_parser("accueil-voix", help="la clinique en boîte : l'accueil du hall à la voix (un enregistrement, ou --essai)")
    # « tests » et « banc-voix » transmettent tout le reste tel quel (options de pytest ou du banc).
    if len(sys.argv) > 1 and sys.argv[1] in ("tests", "banc-voix", "banc-cerveau", "brancher", "verif-rapide", "repetition", "essais", "pannes", "moments", "brancher-carte", "papiers-images", "ecoute-mesure", "accueil-voix", "monde-robots", "cartes", "endurance", "tirage", "apertus-essai", "resume-apertus", "papiers-apertus", "tirage-apertus", "chaine-mesure", "interprete-mesure", "panne-reprise", "a-vous", "invite-essai", "rejeu-autonome", "telephones", "preuves", "concours", "seance-unique"):
        args = argparse.Namespace(commande=sys.argv[1], reste=sys.argv[2:], robot=None, port=None)
    else:
        args = p.parse_args()
    return {"tests": tests, "demo": demo, "rejouer": rejouer, "banc-voix": banc_voix, "micro": micro,
            "enregistrer": enregistrer, "banc-cerveau": banc_cerveau, "cerveau": cerveau,
            "scenario": scenario, "kit-samedi": kit_samedi, "porte-agents": porte_agents,
            "brancher": brancher, "verif-rapide": verif_rapide, "repetition": repetition, "essais": essais, "pannes": pannes, "moments": moments, "brancher-carte": brancher_carte, "papiers-images": papiers_images, "ecoute-mesure": ecoute_mesure, "accueil-voix": accueil_voix, "monde-robots": monde_robots, "cartes": cartes, "endurance": endurance, "tirage": tirage, "apertus-essai": apertus_essai, "resume-apertus": resume_apertus, "papiers-apertus": papiers_apertus, "tirage-apertus": tirage_apertus, "chaine-mesure": chaine_mesure, "interprete-mesure": interprete_mesure, "panne-reprise": panne_reprise, "a-vous": a_vous, "invite-essai": invite_essai, "rejeu-autonome": rejeu_autonome, "telephones": telephones, "preuves": preuves, "concours": concours, "seance-unique": seance_unique}.get(args.commande, serveur)(args)


if __name__ == "__main__":
    sys.exit(main())
