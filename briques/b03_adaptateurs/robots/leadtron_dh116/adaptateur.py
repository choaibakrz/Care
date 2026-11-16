"""Adaptateur du robot « leadtron_dh116 » (créé comme « bras » par l'assistant ; sa carte dit « autre » : une main seule, posée ou fixée sur une table ; chemin sdk). Créé par l'assistant le 15.11.2026 16:04.

NON TESTÉ SUR VRAI ROBOT. fabriquer(vrai=False) : une DOUBLURE à la place de la main (doublure.py), avec la vraie
liaison de ce dossier : testé sur faux robot.
Seule la prise appelle cet adaptateur. Il se fabrique dans commun/systeme.py (par briques/b03_adaptateurs/registre.py)
ou pour le test de conformité : python3 lancer.py brancher leadtron_dh116 --conformite
"""
from __future__ import annotations

from pathlib import Path

from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from .doublure import DoublureLeadtronDh116
from .liaison import LiaisonLeadtronDh116

CARTE = Path(__file__).with_name("carte.yaml")
# L'OBJET du vrai kit est créé une seule fois par programme. Sa CONNEXION, elle, est fermée puis rouverte à chaque fois
# qu'un adaptateur se déconnecte et qu'un autre se connecte : le test de conformité le fait 2 fois (« --vrai ») ou
# 5 fois (« --vrai --complet »). Le kit attend 0,3 s entre fermer et rouvrir (voir KitDeLaMain.relier). À vérifier sur
# la vraie main : que le boîtier USB supporte ces fermetures et ces ouvertures à la suite.
_VRAI_KIT: list = []


def fabriquer(vrai: bool = False, lent: bool = False, acceleration: float = 1.0, **options) -> AdaptateurModele:
    """vrai=False : la doublure (testé sur faux robot). vrai=True : la VRAIE main — feu orange, après le « oui » de Hiba.
    lent=True : les gestes sont demandés à mi-vitesse par l'adaptateur (la liaison ne fait jamais que ralentir).
    Appelé SEULEMENT par briques/b03_adaptateurs/registre.py (le système, le test de conformité)."""
    if vrai:
        if not _VRAI_KIT:
            _VRAI_KIT.append(LiaisonLeadtronDh116.creer_kit())
        liaison = LiaisonLeadtronDh116(_VRAI_KIT[0])
    else:
        liaison = LiaisonLeadtronDh116(DoublureLeadtronDh116(acceleration=acceleration))
    liaison.lent = bool(lent)
    return AdaptateurModele(CARTE, liaison, lent=lent, **options)
