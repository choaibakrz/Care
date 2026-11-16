"""Brique 3 — L'assistant « brancher un robot ». N'envoie RIEN à un robot, sauf avec --vrai (feu orange, phrase tapée).

    python3 lancer.py brancher NOM --genre humanoide|chien|bras|roues --chemin sdk|ros2
        crée briques/b03_adaptateurs/robots/NOM/ à partir du modèle vide : carte, liaison, adaptateur, test.
    python3 lancer.py brancher NOM --conformite
        test de conformité avec le FAUX kit (testé sur faux robot) : sans mouvement, puis complet. Il essaie la
        mécanique commune, la carte et l'ÉBAUCHE du chemin — PAS le liaison.py du robot (seul --vrai l'essaie).
    python3 lancer.py brancher NOM --conformite --vrai             FEU ORANGE : vrai robot, sans mouvement.
    python3 lancer.py brancher NOM --conformite --vrai --complet   FEU ORANGE : vrai robot, mouvements lents.

La phrase à taper (avec un nombre tiré au hasard) protège contre l'OUBLI, pas contre un agent ou un script :
la vraie garde est le feu orange (le « oui » de Hiba, le responsable sécurité, la main sur l'arrêt physique).
Le guide pas à pas : BRANCHER_UN_ROBOT.md (à la racine du projet).
"""
from __future__ import annotations

import argparse
import asyncio
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from briques.b01_prise.conformite import Controle
from briques.b01_prise.carte import CarteIdentite

from . import conformite_deux_temps as conformite
from .registre import DOSSIER_ROBOTS, charger_robot, empreintes, fabrique_pour_conformite, nom_valide

ICI = Path(__file__).resolve().parent
__all__ = ["DOSSIER_ROBOTS", "charger_robot", "nom_valide", "creer", "main", "reste_a_brancher", "lancer_conformite"]
MODELE_VIDE = ICI / "modele_vide"
GENRES = ("humanoide", "chien", "bras", "roues")
EBAUCHES = {"sdk": ICI / "chemins" / "sdk" / "liaison_sdk.py", "ros2": ICI / "chemins" / "ros2" / "liaison_ros2.py"}
# Des propositions selon le genre, à vérifier dans la doc du robot : la carte commence avec arreter et etat seulement.
PROPOSITIONS = {
    "humanoide": ["se_deplacer", "regarder", "parler", "montrer", "rejouer_geste"],
    "chien": ["se_deplacer", "rejouer_geste"],
    "bras": ["saisir", "poser", "montrer", "rejouer_geste"],
    "roues": ["se_deplacer", "parler"],
}
MARQUE = "À BRANCHER"

ADAPTATEUR = '''"""Adaptateur du robot « {{nom}} » ({{genre}}, chemin {{chemin}}). Créé par l'assistant le {{date}}.

NON TESTÉ SUR VRAI ROBOT. fabriquer(vrai=False) : faux kit, testé sur faux robot.
Seule la prise appelle cet adaptateur. Il se fabrique dans commun/systeme.py (par briques/b03_adaptateurs/registre.py)
ou pour le test de conformité : python3 lancer.py brancher {{nom}} --conformite
"""
from __future__ import annotations

from pathlib import Path

from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
{{imports_faux}}
from .liaison import {{imports_liaison}}

CARTE = Path(__file__).with_name("carte.yaml")
_VRAI_KIT: list = []  # le vrai kit, créé une seule fois par programme (le relancer peut gêner certains kits : à vérifier)


def fabriquer(vrai: bool = False, lent: bool = False, acceleration: float = 1.0, **options) -> AdaptateurModele:
    """vrai=False : le faux kit (testé sur faux robot). vrai=True : le VRAI robot — feu orange, après le « oui » de Hiba.
    lent=True : 0,1 m/s ; gestes demandés à mi-vitesse (tenu ou non : à vérifier par kit). Appelé SEULEMENT par
    briques/b03_adaptateurs/registre.py (le système, le test de conformité)."""
    if vrai:
        if not _VRAI_KIT:
            _VRAI_KIT.append({{creer_vrai}})
        liaison = {{classe}}({{args_vrai}})
    else:
        liaison = {{liaison_fausse}}
    return AdaptateurModele(CARTE, liaison, lent=lent, **options)
'''

TEST = '''"""Test de conformité du robot « {{nom}} », prêt à lancer : python3 lancer.py tests {{dossier}}

Avec le faux kit seulement : testé sur faux robot. Ce test ne parle JAMAIS au vrai robot, et il n'essaie PAS le
liaison.py de ce dossier (il essaie la mécanique commune, la carte et l'ébauche du chemin avec le faux kit).
Le vrai robot (feu orange, à taper par un humain) : python3 lancer.py brancher {{nom}} --conformite --vrai
"""
import asyncio
from pathlib import Path

from briques.b01_prise.actions import ACTIONS
from briques.b01_prise.carte import CarteIdentite
from briques.b03_adaptateurs import conformite_deux_temps as conformite
from briques.b03_adaptateurs.assistant import reste_a_brancher
from briques.b03_adaptateurs.registre import charger_robot

ICI = Path(__file__).resolve().parents[1]
ROBOT = charger_robot(ICI.name, ICI.parent)


def _faux():
    return ROBOT.fabriquer(vrai=False, acceleration=5)


def test_la_carte_du_robot_est_valide():
    carte = CarteIdentite.charger(ICI / "carte.yaml")
    assert carte.sait("arreter") and carte.sait("etat")


def test_sans_mouvement_avec_le_faux_kit():
    rapport = asyncio.run(conformite.sans_mouvement(_faux, vrai_attendu=False))
    assert rapport.reussi, rapport.texte()
    assert rapport.mention == "testé sur faux robot"


def test_complet_avec_le_faux_kit():
    rapport = asyncio.run(conformite.complet(_faux, vrai_attendu=False))
    assert rapport.reussi, rapport.texte()


def test_la_vraie_liaison_se_charge_sans_parler_au_robot():
    """Charger le fichier ne lance rien : le vrai kit ne s'importe que dans creer_kit / creer_ros2."""
    assert set(ROBOT.{{classe}}.branchees) <= set(ACTIONS)
    print("\\n".join(reste_a_brancher(ICI)))
'''

INIT = '''"""Le robot « {{nom}} » ({{genre}}, chemin {{chemin}}). NON TESTÉ SUR VRAI ROBOT. Créé le {{date}}."""
'''

CHEMINS = {
    "sdk": {
        "imports_faux": "from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit\n"
                        "from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK",
        "imports_liaison": "{{classe}}",
        "creer_vrai": "{{classe}}.creer_kit()",
        "args_vrai": "_VRAI_KIT[0]",
        "liaison_fausse": "LiaisonSDK(FauxKit(acceleration=acceleration))",
    },
    "ros2": {
        "imports_faux": "from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import MESSAGES, FauxRclpy\n"
                        "from briques.b03_adaptateurs.chemins.ros2.liaison_ros2 import LiaisonPontROS2",
        "imports_liaison": "{{classe}}, creer_ros2",
        "creer_vrai": "creer_ros2()",
        "args_vrai": "*_VRAI_KIT[0]",
        "liaison_fausse": "LiaisonPontROS2(FauxRclpy(acceleration=acceleration), MESSAGES)",
    },
}


def _remplir(texte: str, valeurs: dict[str, str]) -> str:
    for _ in range(2):  # deux passes : une valeur peut contenir {{classe}}
        for cle, valeur in valeurs.items():
            texte = texte.replace("{{" + cle + "}}", valeur)
    return texte


def nom_de_classe(nom: str) -> str:
    return "Liaison" + "".join(m.capitalize() for m in nom.split("_") if m)


def copier_liaison(chemin: str, classe: str, nom: str, date: str) -> str:
    """La liaison du robot : une copie de l'ébauche du chemin, avec son nom, et RIEN de branché au départ."""
    source = EBAUCHES[chemin].read_text(encoding="utf-8")
    lignes = []
    for ligne in source.splitlines():
        if "# gabarit:classe" in ligne:
            ligne = f"class {classe}(LiaisonVide):"
        elif "# gabarit:branchees" in ligne:
            ligne = ("    # " + MARQUE + " : ajouter chaque action quand elle est écrite ET essayée sur le robot, "
                     "ex. frozenset({\"arreter\", \"etat\"}).\n    branchees: frozenset[str] = frozenset()")
        lignes.append(ligne)
    attention = {"sdk": "Les appels écrits ici sont ceux du FAUX kit (noms inventés) : ils ne marchent pas sur un vrai robot.",
                 "ros2": "Les sujets (SUJETS) et messages écrits ici sont courants ou inventés : à vérifier pour CE robot."}
    entete = (f"# Liaison du robot « {nom} », copiée de {EBAUCHES[chemin].relative_to(ICI.parents[1]).as_posix()} "
              f"par l'assistant le {date}.\n"
              f"# NON TESTÉ SUR VRAI ROBOT. Remplacer chaque ligne « {MARQUE} » par l'appel du vrai robot (doc du "
              f"fabricant).\n# {attention[chemin]}\n")
    return entete + "\n".join(lignes) + "\n"


def carte_du_robot(nom: str, genre: str, chemin: str, date: str) -> str:
    texte = (MODELE_VIDE / "carte.yaml").read_text(encoding="utf-8")
    remplacements = {
        "id: modele-vide ": f"id: {nom.replace('_', '-')} ",
        "nom: Robot à brancher ": f"nom: {nom} ",
        "genre: autre ": f"genre: {genre} ",
        "capacites: [arreter, etat]": (f"capacites: [arreter, etat]\n# Proposition pour un robot « {genre} » (à vérifier "
                                       f"dans la doc, à ajouter UNE PAR UNE) : {PROPOSITIONS[genre]}"),
    }
    for avant, apres in remplacements.items():
        if avant not in texte:
            raise RuntimeError(f"modele_vide/carte.yaml a changé : « {avant} » introuvable")
        texte = texte.replace(avant, apres, 1)
    return f"# Carte du robot « {nom} » ({genre}, chemin {chemin}), créée par l'assistant le {date}.\n" + texte


def creer(nom: str, genre: str, chemin: str, dossier: Path = DOSSIER_ROBOTS, maintenant: datetime | None = None) -> Path:
    """Crée le dossier du robot. Ne touche à aucun robot. Refuse un nom faux ou un dossier qui existe déjà."""
    probleme = nom_valide(nom)
    if probleme:
        raise ValueError(probleme)
    if genre not in GENRES:
        raise ValueError(f"genre inconnu : {genre} (choisir parmi {list(GENRES)})")
    if chemin not in EBAUCHES:
        raise ValueError(f"chemin inconnu : {chemin} (sdk ou ros2)")
    ici = Path(dossier) / nom
    if ici.exists():
        raise ValueError(f"le dossier {ici} existe déjà : rien n'est écrasé")
    maintenant = maintenant or datetime.now()
    date = maintenant.strftime("%d.%m.%Y %H:%M")
    classe = nom_de_classe(nom)
    valeurs = {"nom": nom, "genre": genre, "chemin": chemin, "date": date, "classe": classe, **CHEMINS[chemin]}
    try:
        dossier_affiche = ici.relative_to(ICI.parents[1]).as_posix()
    except ValueError:
        dossier_affiche = str(ici)
    valeurs["dossier"] = dossier_affiche
    (ici / "tests").mkdir(parents=True)
    (ici / "__init__.py").write_text(_remplir(INIT, valeurs), encoding="utf-8")
    (ici / "carte.yaml").write_text(carte_du_robot(nom, genre, chemin, date), encoding="utf-8")
    (ici / "liaison.py").write_text(copier_liaison(chemin, classe, nom, date), encoding="utf-8")
    (ici / "adaptateur.py").write_text(_remplir(ADAPTATEUR, valeurs), encoding="utf-8")
    (ici / "tests" / f"test_conformite_{nom}.py").write_text(_remplir(TEST, valeurs), encoding="utf-8")
    (ici / "branchement.yaml").write_text(yaml.safe_dump(
        {"nom": nom, "genre": genre, "chemin": chemin, "cree_le": maintenant.isoformat(timespec="seconds")},
        allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ici


def reste_a_brancher(ici: Path) -> list[str]:
    """Les lignes « À BRANCHER » de la liaison et les chiffres « à vérifier » de la carte."""
    lignes = [f"  liaison.py:{n} {l.strip()}" for n, l in
              enumerate((Path(ici) / "liaison.py").read_text(encoding="utf-8").splitlines(), 1) if MARQUE in l]
    carte = (Path(ici) / "carte.yaml").read_text(encoding="utf-8")
    a_verifier = sum(1 for l in carte.splitlines() if "à vérifier" in l and not l.lstrip().startswith("#"))
    return [f"Reste à brancher : {len(lignes)} lignes « {MARQUE} », {a_verifier} lignes « à vérifier » dans la carte.",
            *lignes]


def _minutes_depuis(ici: Path) -> str:
    """Chronomètre « robot inconnu » (idée 12) : le temps depuis la création du dossier."""
    try:
        debut = datetime.fromisoformat(yaml.safe_load((ici / "branchement.yaml").read_text(encoding="utf-8"))["cree_le"])
        return f"Chronomètre : {(datetime.now() - debut).total_seconds() / 60:.0f} min depuis le début du branchement."
    except Exception:
        return "Chronomètre : début du branchement inconnu."


def _noter(ici: Path, temps: str, rapport: conformite.Rapport) -> None:
    """Garde le résultat du VRAI robot dans conformite.yaml (le registre le lit avant d'accepter le vrai robot)."""
    fichier = ici / "conformite.yaml"
    notes = (yaml.safe_load(fichier.read_text(encoding="utf-8")) if fichier.exists() else None) or {}
    notes[temps] = {"date": datetime.now().isoformat(timespec="seconds"), "reussi": rapport.reussi,
                    "mention": rapport.mention, "empreintes": empreintes(ici),  # changer un fichier = refaire le test
                    "controles": [f"{'ok' if c.ok else 'ÉCHEC'} {c.nom} {c.detail}".strip() for c in rapport.controles]}
    fichier.write_text(yaml.safe_dump(notes, allow_unicode=True, sort_keys=False), encoding="utf-8")


def ecran_allume(port: int) -> bool:
    """L'écran (python3 lancer.py) tourne-t-il sur cet ordinateur ? Il aurait déjà sa propre liaison avec le robot."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def lancer_conformite(nom: str, dossier: Path = DOSSIER_ROBOTS, vrai: bool = False, complet: bool = False,
                      lire: Callable[[str], str] | None = None, ecrire: Callable[[str], None] = print,
                      port_ecran: int | None = None) -> int:
    ici = Path(dossier) / nom
    if not (ici / "adaptateur.py").exists():
        ecrire(f"Refusé : pas de robot « {nom} » dans {dossier}. D'abord : python3 lancer.py brancher {nom} "
               f"--genre … --chemin …")
        return 2
    if not vrai:
        rapport = asyncio.run(conformite.complet(fabrique_pour_conformite(nom, dossier), vrai_attendu=False))
        ecrire(rapport.texte())
        ecrire("Faux kit seulement : le vrai robot n'a RIEN reçu. Testé sur faux robot. Ce test n'essaie PAS le "
               "liaison.py du robot (seulement la mécanique, la carte et l'ébauche) : seul --vrai l'essaie.")
        ecrire(_minutes_depuis(ici))
        return 0 if rapport.reussi else 1

    if port_ecran is None:
        from commun.systeme import charger_reglages

        port_ecran = int(charger_reglages()["ecran"]["port"])
    if ecran_allume(port_ecran):
        ecrire(f"Refusé : l'écran tourne déjà (port {port_ecran}). L'arrêter d'abord : une seule liaison avec le robot.")
        return 2
    carte = CarteIdentite.charger(ici / "carte.yaml")
    if not conformite.confirmer(conformite.PHRASE_SANS_MOUVEMENT, conformite.AVERTISSEMENT_SANS_MOUVEMENT, lire, ecrire):
        return 2
    fabrique = fabrique_pour_conformite(nom, dossier, vrai=True, lent=True)
    rapport = asyncio.run(conformite.sans_mouvement(fabrique, vrai_attendu=True))
    ecrire(rapport.texte())
    _noter(ici, "sans_mouvement", rapport)
    ecrire(_minutes_depuis(ici))
    if not rapport.reussi:
        ecrire("\n".join(reste_a_brancher(ici)))
        return 1
    if not complet:
        ecrire(f"Temps 1 réussi. Temps 2, FEU ORANGE (accord de Hiba) : python3 lancer.py brancher {nom} "
               f"--conformite --vrai --complet")
        return 0
    sur_place = not carte.sait("se_deplacer")  # une tête, une main : rien n'« avance », le texte le dit autrement
    avertissement = conformite.AVERTISSEMENT_COMPLET_SUR_PLACE if sur_place else conformite.AVERTISSEMENT_COMPLET
    if not conformite.confirmer(conformite.phrase_complet(carte.id), avertissement, lire, ecrire):
        return 2
    rapport = asyncio.run(conformite.complet(fabrique, vrai_attendu=True))
    if rapport.reussi:
        # 2e relecture du lot C : sans odomètre, le programme ne voit pas un robot parti à l'envers. Un humain le dit.
        if sur_place:
            vu = conformite.confirmer(conformite.PHRASE_SUR_PLACE,
                                      "Regardez le robot : pendant le test, a-t-il fait SEULEMENT le mouvement prévu par sa "
                                      "fiche, sans à-coup et sans rien heurter ? Si vous n'êtes pas sûr, répondez autre "
                                      "chose : le test sera refusé.", lire, ecrire)
        else:
            vu = conformite.confirmer(conformite.PHRASE_SENS,
                                      "Regardez le robot : pendant le test, a-t-il avancé DEVANT lui (et pas en arrière, ni sur "
                                      "le côté) ? Si vous n'êtes pas sûr, répondez autre chose : le test sera refusé.",
                                      lire, ecrire)
        rapport.controles.append(Controle(nom="[complet] sens vérifié à l'œil par un humain", ok=vu,
                                          detail="confirmé" if vu else "non confirmé"))
    ecrire(rapport.texte())
    _noter(ici, "complet", rapport)
    ecrire(_minutes_depuis(ici))
    return 0 if rapport.reussi else 1


def main(argv: list[str] | None = None, lire: Callable[[str], str] | None = None,
         ecrire: Callable[[str], None] = print) -> int:
    p = argparse.ArgumentParser(prog="python3 lancer.py brancher",
                                description="Créer l'adaptateur d'un nouveau robot, puis le tester (BRANCHER_UN_ROBOT.md).")
    p.add_argument("nom", help="nom court du robot, ex. unitree_g1")
    p.add_argument("--genre", choices=GENRES)
    p.add_argument("--chemin", choices=tuple(EBAUCHES), help="sdk : kit Python du fabricant ; ros2 : pont ROS 2")
    p.add_argument("--conformite", action="store_true", help="lancer le test de conformité (faux kit par défaut)")
    p.add_argument("--vrai", action="store_true", help="FEU ORANGE : sur le vrai robot (phrase tapée au clavier)")
    p.add_argument("--complet", action="store_true", help="avec --vrai : ajoute les mouvements lents (feu orange)")
    p.add_argument("--dossier", default=str(DOSSIER_ROBOTS), help=argparse.SUPPRESS)  # pour les tests
    a = p.parse_args(argv)
    dossier = Path(a.dossier)
    if a.conformite:
        return lancer_conformite(a.nom, dossier, vrai=a.vrai, complet=a.complet, lire=lire, ecrire=ecrire)
    if a.vrai or a.complet:
        ecrire("Refusé : --vrai et --complet vont avec --conformite.")
        return 2
    if not (a.genre and a.chemin):
        ecrire("Refusé : pour créer un robot, donner --genre et --chemin (ex. --genre chien --chemin sdk).")
        return 2
    try:
        ici = creer(a.nom, a.genre, a.chemin, dossier)
    except ValueError as e:
        ecrire(f"Refusé : {e}")
        return 2
    ecrire(f"Dossier créé : {ici} — rien n'a été envoyé à un robot. NON TESTÉ SUR VRAI ROBOT.")
    ecrire("  carte.yaml       la carte d'identité (chiffres « à vérifier » : doc du fabricant, lien et date)")
    ecrire("  liaison.py       les appels au robot (copie de l'ébauche : lignes « À BRANCHER »)")
    ecrire("  adaptateur.py    fabriquer(vrai=False) : faux kit ; fabriquer(vrai=True) : vrai robot")
    ecrire(f"  tests/test_conformite_{a.nom}.py   le test prêt à lancer (faux kit)")
    ecrire("\n".join(reste_a_brancher(ici)[:1]))
    ecrire("Ensuite (BRANCHER_UN_ROBOT.md) :")
    ecrire(f"  1. python3 lancer.py brancher {a.nom} --conformite                  (faux kit, doit réussir)")
    ecrire("  2. remplir carte.yaml et liaison.py avec la doc du fabricant (fiches : briques/b03_adaptateurs/fiches/)")
    ecrire(f"  3. FEU ORANGE, à taper par un humain : python3 lancer.py brancher {a.nom} --conformite --vrai")
    ecrire(f"  4. FEU ORANGE, mouvements lents : python3 lancer.py brancher {a.nom} --conformite --vrai --complet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
