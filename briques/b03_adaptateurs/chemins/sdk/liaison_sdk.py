"""Brique 3 — Chemin (a) : ÉBAUCHE de liaison vers le kit Python du fabricant (SDK).

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot, avec le faux kit (faux_sdk.py).

Chaque appel au kit est marqué « # À BRANCHER (à vérifier dans la doc du fabricant) ». Les noms appelés ici
(ouvrir_liaison, lire, vitesse, stop…) sont ceux du FAUX kit : pour un vrai robot, remplacer chaque ligne marquée par
l'appel du vrai kit. Les vrais noms lus dans les docs publiques sont dans les commentaires « Lu : » et dans fiches/
(adresse et date de lecture). Rien ici ne prétend marcher sur un vrai robot.

L'assistant (python3 lancer.py brancher NOM --chemin sdk) copie ce fichier dans robots/NOM/liaison.py.
"""
from __future__ import annotations

from typing import Any

from briques.b01_prise.actions import ACTIONS
from briques.b01_prise.adaptateur import ActionImpossible
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide


class LiaisonSDK(LiaisonVide):  # gabarit:classe
    chemin = "sdk"
    # Les actions vraiment branchées. Le faux kit sait tout jouer ; un vrai robot : seulement ce qui est écrit ET essayé.
    branchees = frozenset(ACTIONS)  # gabarit:branchees
    sait_aller_au_lieu = False  # à vérifier : le kit a-t-il une navigation vers un lieu nommé ? (rarement)

    def __init__(self, kit: Any) -> None:
        self.kit = kit
        # Faux ou vrai : décidé par la CLASSE du kit (le faux kit du projet), jamais par ce que le kit dit de lui-même.
        self.vrai_robot = type(kit) is not FauxKit
        # Vrai robot : le repère de l'odomètre n'est pas celui du monde tant qu'il n'est pas calé (à vérifier).
        self.repere_du_monde = not self.vrai_robot

    @staticmethod
    def creer_kit(**options: Any) -> Any:
        """Créer le client du vrai kit. Appelé seulement pour le vrai robot, après la confirmation tapée (feu orange).
        Importer le kit ICI (pas en haut du fichier) : le projet tourne sans lui. Installer un kit = feu orange.
        L'arrêt d'urgence doit avoir un DÉLAI COURT : si le kit le permet, un client à part pour les arrêts, avec un
        délai d'attente court (ex. 0,5 s au lieu des 10 s des exemples Unitree ; à vérifier)."""
        # À BRANCHER (à vérifier dans la doc du fabricant) : importer le kit et créer le client.
        # Lu (Unitree G1, github.com/unitreerobotics/unitree_sdk2_python, example/g1/high_level/g1_loco_client_example.py,
        #     11.11.2026) : ChannelFactoryInitialize(0, "<nom de la carte réseau>") ; LocoClient() ; SetTimeout(10.0) ; Init()
        # Lu (Flexiv, github.com/flexivrobotics/flexiv_rdk, tag v1.10, example_py/basics3_primitive_execution.py,
        #     11.11.2026) : flexivrdk.Robot("<numéro de série>")
        raise ABrancher("creer_kit", "importer le kit du fabricant et créer son client (voir fiches/)")

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else self.kit.infos_simulation()

    @staticmethod
    def _ok(code: Any, quoi: str, arret: bool = False) -> None:
        """Beaucoup de kits rendent un code (0 = bien) : à vérifier pour chaque kit.
        Pour un ARRÊT, pas de code (None) = arrêt NON confirmé (Unitree G1 : StopMove(), Move(), Damp() rendent None ;
        SetVelocity() rend un code — lu le 11.11.2026)."""
        if arret and code is None:
            raise ActionImpossible("arret_non_confirme", f"{quoi} : le kit ne rend aucun code, arrêt non confirmé")
        if code not in (0, None):
            raise ActionImpossible("robot_refuse", f"{quoi} : le robot répond le code {code}")

    # ---------------------------------------------------------------- la connexion
    def ouvrir(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : ouvrir la connexion, SANS faire bouger le robot.
        # Lu (Flexiv, v1.10) : robot.Enable() « make sure the E-stop is released before enabling » met les moteurs sous
        #     tension → PAS ici, feu orange, à décider.
        self._ok(self.kit.ouvrir_liaison(), "ouvrir la liaison")

    def fermer(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : fermer la connexion.
        self._ok(self.kit.fermer(), "fermer")

    def signe_de_vie(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : un appel court qui prouve que le robot répond.
        self._ok(self.kit.ping(), "signe de vie")

    def lire_etat(self) -> dict[str, Any]:
        # À BRANCHER (à vérifier dans la doc du fabricant) : lire batterie, odomètre (x, y, cap), mouvement, erreurs.
        # Lu (Unitree Go2) : dossier unitree_sdk2py/go2/robot_state existe (non lu en détail : à vérifier).
        brut = self.kit.lire()
        return {cle: brut.get(cle) for cle in ("batterie_pct", "x", "y", "cap", "en_mouvement", "occupe",
                                               "objet_tenu", "erreurs", "arret_urgence", "entendu")}

    # ---------------------------------------------------------------- s'arrêter (à brancher EN PREMIER)
    def arreter_mouvement(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : arrêt normal, vitesse nulle, le robot reste stable.
        # Lu (Unitree G1) : SetVelocity(0, 0, 0) rend un code (StopMove() rend None). Lu (Go2) : StopMove() rend un code.
        # Lu (Flexiv v1.10) : robot.Stop().
        self._ok(self.kit.stop(), "stop", arret=True)

    def arret_urgence(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : l'arrêt logiciel le plus sûr, choisi avec le responsable sécurité.
        # Lu (Unitree G1) : Damp() = mode amorti (FSM 1), ZeroTorque() = moteurs sans force (FSM 0) : le robot
        #     peut TOMBER (à vérifier). Proposition : SetVelocity(0, 0, 0). ATTENTION : cet « arrêt de marche » ne BLOQUE
        #     PAS le robot (il accepte l'ordre suivant) ; l'adaptateur bloque nos ordres, pas ceux d'un autre programme.
        self._ok(self.kit.arreter_en_urgence(), "arrêt d'urgence", arret=True)

    def rearmer(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : lever le blocage, SANS mouvement (ne pas relever le robot).
        # Lu (Flexiv v1.10) : robot.fault() / robot.ClearFault() — c'est ICI (réarmer), pas dans ouvrir().
        self._ok(self.kit.lever_arret(), "réarmer")

    # ---------------------------------------------------------------- bouger
    def vitesse(self, vx: float, vy: float, vyaw: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : un ordre de vitesse court, qui expire seul.
        # Lu (Unitree G1) : Move(vx, vy, vyaw) envoie SetVelocity(..., duration=1.0) et rend None ; mieux : SetVelocity
        #     (rend un code). JAMAIS continous_move=True (durée 864000 s). Lu (Go2) : Move(vx, vy, vyaw) rend un code,
        #     sans durée : son chien de garde est à vérifier.
        self._ok(self.kit.vitesse(vx, vy, vyaw), "vitesse")

    def geste(self, nom: str, vitesse_relative: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : rejouer un geste enregistré, par son nom.
        # Lu (Unitree G1) : G1ArmActionClient().ExecuteAction(action_map.get("high wave")) — SANS réglage de vitesse :
        #     vitesse du geste à vérifier par kit. Lu (Go2) : Hello(), Stretch()…
        self._ok(self.kit.jouer_geste(nom, vitesse_relative), f"geste {nom}")

    def regarder(self, cible: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : tourner la tête ou la caméra.
        self._ok(self.kit.tourner_tete(cible), "regarder")

    def montrer(self, cible: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : montrer du bras ou du corps.
        self._ok(self.kit.pointer(cible), "montrer")

    def saisir(self, objet: str, force_n: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : fermer la pince ou la main (force déjà bridée).
        # Lu (Flexiv) : example_py/basics6_gripper_control.py existe (non lu en détail : à vérifier).
        self._ok(self.kit.prendre(objet, force_n), "saisir")

    def poser(self, lieu: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : ouvrir la pince ou la main.
        self._ok(self.kit.lacher(lieu), "poser")

    # ---------------------------------------------------------------- parler, écouter
    def parler(self, texte: str, langue: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : haut-parleur du robot (sinon : la voix du Mac, brique 4).
        # Lu (Unitree G1) : un dossier example/g1/audio existe (non lu : à vérifier).
        self._ok(self.kit.dire(texte, langue), "parler")

    def ecouter(self, duree_s: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : micros du robot (sinon : le micro du Mac, brique 4).
        self._ok(self.kit.ecouter(duree_s), "écouter")
