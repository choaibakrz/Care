"""Adaptateur du robot « roues_ros2 » (roues, chemin ros2). Créé par l'assistant le 12.11.2026 13:42.

PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot. fabriquer(vrai=False) : une DOUBLURE à la place du robot
(le faux ROS 2 du projet), avec la vraie liaison de ce dossier : testé sur faux robot.
Seule la prise appelle cet adaptateur. Il se fabrique dans commun/systeme.py (par briques/b03_adaptateurs/registre.py)
ou pour le test de conformité : python3 lancer.py brancher roues_ros2 --conformite
"""
from __future__ import annotations

from pathlib import Path

from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import MESSAGES, FauxRclpy
from .liaison import LiaisonRouesRos2, creer_ros2

CARTE = Path(__file__).with_name("carte.yaml")
_VRAI_KIT: list = []  # le vrai kit, créé une seule fois par programme (le relancer peut gêner certains kits : à vérifier)


def fabriquer(vrai: bool = False, lent: bool = False, acceleration: float = 1.0, **options) -> AdaptateurModele:
    """vrai=False : la doublure (testé sur faux robot). vrai=True : le VRAI robot — feu orange, après le « oui » de Hiba.
    lent=True : 0,1 m/s ; gestes demandés à mi-vitesse (tenu ou non : à vérifier par kit). Appelé SEULEMENT par
    briques/b03_adaptateurs/registre.py (le système, le test de conformité)."""
    if vrai:
        if not _VRAI_KIT:
            _VRAI_KIT.append(creer_ros2())
        liaison = LiaisonRouesRos2(*_VRAI_KIT[0])
    else:
        liaison = LiaisonRouesRos2(FauxRclpy(acceleration=acceleration), MESSAGES)
    return AdaptateurModele(CARTE, liaison, lent=lent, **options)
