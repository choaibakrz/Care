"""T28 — « À vous » : le jury change le scénario, sans toucher au code (cahier 4.3).

    python3 lancer.py a-vous                                   joue les trois choix écrits dans a_vous.yaml
    python3 lancer.py a-vous --langue de                       une autre langue à l'arrivée (it, de, fr, en)
    python3 lancer.py a-vous --point 5                         un autre point oublié dans la liste « installation »
    python3 lancer.py a-vous --objet "une guitare"             un objet demandé au robot ; absent de la réserve : il le dit

Chaque choix rejoue la vraie étape de la répétition (1, 7 ou 8) avec ce changement, par les vraies pièces.
Rien n'est écrit en dur : les langues viennent de l'accueil, les points viennent de la liste du faux dossier, et c'est le
tableau des tâches lui-même qui dit si l'objet est dans la réserve, flou, ou absent.
DIRE VRAI : l'arrivée est tapée (pas de voix) ; les coches sont faites par le programme ; le robot est le faux robot.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

import yaml

from . import repetition

FICHIER = Path(__file__).with_name("a_vous.yaml")
LANGUES = {"it": "italien", "de": "allemand", "fr": "français", "en": "anglais"}


class ChoixImpossible(ValueError):
    """Le choix du jury ne peut pas être joué : on le dit, et on ne joue rien."""


def points_de_la_liste() -> dict[int, str]:
    """Les points de la liste « installation » de la patiente du scénario, lus par la pièce des listes."""
    from .carnet import Carnet
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges

    horloge = HorlogeDeDemonstration()
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), Carnet(horloge=horloge))
    return {p["numero"]: p["nom"] for p in listes.liste(charger_badges()["soignant-etage-2"], "p01", "installation")["points"]}


def sorte_d_objet(objet: str) -> str:
    """« absent », « flou » ou « précis » : c'est le vrai tableau des tâches qui le dit, sur une clinique neuve."""
    from .carnet import Carnet
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges
    from .taches import TableauDesTaches

    horloge = HorlogeDeDemonstration()
    carnet = Carnet(horloge=horloge)
    listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
    rendu = TableauDesTaches(listes.porte, carnet, listes).demander(charger_badges()["soignant-etage-2"], "p01",
                                                                    f"il manque {objet} en chambre 12")
    if rendu["genre"] == "question":
        return "flou"
    return "absent" if (rendu.get("tache") or {}).get("sorte") == "humain" else "précis"


def lire_les_choix(fichier: str | Path) -> dict[str, Any]:
    lus = yaml.safe_load(Path(fichier).read_text(encoding="utf-8")) or {}
    if not isinstance(lus, dict):
        raise ChoixImpossible(f"{Path(fichier).name} : il faut trois lignes « mot: valeur » (langue, point_oublie, objet)")
    return {cle: lus[cle] for cle in ("langue", "point_oublie", "objet") if lus.get(cle) is not None}


def verifier(choix: dict[str, Any]) -> dict[str, Any]:
    """Rend les changements à donner aux étapes. Un choix impossible : une phrase claire, rien n'est joué."""
    changements: dict[str, Any] = {}
    if "langue" in choix:
        langue = str(choix["langue"]).strip().lower()
        if langue not in LANGUES:
            raise ChoixImpossible(f"langue « {choix['langue']} » : l'accueil du prototype connaît "
                                  + ", ".join(f"{code} ({nom})" for code, nom in LANGUES.items()))
        changements["langue"] = langue
    if "point_oublie" in choix:
        points = points_de_la_liste()
        try:
            numero = int(str(choix["point_oublie"]).strip())
        except ValueError:
            raise ChoixImpossible(f"point « {choix['point_oublie']} » : il faut un numéro de point, entre 1 et {max(points)}") from None
        if numero not in points:
            raise ChoixImpossible(f"point {numero} : la liste « installation » a des points entre 1 et {max(points)}")
        changements["point_oublie"] = numero
    if "objet" in choix:
        objet = " ".join(str(choix["objet"]).split())
        if not objet:
            raise ChoixImpossible("objet vide : écrire un objet, avec son petit mot devant (« une guitare »)")
        sorte = sorte_d_objet(objet)
        changements.update(objet=objet, objet_absent=sorte == "absent", objet_flou=sorte == "flou")
    return changements


ETAPES = (("langue", 1, "Une autre langue à l'arrivée"), ("point_oublie", 7, "Un autre point oublié dans la liste"),
          ("objet", 8, "Un objet demandé au robot"))


def jouer(changements: dict[str, Any], ecrire: Callable[[str], None] = print) -> int:
    ratees = 0
    for cle, numero, titre in ETAPES:
        if cle not in changements:
            continue
        plus = ""
        if cle == "objet":
            plus = (" — absent de la réserve" if changements["objet_absent"] else
                    " — flou : plusieurs objets de la réserve y ressemblent" if changements.get("objet_flou") else " — dans la réserve")
        ecrire(f"{titre} : « {changements[cle]} »{plus} (étape {numero} de la répétition, rejouée avec ce changement)")
        with repetition.variation(changements):
            try:
                resultat = repetition.CONTROLES[numero]()
            except Exception as erreur:  # une pièce qui casse : c'est raté, et on le dit
                resultat = repetition.Resultat(False, "SIMULÉ", f"la pièce s'est arrêtée ({type(erreur).__name__} : {erreur})")
        ratees += not resultat.reussie
        ecrire(f"  [{resultat.etiquette}] {'réussie' if resultat.reussie else 'RATÉE'} — {resultat.detail}")
    return ratees


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print, fichier: str | Path | None = None) -> int:
    lecteur = argparse.ArgumentParser(prog="python3 lancer.py a-vous", description="« À vous » : le jury change le scénario.")
    lecteur.add_argument("--langue")
    lecteur.add_argument("--point")
    lecteur.add_argument("--objet")
    options = lecteur.parse_args(reste or [])
    choix = {cle: valeur for cle, valeur in (("langue", options.langue), ("point_oublie", options.point), ("objet", options.objet))
             if valeur is not None}
    ecrire("« À VOUS » — le jury change le scénario — DONNÉES INVENTÉES")
    try:
        if not choix:
            fichier = Path(fichier) if fichier else FICHIER
            choix = lire_les_choix(fichier)
            ecrire(f"Choix lus dans {fichier.name} (changez ce fichier, ou utilisez --langue, --point, --objet).")
        if not choix:
            raise ChoixImpossible("aucun choix : donner --langue, --point ou --objet, ou remplir a_vous.yaml")
        changements = verifier(choix)
    except ChoixImpossible as raison:
        ecrire(f"CHOIX IMPOSSIBLE — {raison}. Rien n'a été joué.")
        return 2
    ratees = jouer(changements, ecrire)
    ecrire("Dire vrai : arrivée tapée au clavier, coches faites par le programme, faux robot. Aucun vrai robot, aucune personne.")
    ecrire("À VOUS : RÉUSSI" if not ratees else f"À VOUS : RATÉ ({ratees} changement{'s' if ratees > 1 else ''})")
    return 0 if not ratees else 1
