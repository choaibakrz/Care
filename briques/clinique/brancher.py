"""Brancher un robot inconnu, chronomètre en main (avenant jury, J04) : la commande, côté carte et faux robot.

    python3 lancer.py brancher-carte plateau --je-commence     le chronomètre part
    python3 lancer.py brancher-carte plateau                   le test de conformité de la prise, sur le faux robot

« Combien de temps pour brancher un robot que vous n'avez jamais vu ? Montrez-le. »
- On donne une carte d'identité (le nom d'une carte du faux robot, ou un fichier .yaml). La commande lance le test de
  conformité de la prise (brique 1) et affiche « contrôles réussis : tant sur tant ».
- Si un contrôle rate, elle dit lequel, et ce qu'il faut corriger, en une phrase.
- Le chronomètre part à « --je-commence ». Il s'arrête seul au premier passage où tous les contrôles réussissent.
- La durée va dans la fiche de vérité, ligne FAUX ROBOT. La ligne RÉEL reste « à mesurer avec le vrai robot » : ce
  programme ne la remplit jamais.

CETTE COMMANDE NE PARLE JAMAIS À UN VRAI ROBOT. Elle fait tourner le faux robot avec la carte donnée. Une carte qui
dit « vrai_robot: true » est refusée : un vrai robot se branche avec la brique 3 (`python3 lancer.py brancher NOM
--conformite --vrai`), par un humain, après un « oui » (feu orange). Voir BRANCHER_UN_ROBOT.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from briques.b01_prise.carte import CarteIdentite
from briques.b01_prise.conformite import verifier_conformite
from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES, cartes_disponibles
from commun.systeme import fabrique_du_faux_robot

DOSSIER = Path(__file__).resolve().parents[2] / "journal" / "clinique"
FICHIER = "branchements.json"
REEL = "à mesurer avec le vrai robot"


def conseil(controle: str) -> str:
    """Pour un contrôle raté : ce qu'il faut corriger, en une phrase."""
    if controle.startswith("carte d'identité"):
        return "relire carte.yaml : il faut les capacités « arreter » et « etat », et des noms d'actions de la prise."
    if controle.startswith("état lisible"):
        return "vérifier la liaison avec le robot (câble, Wi-Fi, adresse), puis la lecture de l'état dans l'adaptateur."
    if controle.startswith("refuse «"):
        return "le gardien doit refuser ce que la carte ne sait pas faire : retirer de « capacites » ce que le robot ne fait pas."
    if controle.startswith("refuse une action sans ticket"):
        return "la prise doit refuser toute action sans ticket du gardien : ne jamais appeler l'adaptateur directement."
    if controle.startswith("action «"):
        nom = controle.split("«")[1].split("»")[0].strip()
        return f"l'action « {nom} » est dans la carte mais ne marche pas : la brancher dans l'adaptateur, ou l'enlever de la carte."
    if controle.startswith("une action longue s'annule"):
        return "un déplacement doit pouvoir être annulé en route : brancher l'annulation (vitesse nulle) dans l'adaptateur."
    if controle.startswith("arrêt d'urgence pendant"):
        return "l'arrêt d'urgence doit couper un mouvement en cours : brancher l'arrêt le plus sûr, choisi avec le responsable sécurité."
    if controle.startswith("bloqué tant que"):
        return "après un arrêt d'urgence, le robot doit refuser tout ordre jusqu'au réarmement par un humain."
    if controle.startswith("arrêt d'urgence immédiat"):
        return "l'arrêt d'urgence doit répondre tout de suite, même à l'arrêt : vérifier l'appel d'arrêt et son délai."
    return "lire le détail de la ligne, puis BRANCHER_UN_ROBOT.md, partie « Si ça coince »."


def _duree(secondes: float) -> str:
    secondes = int(round(secondes))
    return f"{secondes // 60} min {secondes % 60:02d} s" if secondes >= 60 else f"{secondes} s"


def _lire(dossier: Path) -> dict[str, Any]:
    try:
        return json.loads((Path(dossier) / FICHIER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire(dossier: Path, notes: dict[str, Any]) -> None:
    Path(dossier).mkdir(parents=True, exist_ok=True)
    (Path(dossier) / FICHIER).write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")


def _carte(donnee: str) -> tuple[str, CarteIdentite, Path]:
    """Le nom d'une carte du faux robot (« plateau »), ou un fichier .yaml. Rend son nom court, la carte, son fichier."""
    chemin = Path(donnee)
    if chemin.suffix in (".yaml", ".yml") and chemin.exists():
        return chemin.stem, CarteIdentite.charger(chemin), chemin
    if donnee in cartes_disponibles():
        chemin = DOSSIER_CARTES / f"{donnee}.yaml"
        return donnee, CarteIdentite.charger(chemin), chemin
    raise FileNotFoundError(donnee)


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print, dossier: Path = DOSSIER,
         temps: Callable[[], float] = time.time) -> int:
    p = argparse.ArgumentParser(prog="lancer.py brancher-carte",
                                description="La clinique en boîte : brancher une carte d'identité sur le faux robot, chronomètre en main")
    p.add_argument("carte", help="le nom d'une carte du faux robot (ex. plateau), ou un fichier .yaml")
    p.add_argument("--je-commence", action="store_true", help="faire partir le chronomètre (sans lancer le test)")
    a = p.parse_args(reste or [])
    try:
        nom, carte, fichier = _carte(a.carte)
    except FileNotFoundError:
        ecrire(f"Carte inconnue « {a.carte} ». Cartes du faux robot : {', '.join(cartes_disponibles())}. Ou donner un fichier .yaml.")
        return 2
    except Exception as erreur:  # une carte mal écrite : le dire en clair
        ecrire(f"Carte illisible « {a.carte} » : {erreur}")
        return 2
    if carte.vrai_robot:
        ecrire(f"Refusé : la carte « {carte.nom} » dit « vrai_robot: true ». Cette commande ne parle jamais à un vrai robot. "
               "Un vrai robot se branche avec la brique 3, par un humain, après un « oui » de Hiba : "
               "python3 lancer.py brancher NOM --conformite --vrai (BRANCHER_UN_ROBOT.md).")
        return 2
    if fichier.parent != DOSSIER_CARTES:
        ecrire(f"Refusé : le faux robot ne lit ses cartes que dans {DOSSIER_CARTES}. Copier la carte là, puis donner son nom.")
        return 2
    notes = _lire(dossier)
    if a.je_commence:
        notes[nom] = {"debut": temps(), "debut_lisible": datetime.now().isoformat(timespec="seconds"), "fin": None,
                      "duree_s": None, "passages": 0, "etiquette": "FAUX ROBOT", "robot": carte.nom}
        _ecrire(dossier, notes)
        ecrire(f"« Je commence » : chronomètre : parti pour la carte « {nom} » ({carte.nom}). Il s'arrêtera seul quand tous "
               f"les contrôles réussiront : python3 lancer.py brancher-carte {nom}")
        return 0
    ecrire(f"BRANCHER UNE CARTE — {carte.nom} — FAUX ROBOT ({carte.mention_test()}) — aucun vrai robot n'est touché")
    # le faux robot se fabrique dans commun/systeme.py seulement ; le test l'entoure d'une prise et d'un gardien
    rapport = asyncio.run(verifier_conformite(fabrique_du_faux_robot(nom, acceleration=20.0), complet=True))
    reussis = sum(1 for c in rapport.controles if c.ok)
    for c in rapport.controles:
        ligne = f"  {'✔' if c.ok else '✘'} {c.nom}" + (f" — {c.detail}" if c.detail else "")
        ecrire(ligne if c.ok else f"{ligne} → à corriger : {conseil(c.nom)}")
    ecrire(f"contrôles réussis : {reussis} sur {len(rapport.controles)} ({rapport.mention})")
    note = notes.get(nom)
    if note is None or note.get("debut") is None:
        ecrire(f"chronomètre : pas démarré (pour le faire partir : python3 lancer.py brancher-carte {nom} --je-commence)")
    elif note.get("fin") is not None:
        ecrire(f"chronomètre déjà arrêté : {_duree(note['duree_s'])}, {note['passages']} passage(s) du test (FAUX ROBOT)")
    else:
        note["passages"] += 1
        if rapport.reussi:
            note["fin"], note["duree_s"] = temps(), int(round(temps() - note["debut"]))
            note["fin_lisible"] = datetime.now().isoformat(timespec="seconds")
            ecrire(f"chronomètre arrêté : {_duree(note['duree_s'])}, {note['passages']} passage{'s' if note['passages'] > 1 else ''} "
                   f"du test — FAUX ROBOT. Sur un vrai robot : {REEL}.")
        else:
            ecrire(f"chronomètre : {_duree(temps() - note['debut'])}, il tourne encore (il s'arrêtera quand tout réussira)")
        _ecrire(dossier, notes)
    return 0 if rapport.reussi else 1
