"""Une DOUBLURE à la place du bras AgileX PiPER : un faux client, pour essayer l'ébauche sans bras et sans kit.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot (c'est elle, le faux robot).

C'est le FAUX KIT du projet (briques/b03_adaptateurs/chemins/sdk/faux_sdk.py), habillé avec les NOMS de fonctions du
client public d'AgileX (`C_PiperInterface_V2`, lu en ligne le 14.11.2026 : github.com/agilexrobotics/piper_sdk,
piper_sdk/interface/piper_interface_v2.py) : ConnectPort(), DisconnectPort(), get_connect_status(), isOk(),
GetArmStatus(), GetArmHighSpdInfoMsgs().
Comme le vrai kit (lu) : tant qu'aucun message n'est arrivé, l'état rendu est celui « par défaut » (time_stamp 0,
Hz 0, codes à 0), et isOk() est vrai dès le départ.
Elle porte aussi des noms d'ORDRES du kit (mise sous tension, mouvement, pince, arrêt « rapide », remise à zéro,
réglages) : ils ne font rien d'autre que se noter. La liste n'est pas complète : les essais vérifient donc, en plus,
que la liaison n'appelle QUE les lectures permises.
Tout le reste est INVENTÉ et ne dit rien du vrai bras : son état ne change que quand un essai le change.
La liaison reconnaît la doublure à sa CLASSE (un faux kit du projet), jamais à ce qu'elle dit.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit

# Des ordres du kit, lus le 14.11.2026 : ce qui met sous tension, fait bouger, arrête, remet à zéro ou règle le bras.
ORDRES = ("EnablePiper", "EnableArm", "DisablePiper", "DisableArm", "MotionCtrl_1", "MotionCtrl_2", "ModeCtrl",
          "JointCtrl", "JointMitCtrl", "EndPoseCtrl", "GripperCtrl", "EmergencyStop", "ResetPiper",
          "CrashProtectionConfig", "MasterSlaveConfig", "JointConfig", "MotorMaxSpdSet", "JointMaxAccConfig",
          "ArmParamEnquiryAndConfig", "EndSpdAndAccParamSet", "PiperInit")


# Lu : les douze pannes possibles par articulation, toutes à « faux » quand tout va bien.
SANS_PANNE = {nom: False for n in range(1, 7) for nom in (f"joint_{n}_angle_limit", f"communication_status_joint_{n}")}


class DoublurePiper(FauxKit):
    def __init__(self, acceleration: float = 1.0) -> None:
        super().__init__(acceleration=acceleration)
        self.appels_du_kit: list[tuple[str, tuple]] = []  # pour les essais : les fonctions « AgileX » appelées, dans l'ordre
        self.branche = False  # la lecture du câble de données est-elle lancée ?
        self.allume = True  # pour les essais : le bras envoie-t-il ses messages ? (éteint, débranché, bras maître : non)
        self.sain = True  # pour les essais : ce que rend isOk()
        self.mode, self.code, self.mouvement = 0x00, 0x00, 0x00  # pour les essais : ctrl_mode, arm_status, motion_status
        self.pannes_articulations: dict[str, bool] = {}  # pour les essais : ex. {"joint_3_angle_limit": True}
        self.vitesses_moteurs = [0, 0, 0, 0, 0, 0]  # pour les essais : en 0,001 rad/s (l'unité du kit)
        self.vitesses_recues = True  # pour les essais : les mesures de vitesse arrivent-elles ?
        # Pour les essais : le bras a parlé puis s'est tu. Comme dans le vrai kit (lu) : time_stamp reste non nul, Hz retombe à 0.
        self.etat_vieux = False
        self.vitesses_vieilles = False

    def _noter(self, nom: str, *valeurs: Any) -> None:
        self.appels_du_kit.append((nom, valeurs))

    def _recu(self, oui: bool, vieux: bool = False) -> dict:
        """Comme le vrai kit : rien reçu = time_stamp 0 et Hz 0 ; reçu = une heure et un rythme (valeurs inventées) ;
        reçu puis plus rien (« vieux ») = l'heure reste, le rythme retombe à 0."""
        if not oui:
            return {"time_stamp": 0, "Hz": 0}
        return {"time_stamp": 1731600000.0, "Hz": 0 if vieux else 200.0}

    # ------------------------------------------------------------ les noms du kit public (lus le 14.11.2026) : lecture
    def ConnectPort(self, can_init: bool = False, piper_init: bool = True, start_thread: bool = True) -> None:  # noqa: N802 — nom du fabricant
        self._noter("ConnectPort", can_init, piper_init)
        self.branche = True
        if piper_init:
            self._noter("PiperInit")  # lu : avec piper_init=True, le kit ÉCRIT 13 messages de question au bras

    def DisconnectPort(self, thread_timeout: float = 0.1) -> None:  # noqa: N802
        self._noter("DisconnectPort")
        self.branche = False

    def get_connect_status(self) -> bool:
        return self.branche

    def isOk(self) -> bool:  # noqa: N802
        return self.sain

    def GetArmStatus(self) -> Any:  # noqa: N802
        self._noter("GetArmStatus")
        recu = self.branche and self.allume
        etat = SimpleNamespace(ctrl_mode=self.mode if recu else 0, arm_status=self.code if recu else 0,
                               motion_status=self.mouvement if recu else 0,
                               err_status=SimpleNamespace(**{**SANS_PANNE, **(self.pannes_articulations if recu else {})}))
        return SimpleNamespace(arm_status=etat, **self._recu(recu, self.etat_vieux))

    def GetArmHighSpdInfoMsgs(self) -> Any:  # noqa: N802
        self._noter("GetArmHighSpdInfoMsgs")
        recu = self.branche and self.allume and self.vitesses_recues
        moteurs = {f"motor_{n}": SimpleNamespace(motor_speed=v if recu else 0)
                   for n, v in enumerate(self.vitesses_moteurs, 1)}
        return SimpleNamespace(**moteurs, **self._recu(recu, self.vitesses_vieilles))

    # ------------------------------------------------------------ des ORDRES du kit : ici, ils se notent et c'est tout
    def __getattr__(self, nom: str) -> Any:
        if nom in ORDRES:
            return lambda *valeurs, **options: self._noter(nom, *valeurs)
        raise AttributeError(nom)
