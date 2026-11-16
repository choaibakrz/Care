"""Adaptateur du robot « reachy_mini » (créé comme « humanoide » par l'assistant ; sa carte dit « autre » : une tête posée sur une table ; chemin sdk). Créé par l'assistant le 14.11.2026 23:53.

NON TESTÉ SUR VRAI ROBOT. fabriquer(vrai=False) : une DOUBLURE à la place du robot (doublure.py), avec la vraie
liaison de ce dossier : testé sur faux robot.
Seule la prise appelle cet adaptateur. Il se fabrique dans commun/systeme.py (par briques/b03_adaptateurs/registre.py)
ou pour le test de conformité : python3 lancer.py brancher reachy_mini --conformite
"""
from __future__ import annotations

from pathlib import Path

from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from .doublure import DoublureReachyMini
from .liaison import LiaisonReachyMini

CARTE = Path(__file__).with_name("carte.yaml")
_VRAI_KIT: list = []  # le vrai kit, créé une seule fois par programme (le relancer peut gêner certains kits : à vérifier)


def fabriquer(vrai: bool = False, lent: bool = False, acceleration: float = 1.0, **options) -> AdaptateurModele:
    """vrai=False : la doublure (testé sur faux robot). vrai=True : le VRAI robot — feu orange, après le « oui » de Hiba.
    lent=True : 0,1 m/s ; gestes demandés à mi-vitesse (tenu ou non : à vérifier par kit). Appelé SEULEMENT par
    briques/b03_adaptateurs/registre.py (le système, le test de conformité)."""
    if vrai:
        if not _VRAI_KIT:
            _VRAI_KIT.append(LiaisonReachyMini.creer_kit())
        liaison = LiaisonReachyMini(_VRAI_KIT[0])
    else:
        liaison = LiaisonReachyMini(DoublureReachyMini(acceleration=acceleration))
    liaison.lent = bool(lent)  # en mode lent, « regarder » va deux fois moins vite (les gestes : l'adaptateur les ralentit déjà)
    return AdaptateurModele(CARTE, liaison, lent=lent, **options)
