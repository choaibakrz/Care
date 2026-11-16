"""Outils communs aux tests de la brique 3. Tout ici est testé sur faux robot."""
from __future__ import annotations

from briques.b01_prise.actions import ACTIONS, ActionDemandee
from briques.b01_prise.carte import CarteIdentite, Limites
from briques.b01_prise.prise import Prise
from briques.b03_adaptateurs.chemins.ros2.faux_ros2 import MESSAGES, FauxRclpy, FauxRobotROS2
from briques.b03_adaptateurs.chemins.ros2.liaison_ros2 import LiaisonPontROS2
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.chemins.sdk.liaison_sdk import LiaisonSDK
from briques.b03_adaptateurs.modele_vide.adaptateur import AdaptateurModele
from briques.b07_gardien.gardien import Gardien
from commun.bus import Bus

CARTE_COMPLETE = CarteIdentite(id="essai-b03", nom="Essai brique 3", genre="humanoide", capacites=list(ACTIONS),
                               vrai_robot=True)  # « true » exprès : la liaison doit le corriger
# Avec des chiffres : pour les kits d'essai dérivés du faux kit, que la liaison traite comme de VRAIS robots
# (type(kit) is not FauxKit) — sans chiffres, ils refuseraient de bouger (0 = refus). Chiffres inventés pour les tests.
CARTE_CHIFFREE = CARTE_COMPLETE.model_copy(update={
    "limites": Limites(vitesse_max_m_s=0.5, portee_max_m=0.6, charge_max_kg=1.0, force_max_n=20.0), "gestes": ["saluer"]})


class KitSansEtiquette(FauxKit):
    """POUR LES TESTS : une copie du faux kit sous un autre nom de classe. La liaison (type(kit) is FauxKit) le traite
    donc comme un VRAI robot. Sert à vérifier ce que fait l'adaptateur avec un vrai robot, sans jamais en toucher un.
    (Le système, lui, le verrait comme un faux kit — registre.sur_faux_kit — et refuserait de démarrer : voulu.)"""


def faux_sdk(carte: CarteIdentite | None = None, acceleration: float = 5.0, kit: FauxKit | None = None,
             **options) -> tuple[AdaptateurModele, FauxKit]:
    """Le faux kit (simulation) ; avec `kit=` un kit d'essai dérivé (traité comme vrai : carte chiffrée par défaut)."""
    if carte is None:
        carte = CARTE_COMPLETE if kit is None or type(kit) is FauxKit else CARTE_CHIFFREE
    kit = kit or FauxKit(acceleration=acceleration)
    return AdaptateurModele(carte, LiaisonSDK(kit), **options), kit


def faux_ros2(carte: CarteIdentite = CARTE_COMPLETE, acceleration: float = 5.0,
              **options) -> tuple[AdaptateurModele, FauxRobotROS2]:
    robot = FauxRobotROS2(acceleration=acceleration)
    return AdaptateurModele(carte, LiaisonPontROS2(FauxRclpy(robot), MESSAGES), **options), robot


FAUX = {"sdk": faux_sdk, "ros2": faux_ros2}


def chaine(adaptateur) -> tuple[Bus, Gardien, Prise]:
    """Gardien + prise autour d'un adaptateur, comme dans commun/systeme.py."""
    bus = Bus()
    gardien = Gardien(bus)
    return bus, gardien, Prise(adaptateur, gardien.verificateur, bus)


async def agir(gardien: Gardien, prise: Prise, action: str, /, **parametres):
    """Une action par le seul chemin permis : gardien (ticket) → prise → adaptateur."""
    decision, ticket = await gardien.verifier(ActionDemandee(nom=action, parametres=parametres), prise.carte())
    assert ticket is not None, decision
    return await prise.executer(ticket)
