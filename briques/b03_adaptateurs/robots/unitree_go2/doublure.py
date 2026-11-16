"""Une DOUBLURE à la place du robot Unitree Go2 : un faux client, pour essayer l'ébauche sans robot et sans kit.

PRÉPARÉE SANS LE ROBOT — non testé sur vrai robot. Testé sur faux robot (c'est elle, le faux robot).

C'est le FAUX KIT du projet (briques/b03_adaptateurs/chemins/sdk/faux_sdk.py), habillé avec les NOMS de fonctions du
client public d'Unitree (`SportClient`, lu en ligne le 12.11.2026 : github.com/unitreerobotics/unitree_sdk2_python,
unitree_sdk2py/go2/sport/sport_client.py) : StandUp(), Move(vx, vy, vyaw), StopMove(), SetTimeout(), Init().
Chacune rend un code, 0 = bien (comme lu dans ce fichier).
Tout le reste vient du faux kit, est INVENTÉ, et ne dit rien du vrai chien :
- elle oublie un ordre de vitesse après 0,3 s s'il n'est pas répété (le vrai Go2 : à vérifier samedi) ;
- elle met 0,6 s à se lever (le vrai Go2 : à vérifier samedi) ;
- sa position avance tout droit, sans glisser ; son état arrive toujours ; son arrêt ne bloque rien (comme StopMove()).
Le registre et la liaison reconnaissent la doublure à sa CLASSE (un faux kit du projet), jamais à ce qu'elle dit.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from briques.b03_adaptateurs.chemins.sdk.faux_sdk import OK, FauxKit

LEVER_S = 0.6  # inventé pour la doublure


class DoublureUnitree(FauxKit):
    def __init__(self, acceleration: float = 1.0) -> None:
        super().__init__(acceleration=acceleration, arret_bloquant=False)
        self.appels_du_kit: list[tuple[str, tuple]] = []  # pour les essais : les fonctions « Unitree » appelées, dans l'ordre
        self.debout = False
        self.muet = False  # pour les essais : le robot ne donne plus son état
        self.code_suivant = OK  # pour les essais : le code rendu au prochain ordre de mouvement
        self.code_de_l_arret: Any = OK  # pour les essais : None = un arrêt sans code
        self.sport = self.arret = self  # le client de marche et le client des arrêts : ici, le même faux client

    def _refus(self) -> int:
        code, self.code_suivant = self.code_suivant, OK
        return code

    # ------------------------------------------------------------ les noms du kit public (lus le 12.11.2026)
    def SetTimeout(self, secondes: float) -> None:  # noqa: N802 — nom du fabricant
        return None

    def Init(self) -> None:  # noqa: N802
        return None

    def StandUp(self) -> int:  # noqa: N802
        self.appels_du_kit.append(("StandUp", ()))
        code = self._refus()
        if code != OK:
            return code
        self._trajet()
        with self._verrou:
            self._arrivee("StandUp")
            code = self._lancer("geste", LEVER_S)
            self.debout = self.debout or code == OK
            return code

    def Move(self, vx: float, vy: float, vyaw: float) -> int:  # noqa: N802
        self.appels_du_kit.append(("Move", (float(vx), float(vy), float(vyaw))))
        code = self._refus()
        return code if code != OK else self.vitesse(vx, vy, vyaw)

    def StopMove(self) -> Any:  # noqa: N802
        self.appels_du_kit.append(("StopMove", ()))
        self.stop()
        return self.code_de_l_arret

    # ------------------------------------------------------------ l'état (forme du message SportModeState_, lu le 12.11.2026)
    def dernier_etat(self) -> tuple[Any, float]:
        """Le dernier message d'état reçu, et son âge en secondes."""
        if self.muet:
            return None, float("inf")
        brut = self.lire()
        vx, vy, vyaw = self._v
        return SimpleNamespace(error_code=0, mode=0, progress=0.0, position=[brut["x"], brut["y"], 0.0],
                               velocity=[vx, vy, 0.0], yaw_speed=vyaw), 0.0

    def occupe(self) -> bool:
        return bool(self.lire()["occupe"])
