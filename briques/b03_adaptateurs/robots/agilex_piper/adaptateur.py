"""Adaptateur du robot « agilex_piper » (bras, chemin sdk). Créé par l'assistant le 14.11.2026 20:48.

NON TESTÉ SUR VRAI ROBOT. fabriquer(vrai=False) : faux kit, testé sur faux robot.
Seule la prise appelle cet adaptateur. Il se fabrique dans commun/systeme.py (par briques/b03_adaptateurs/registre.py)
ou pour le test de conformité : python3 lancer.py brancher agilex_piper --conformite
"""
from __future__ import annotations

from pathlib import Path

from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK
from .liaison import LiaisonAgilexPiper

CARTE = Path(__file__).with_name("carte.yaml")
_VRAI_KIT: list = []  # le vrai kit, créé une seule fois par programme (le relancer peut gêner certains kits : à vérifier)


def fabriquer(vrai: bool = False, lent: bool = False, acceleration: float = 1.0, **options) -> AdaptateurModele:
    """vrai=False : le faux kit (testé sur faux robot). vrai=True : le VRAI robot — feu orange, après le « oui » de Hiba.
    lent=True : 0,1 m/s ; gestes demandés à mi-vitesse (tenu ou non : à vérifier par kit). Appelé SEULEMENT par
    briques/b03_adaptateurs/registre.py (le système, le test de conformité)."""
    if vrai:
        if not _VRAI_KIT:
            _VRAI_KIT.append(LiaisonAgilexPiper.creer_kit())
        liaison = LiaisonAgilexPiper(_VRAI_KIT[0])
    else:
        liaison = LiaisonSDK(FauxKit(acceleration=acceleration))
    return AdaptateurModele(CARTE, liaison, lent=lent, **options)
