"""ÉBAUCHE de liaison vers un bras AgileX PiPER, par le kit Python public du fabricant (piper_sdk).

NON TESTÉ SUR VRAI ROBOT. Essayée seulement avec une doublure (doublure.py).
Le bras est sur la table de l'équipe (photos de Hiba, 14.11.2026) ; rien ne lui a été envoyé. Le kit du fabricant
n'est PAS installé sur nos ordinateurs (l'installer est un feu orange : taille, licence MIT, « oui » de Hiba).

Ce que cette ébauche sait faire, et rien d'autre (demande de Hiba, 14.11.2026) :
    se connecter   → C_PiperInterface_V2(can_name) puis ConnectPort(piper_init=False)   (écoute seule : rien n'est écrit)
    dire son état  → GetArmStatus() et GetArmHighSpdInfoMsgs()                          (lecture seule)
    se déconnecter → DisconnectPort()
Les TROIS ARRÊTS (arrêt normal, arrêt d'urgence, réarmement) et tous les mouvements restent « À BRANCHER » :
l'arrêt « rapide » du kit fait DESCENDRE le bras et la remise à zéro le fait TOMBER (lu, voir plus bas). Le choix se
fait avec le responsable sécurité, pas ici. Tant qu'ils ne sont pas choisis, `branchees` reste vide.

LU EN LIGNE, le 14.11.2026 (documentation publique, rien installé ; dépôt github.com/agilexrobotics/piper_sdk,
branche master ; licence MIT). Les commentaires du fabricant sont souvent en chinois : les traductions sont les nôtres.
- README : « Use `C_PiperInterface_V3` for firmware version `1.8-8` and later ». La classe V2 est donc un CHOIX
  PROVISOIRE : lire la version du logiciel du bras AVANT de choisir V2 ou V3 (la doc de V3 n'a pas été lue).
- README : « the first frame of all messages is the default value » ; en mode « bras maître », « the robot will not
  respond ». Avant le premier message, GetArmStatus() rend time_stamp = 0, Hz = 0 et des codes à 0 (= « normal ») :
  un état jamais reçu ressemble à « tout va bien ». D'où _etat_recu() plus bas.
- piper_sdk/interface/piper_interface_v2.py :
  ConnectPort(can_init=False, piper_init=True, start_thread=True) lance un fil (un petit programme à côté) qui lit le
  câble de données (CAN). Avec piper_init=True, il écrit aussi 13 messages de QUESTION au bras (vitesses max,
  accélérations max, version) ; avec piper_init=False, il n'écrit RIEN : c'est le choix de cette ébauche ;
  « can_init(bool): can port init flag, Behind you using DisconnectPort(), you should set it True. » ;
  get_connect_status() rend un drapeau du programme, mis à vrai même si l'ouverture du câble a échoué ;
  isOk() est vrai dès le départ, et ne devient faux qu'après plusieurs mesures sans AUCUN message sur le câble
  (pas seulement les messages d'état) ; DisconnectPort() n'arrête pas cette surveillance ;
  GetArmStatus() rend un objet avec time_stamp, Hz et .arm_status, qui porte ctrl_mode, arm_status, motion_status
  et err_status (pannes par articulation) ;
  GetArmHighSpdInfoMsgs() rend time_stamp, Hz et motor_1 … motor_6, chacun avec motor_speed (en 0,001 rad/s).
- piper_sdk/demo/V2/README.MD : piper_ctrl_stop.py = « Stop the robotic arm and allow it to descend slowly. After use,
  reset and re-enable twice before resuming normal control. »
- piper_interface_v2.py, ResetPiper() : « The robot will immediately lose power and fall down ». Le même ordre
  s'écrit aussi EmergencyStop(0x02), que le kit appelle « Resume » : piège pour qui écrira rearmer().

À VÉRIFIER (pas lu, ou pas essayé) — la liste complète est dans fiches/agilex_piper.md :
- V2 ou V3 selon la version du logiciel du bras ; en écoute seule, le kit ne demande JAMAIS cette version : elle se
  lit sur la plaque du bras ou dans l'application du fabricant, ou par une question écrite au bras (feu orange) ;
- si la version du kit installée a bien toutes ces fonctions ;
- si le bras envoie son état sans qu'on lui demande rien (écoute seule), en combien de temps Hz devient > 0, et à
  quel rythme arrivent les messages d'état (un rythme trop lent pourrait faire retomber Hz à 0) ;
- si Hz retombe bien à 0 quand les messages cessent (la classe qui le calcule n'a pas été lue) ;
- le Hz des vitesses est une moyenne des six moteurs : un seul moteur muet garderait sa vieille vitesse ;
  la pince ou la main ne sont pas regardées pour dire « en mouvement » ;
- isOk() peut rester faux un court instant juste après une reconnexion (faux « ne répond plus » possible) ;
- si int() marche sur les valeurs rendues (la classe IntEnumBase du kit n'a pas été lue) ;
- le seuil de vitesse BOUGE_RAD_S (choix de l'équipe) ; le bruit des capteurs quand le bras est immobile ;
- si une reconnexion rapide après DisconnectPort() relance bien la lecture ; si le kit accepte deux appels en même temps ;
- le nom du câble de données (« can0 » est celui des exemples) ; si tout cela marche depuis une machine virtuelle Ubuntu.
"""
from __future__ import annotations

import time
from typing import Any

from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit
from briques.b03_adaptateurs.modele_vide.liaison import ABrancher, LiaisonVide

CAN_PAR_DEFAUT = "can0"  # lu : le nom utilisé dans tous les exemples du fabricant. Le vrai nom : à vérifier sur l'ordinateur.
ATTENTE_OUVERTURE_S = 1.2  # choix de l'équipe : ouvrir() attend au plus 1,2 s le premier état (la prise en laisse 2)
BOUGE_RAD_S = 0.02  # choix de l'équipe, à vérifier sur le bras : au-dessus, un moteur est dit en mouvement
MODES_CALMES = (0x00, 0x01)  # lu : ctrl_mode 0x00 = attente, 0x01 = commandé par CAN. Tout autre mode : dans le doute, il bouge.
ARRIVE = 0x00  # lu : motion_status 0x00 = arrivé au point demandé ; 0x01 = pas arrivé ; 0xFF = inconnu
ARRET_URGENCE = 0x01  # lu : arm_status 0x01 = arrêt d'urgence
APPRENTISSAGE = {0x0B: "enregistre un trajet guidé à la main", 0x0C: "rejoue un trajet appris",
                 0x0D: "trajet appris en pause"}  # lu : des états, pas des pannes
# Lu dans GetArmStatus() (traductions : les nôtres). 0x00 = normal. Tout autre code absent d'ici est dit « inconnu ».
CODES = {
    0x01: "arrêt d'urgence",
    0x02: "pas de solution pour ce mouvement",
    0x03: "point singulier (une position où le bras ne sait plus comment bouger)",
    0x04: "angle demandé hors limite",
    0x05: "communication d'une articulation anormale",
    0x06: "frein d'une articulation non ouvert",
    0x07: "collision",
    0x08: "survitesse pendant l'apprentissage à la main",
    0x09: "état d'une articulation anormal",
    0x0A: "autre anomalie",
    0x0E: "surchauffe du contrôleur",
    0x0F: "surchauffe de la résistance de décharge",
}
CONSEIL_ARRETS = "choix avec le responsable sécurité (voir fiches/agilex_piper.md)"


class LiaisonAgilexPiper(LiaisonVide):
    chemin = "sdk"
    # Les actions vraiment branchées : AUCUNE pour l'instant. « etat » est écrit, mais « arreter » ne l'est pas, et les
    # deux vont ensemble (obligatoires). À BRANCHER : frozenset({"arreter", "etat"}) quand les trois arrêts sont choisis.
    branchees: frozenset[str] = frozenset()
    sait_aller_au_lieu = False  # un bras fixé à une table ne va nulle part
    # Pas pour ce robot (rien à écrire, le modèle vide répond « À BRANCHER ») : vitesse (un bras fixé ne se déplace pas),
    # regarder (ni tête ni caméra à lui), parler et ecouter (ni haut-parleur ni micro : la voix reste au Mac, brique 4).

    def __init__(self, kit: Any) -> None:
        self.kit = kit
        # Faux ou vrai : décidé par la CLASSE du kit (un faux kit du projet, comme la doublure), jamais par ce que le kit dit.
        self.vrai_robot = not isinstance(kit, FauxKit)
        self.repere_du_monde = False  # un bras n'a pas d'odomètre : aucune position n'est donnée au gardien

    @staticmethod
    def creer_kit(can_name: str = CAN_PAR_DEFAUT, **options: Any) -> Any:
        """Créer le client du VRAI kit. Appelé seulement pour le vrai bras, après la confirmation tapée par un humain
        (feu orange). Le kit s'importe ICI : le projet tourne sans lui. Rien ne bouge et rien n'est écrit sur le câble :
        écoute seule (piper_init=False), aucun moteur mis sous tension, aucun ordre."""
        try:
            from piper_sdk import C_PiperInterface_V2  # lu le 14.11.2026. V2 : choix provisoire (V3 dès la version 1.8-8)
        except ImportError as erreur:
            raise RuntimeError("le kit du fabricant (piper_sdk) n'est pas installé sur cet ordinateur : l'installer est "
                               "un feu orange (taille, licence MIT, « oui » de Hiba)") from erreur
        try:
            kit = C_PiperInterface_V2(can_name=can_name)  # lu : la forme des exemples ; ouvre le câble de données
        except Exception as erreur:  # le kit répond en anglais : on le redit simplement
            raise ConnectionError(f"le câble de données « {can_name} » ne s'ouvre pas (boîtier USB → CAN branché et "
                                  f"activé ?) : {erreur}") from erreur
        kit.ConnectPort(piper_init=False)  # lu : lance la lecture du câble ; piper_init=False = aucune question écrite
        return kit

    def infos_simulation(self) -> dict | None:
        return None if self.vrai_robot else {"limites": {}, "gestes": []}

    def _etat_recu(self) -> Any:
        """Le dernier état du bras, seulement s'il a VRAIMENT été reçu et s'il arrive encore. N'écrit rien sur le câble.
        Lu : avant le premier message, le kit rend des valeurs par défaut (time_stamp 0, Hz 0, codes à 0 = « normal »)."""
        if not self.kit.get_connect_status():  # lu : un drapeau du programme (vrai même si le câble ne s'est pas ouvert)
            raise ConnectionError("la liaison avec le bras n'est pas ouverte")
        message = self.kit.GetArmStatus()
        if not message.time_stamp or not message.Hz > 0:
            raise TimeoutError("le bras ne donne pas son état (éteint, débranché, en mode « bras maître », ou pas encore reçu)")
        return message

    # ---------------------------------------------------------------- la connexion (rien ne bouge, rien n'est écrit)
    def ouvrir(self) -> None:
        if not self.kit.get_connect_status():
            # Lu : après DisconnectPort(), il faut ConnectPort(can_init=True). piper_init=False : écoute seule.
            self.kit.ConnectPort(can_init=True, piper_init=False)
        # isOk() est vrai dès le départ (lu) : il ne prouve rien à l'ouverture. On attend un VRAI état du bras.
        fin = time.monotonic() + ATTENTE_OUVERTURE_S
        while True:
            try:
                self._etat_recu()
                return
            except TimeoutError:
                if time.monotonic() >= fin:
                    raise
                time.sleep(0.05)

    def fermer(self) -> None:
        self.kit.DisconnectPort()  # lu : « Disconnect the port without blocking the main thread »

    def signe_de_vie(self) -> None:
        self._etat_recu()
        if not self.kit.isOk():  # lu : faux après plusieurs mesures sans aucun message sur le câble
            raise TimeoutError("le bras ne répond plus (aucun message sur le câble de données)")

    def _bouge(self, etat: Any, code: int) -> bool:
        """Dans le doute, le bras est dit EN MOUVEMENT (le sens sûr). Seuil et logique : à vérifier sur le bras."""
        if int(etat.ctrl_mode) not in MODES_CALMES or int(etat.motion_status) != ARRIVE:
            return True
        if code == ARRET_URGENCE or code in APPRENTISSAGE or (code and code not in CODES):
            return True  # arrêt d'urgence (l'ordre d'arrêt « rapide » fait descendre le bras), trajet guidé ou rejoué, code inconnu
        vitesses = self.kit.GetArmHighSpdInfoMsgs()  # lu : motor_1 … motor_6, motor_speed en 0,001 rad/s
        if not vitesses.time_stamp or not vitesses.Hz > 0:
            return True  # aucune mesure de vitesse reçue : on ne peut pas dire « immobile »
        v = vitesses  # les six moteurs, par leur nom (la règle du projet : jamais un nom calculé)
        moteurs = (v.motor_1, v.motor_2, v.motor_3, v.motor_4, v.motor_5, v.motor_6)
        return any(abs(int(moteur.motor_speed)) / 1000 > BOUGE_RAD_S for moteur in moteurs)

    def lire_etat(self) -> dict[str, Any]:
        etat = self._etat_recu().arm_status  # lu : ctrl_mode, arm_status, motion_status, err_status
        code = int(etat.arm_status)  # à vérifier : int() sur les valeurs du kit
        erreurs = []
        if code in CODES:
            erreurs.append(f"le bras dit : {CODES[code]} (code {code})")
        elif code and code not in APPRENTISSAGE:
            erreurs.append(f"le bras dit un code inconnu : {code} (à vérifier dans la doc du fabricant)")
        p = etat.err_status  # lu : une panne possible par articulation (par leur nom : jamais un nom calculé)
        hors_limite = (p.joint_1_angle_limit, p.joint_2_angle_limit, p.joint_3_angle_limit,
                       p.joint_4_angle_limit, p.joint_5_angle_limit, p.joint_6_angle_limit)
        communication = (p.communication_status_joint_1, p.communication_status_joint_2, p.communication_status_joint_3,
                         p.communication_status_joint_4, p.communication_status_joint_5, p.communication_status_joint_6)
        for n, (limite, muette) in enumerate(zip(hors_limite, communication), 1):
            if limite:
                erreurs.append(f"articulation {n} : angle hors limite")
            if muette:
                erreurs.append(f"articulation {n} : communication anormale")
        bouge = self._bouge(etat, code)
        return {"batterie_pct": None,  # à vérifier : le kit donne une tension (en 0,1 V), pas un pourcentage
                "x": None, "y": None, "cap": None,  # un bras fixé n'a pas de position dans la salle
                "en_mouvement": bouge, "occupe": bouge,
                "objet_tenu": None,  # à vérifier : la pince dit sa course, pas ce qu'elle tient
                "erreurs": erreurs, "arret_urgence": code == ARRET_URGENCE, "entendu": None}

    # ---------------------------------------------------------------- s'arrêter (À BRANCHER EN PREMIER, avec le responsable sécurité)
    def arreter_mouvement(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : un arrêt où le bras RESTE EN PLACE. Rien de clair n'a été lu.
        # Lu : MotionCtrl_1(0, 0x01, 0) = « Pause current plan » (mettre en pause le trajet prévu) — vaut-il pour
        # un mouvement lancé par JointCtrl ? à vérifier.
        raise ABrancher("arreter_mouvement", "un arrêt où le bras reste en place ; " + CONSEIL_ARRETS)

    def arret_urgence(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : l'arrêt logiciel le plus sûr.
        # Lu : EmergencyStop(0x01) = arrêt « rapide » : le bras DESCEND lentement, puis il faut une remise à zéro.
        # Ce n'est pas un arrêt sans mouvement : où descend le bras, et avec quoi dans la main ? Choix humain.
        raise ABrancher("arret_urgence", "le bras descend lentement avec l'arrêt « rapide » du kit ; " + CONSEIL_ARRETS)

    def rearmer(self) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : lever le blocage SANS mouvement.
        # Lu : après l'arrêt « rapide », « reset and re-enable twice ». Or ResetPiper() — le même ordre que
        # EmergencyStop(0x02), « Resume » — fait TOMBER le bras : il ne peut pas être appelé ici.
        # Proposition : la remise à zéro est une étape humaine à part (bras tenu à la main).
        raise ABrancher("rearmer", "la remise à zéro du kit fait tomber le bras : étape humaine à décider ; " + CONSEIL_ARRETS)

    # ---------------------------------------------------------------- bouger (rien n'est branché)
    def geste(self, nom: str, vitesse_relative: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : rejouer un trajet appris à la main (lu : MotionCtrl_1, 3e valeur).
        raise ABrancher("geste", "rejouer un trajet appris à la main (non essayé, vitesse inconnue)")

    def montrer(self, cible: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : aller à une pose enregistrée, à petite vitesse.
        # Lu : MotionCtrl_2(0x01, 0x01, <vitesse en %>, 0x00) puis JointCtrl(j1…j6), après EnablePiper().
        raise ABrancher("montrer", "aller lentement à une pose enregistrée (poses à enregistrer avec le bras)")

    def saisir(self, objet: str, force_n: float) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : fermer la pince du bras (lu : GripperCtrl, couple de 0 à
        # 5 N·m — un couple, pas une force), ou la main posée à côté du bras (un autre kit, un autre câble : voir la fiche).
        raise ABrancher("saisir", "fermer la pince ou la main (laquelle ? force à convertir : à vérifier)")

    def poser(self, lieu: str) -> None:
        # À BRANCHER (à vérifier dans la doc du fabricant) : ouvrir la pince (lu : GripperCtrl) ou la main.
        raise ABrancher("poser", "ouvrir la pince ou la main")
