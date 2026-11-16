"""Test de conformité du robot « roues_deux_bras », prêt à lancer : python3 lancer.py tests briques/b03_adaptateurs/robots/roues_deux_bras

Avec le faux kit seulement : testé sur faux robot. Ce test ne parle JAMAIS au vrai robot, et il n'essaie PAS le
liaison.py de ce dossier (il essaie la mécanique commune, la carte et l'ébauche du chemin avec le faux kit).
Le vrai robot (feu orange, à taper par un humain) : python3 lancer.py brancher roues_deux_bras --conformite --vrai
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
    assert set(ROBOT.LiaisonRouesDeuxBras.branchees) <= set(ACTIONS)
    print("\n".join(reste_a_brancher(ICI)))
