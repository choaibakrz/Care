"""Test de conformité du robot « leadtron_dh116 », prêt à lancer : python3 lancer.py tests briques/b03_adaptateurs/robots/leadtron_dh116

NON TESTÉ SUR VRAI ROBOT. Avec la doublure seulement (doublure.py) : testé sur faux robot. Ce test ne parle JAMAIS à la
vraie main. Ici, il essaie bien la VRAIE liaison de ce dossier (liaison.py), avec la doublure à la place de la main.
La vraie main (feu orange, à taper par un humain) : python3 lancer.py brancher leadtron_dh116 --conformite --vrai
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
    """Charger le fichier ne lance rien : le vrai kit ne s'importe que dans creer_kit (classe KitDeLaMain)."""
    assert set(ROBOT.LiaisonLeadtronDh116.branchees) <= set(ACTIONS)
    print("\n".join(reste_a_brancher(ICI)))
