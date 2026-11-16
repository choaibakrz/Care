"""Adaptateur du robot « roues_deux_bras » (roues, chemin sdk). Créé par l'assistant le 12.11.2026 19:13.

NON TESTÉ SUR VRAI ROBOT. fabriquer(vrai=False) : faux kit, testé sur faux robot.
Seule la prise appelle cet adaptateur. Il se fabrique dans commun/systeme.py (par briques/b03_adaptateurs/registre.py)
ou pour le test de conformité : python3 lancer.py brancher roues_deux_bras --conformite
"""
from __future__ import annotations

from pathlib import Path

from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK
from .liaison import LiaisonRouesDeuxBras

CARTE = Path(__file__).with_name("carte.yaml")
_VRAI_KIT: list = []  # le vrai kit, créé une seule fois par programme (le relancer peut gêner certains kits : à vérifier)


def fabriquer(vrai: bool = False, lent: bool = False, acceleration: float = 1.0, **options) -> AdaptateurModele:
    """vrai=False : le faux kit (testé sur faux robot). vrai=True : le VRAI robot — feu orange, après le « oui » de Hiba.
    lent=True : 0,1 m/s ; gestes demandés à mi-vitesse (tenu ou non : à vérifier par kit). Appelé SEULEMENT par
    briques/b03_adaptateurs/registre.py (le système, le test de conformité)."""
    if vrai:
        if not _VRAI_KIT:
            _VRAI_KIT.append(LiaisonRouesDeuxBras.creer_kit())
        liaison = LiaisonRouesDeuxBras(_VRAI_KIT[0])
    else:
        liaison = LiaisonSDK(FauxKit(acceleration=acceleration))
    return AdaptateurModele(CARTE, liaison, lent=lent, **options)
