"""Une DOUBLURE à la place de la main Leadtron DH116 : une fausse main, pour essayer l'ébauche sans la main et sans son kit.

NON TESTÉ SUR VRAI ROBOT. Testé sur faux robot (c'est elle, le faux robot).

C'est le FAUX KIT du projet (briques/b03_adaptateurs/chemins/sdk/faux_sdk.py), habillé avec exactement les mêmes
méthodes que `KitDeLaMain` (liaison.py) : relier, nombre_de_moteurs, positions, etats, alarmes, moteurs_allumes,
cibles_atteintes, couples_atteints, allumer_les_moteurs, couper_les_moteurs, mise_en_position_de_depart,
donner_une_cible, regler_vitesse_et_courant, envoyer_les_reglages, lancer_le_mouvement, arreter_les_moteurs, fermer.
Un essai vérifie que les deux listes sont les mêmes.
Elle imite ce qui a été LU dans le kit du fabricant le 15.11.2026 :
- six moteurs ; positions de 0 (ouvert) à 10000 ; une vitesse en positions par seconde ; un courant en pour mille ;
- sans mise en position de départ, elle refuse de bouger (lu : l'erreur « LER_NOT_HOME ») ;
- avant tout réglage, sa vitesse est 20000 et son courant 1000 : ce sont les valeurs des EXEMPLES du fabricant
  (main.py), prises ici faute de mieux. Les valeurs d'origine de la VRAIE main ne sont pas connues (rien lu) ;
- les états (0 arrêté, 1 en marche, 2 alarme, 7 mise en position de départ) et les alarmes sont des nombres ;
- la vitesse et le courant qu'on règle ne vont DANS LA MAIN qu'au mouvement suivant, ou tout de suite avec
  « envoyer_les_reglages » (lu : manuel, lignes 1317 à 1353) ; la mise en position de départ les remet d'origine dans
  la main, et le mouvement suivant les renvoie (lu : manuel, ligne 2160).
Elle imite aussi, SUR DEMANDE (options « pour les essais »), ce qui a été VU sur la vraie main le 15.11.2026 et
l'hypothèse qu'on en a tirée (pas prouvée) : avec trop peu de courant dans la main, la mise en position de départ ne
finit pas, et la main reste dite « en mise en position de départ » même après un arrêt.
Tout le reste est INVENTÉ et ne dit rien de la vraie main : elle répond tout de suite ; ses doigts avancent en ligne
droite à la vitesse réglée ; sa mise en position de départ dure 1,5 s et ramène les doigts à 0 ; moteurs coupés, plus
rien ne bouge et les doigts restent où ils sont (la vraie main lâche-t-elle l'objet ? ON NE LE SAIT PAS) ; un arrêt
fige les doigts sur place ; un doigt qui touche l'objet s'arrête là et dit « couple atteint ».
ATTENTION : cette fausse main va toujours à la VRAIE vitesse, même quand on demande au faux kit d'aller plus vite
(« acceleration »). La liaison MESURE la vitesse des doigts et dit « raté » s'ils vont trop vite : une fausse main
accélérée ferait rater tous les gestes. Seule la mise en position de départ est raccourcie.
La liaison reconnaît la doublure à sa CLASSE (un faux kit du projet), jamais à ce qu'elle dit.
"""
from __future__ import annotations

import time
from typing import Any

from briques.b01_prise.adaptateur import ActionImpossible
from briques.b03_adaptateurs.chemins.sdk.faux_sdk import FauxKit

MOTEURS = 6
ARRETE, EN_MARCHE, EN_ALARME, EN_DEPART = 0, 1, 2, 7  # lu : LST_STOPPED, LST_RUNNING, LST_ALARM, LST_HOMING
VITESSE_D_ORIGINE, COURANT_D_ORIGINE = 20000, 1000  # les valeurs des EXEMPLES du fabricant ; celles de la vraie main : inconnues
# Les ORDRES (tout le reste est une lecture, ou la connexion). Sert aux essais : « rien n'est parti ».
ORDRES = ("allumer_les_moteurs", "couper_les_moteurs", "mise_en_position_de_depart", "donner_une_cible",
          "regler_vitesse_et_courant", "envoyer_les_reglages", "lancer_le_mouvement", "arreter_les_moteurs")


class DoublureLeadtronDh116(FauxKit):
    def __init__(self, acceleration: float = 1.0) -> None:
        super().__init__(acceleration=acceleration)
        self.appels_du_kit: list[tuple[str, tuple]] = []  # pour les essais : (méthode, valeurs), dans l'ordre d'arrivée
        self.reliee = False
        self.moteurs = MOTEURS  # pour les essais : une main qui dit un autre nombre de moteurs
        self.position = [0.0] * MOTEURS
        self.cible = [0] * MOTEURS
        self.vitesse_reglee = [VITESSE_D_ORIGINE] * MOTEURS  # ce qu'on a réglé (côté kit), pas encore dans la main
        self.courant_regle = [COURANT_D_ORIGINE] * MOTEURS
        self.vitesse_dans_la_main = [VITESSE_D_ORIGINE] * MOTEURS  # ce que la main a VRAIMENT reçu
        self.courant_dans_la_main = [COURANT_D_ORIGINE] * MOTEURS
        # Pour les essais (HYPOTHÈSE du 15.11.2026, pas prouvée) : si le plus petit courant DANS LA MAIN est sous cette
        # valeur, la mise en position de départ ne finit jamais (les doigts ne bougent pas, la main se dit « en cours »).
        self.courant_min_pour_le_depart = 0
        # Pour les essais (vu sur la vraie main, semble-t-il) : après une mise en position de départ bloquée, la main
        # se dit encore « en mise en position de départ », même après un arrêt, jusqu'à la prochaine qui réussit à partir.
        self.depart_colle = False
        self.refuser_les_reglages = False  # pour les essais : la main refuse « régler » et « envoyer les réglages »
        self._depart_bloque = False
        self._colle_en_depart = False
        self.allume = [False] * MOTEURS  # au départ, moteurs coupés (inventé : à vérifier sur la vraie main)
        self.depart_fait = False
        self.alarme = [0] * MOTEURS  # pour les essais : une alarme provoquée (voir provoquer_alarme)
        self.couple = [False] * MOTEURS
        self.objet: dict[int, int] = {}  # pour les essais : moteur (1 à 6) → la position où ce doigt touche l'objet
        self.coinces: set[int] = set()  # pour les essais : les moteurs (1 à 6) qui ne bougent pas du tout, sans rien dire
        self.duree_depart_s = 1.5  # inventé : la mise en position de départ dure 1,5 s
        self.dit_en_depart = True  # pour les essais : la main dit-elle « mise en position de départ en cours » ? (à vérifier)
        self.en_marche_sur_l_objet = False  # pour les essais : un doigt qui pousse sur l'objet reste dit « en marche »
        self.vitesse_ignoree = False  # pour les essais : la main va à sa vitesse d'origine quoi qu'on ait réglé
        self.saut_a_l_allumage = 0  # pour les essais : de combien les doigts sautent quand les moteurs s'allument
        self.refuser_d_allumer = False  # pour les essais : l'ordre d'allumer est reçu, mais les moteurs restent coupés
        self.reponse_perdue: set[str] = set()  # pour les essais : ces ordres ARRIVENT à la main, mais leur réponse se perd
        self.glisse_s = 0.0  # pour les essais : après un arrêt, les doigts glissent encore pendant ce temps
        # Pour les essais (relecture du 15.11.2026) : la main dit « couple atteint » PARTOUT, tout le temps (une lecture
        # collée à « vrai »). Avec `coinces` (des doigts qui ne bougent pas), c'est une main qui n'a rien pris.
        self.couple_colle = False
        # Pour les essais : le lancement est REFUSÉ, mais une partie de ses messages est partie quand même (lu : un
        # lancement envoie plusieurs messages) : les trois premiers doigts bougent.
        self.refus_a_moitie = False
        self.mouvements_lances = 0  # pour les essais : combien de mouvements sont VRAIMENT partis
        self.departs_lances = 0  # pour les essais : combien de mises en position de départ sont VRAIMENT parties
        self._en_route = [False] * MOTEURS
        self._depart_jusqu_a: float | None = None
        self._glisse_jusqu_a: float | None = None
        self._heure_de_la_main = time.monotonic()

    # ---------------------------------------------------------------- pour les essais
    def provoquer_alarme(self, moteur: int, code: int = 3) -> None:
        """Une alarme sur un moteur (1 à 6). Lu : 3 = trop de courant. Le moteur s'arrête."""
        self.alarme[moteur - 1] = code

    def preparer_sans_bouger(self) -> None:
        """Pour les essais : la main déjà préparée (moteurs allumés, mise en position de départ faite, doigts à 0)."""
        self.reliee, self.allume, self.depart_fait = True, [True] * MOTEURS, True

    # ---------------------------------------------------------------- simulation (tout est inventé)
    def _la_main_avance(self) -> None:
        maintenant = time.monotonic()
        dt, self._heure_de_la_main = maintenant - self._heure_de_la_main, maintenant
        if self._depart_jusqu_a is not None:  # une mise en position de départ en cours : les doigts reviennent à 0
            if not all(self.allume):
                self._depart_jusqu_a = None  # moteurs coupés : elle s'arrête là, pas finie
                return
            if self._depart_bloque:
                return  # hypothèse : trop peu de courant dans la main, les doigts ne bougent pas, et ça ne finit jamais
            self.position = [max(0.0, p - 5000 * dt) for p in self.position]
            if maintenant >= self._depart_jusqu_a:
                self.position, self.depart_fait, self._depart_jusqu_a = [0.0] * MOTEURS, True, None
                self.vitesse_dans_la_main = [VITESSE_D_ORIGINE] * MOTEURS  # lu (une phrase du manuel) : remis d'origine
                self.courant_dans_la_main = [COURANT_D_ORIGINE] * MOTEURS
            return
        if self._glisse_jusqu_a is not None and maintenant >= self._glisse_jusqu_a:
            self._en_route, self._glisse_jusqu_a = [False] * MOTEURS, None  # la glissade est finie
        for i in range(MOTEURS):
            if not self._en_route[i]:
                continue
            if not self.allume[i] or self.alarme[i]:
                self._en_route[i] = False
                continue
            if (i + 1) in self.coinces:
                continue  # il ne bouge pas, et ne dit rien
            vitesse = VITESSE_D_ORIGINE if self.vitesse_ignoree else self.vitesse_dans_la_main[i]
            but = float(self.cible[i])
            touche = self.objet.get(i + 1)
            sur_l_objet = touche is not None and self.position[i] <= touche < but
            if sur_l_objet:
                but = float(touche)
            pas = vitesse * dt
            if abs(but - self.position[i]) <= pas:
                self.position[i] = but
                if sur_l_objet:
                    self.couple[i] = True  # il pousse sur l'objet : « couple atteint », et il reste là
                else:
                    self._en_route[i] = False  # arrivé à sa cible
            else:
                self.position[i] += pas if but > self.position[i] else -pas

    def _appel(self, nom: str, *valeurs: Any) -> None:
        """Chaque appel : le trajet (pannes du faux kit), puis l'arrivée à la main."""
        self._trajet()  # une panne « coupure » du faux kit lève ConnectionError, comme une main injoignable
        with self._verrou:
            self._arrivee(nom)
            self.appels_du_kit.append((nom, valeurs))
            if not self.reliee and nom != "relier":
                raise ConnectionError("la liaison avec la fausse main n'est pas ouverte")
            self._la_main_avance()

    def _reponse(self, nom: str) -> None:
        if nom in self.reponse_perdue:
            raise ConnectionError(f"fausse main : la réponse à « {nom} » s'est perdue (l'ordre, lui, est arrivé)")

    # ---------------------------------------------------------------- la connexion et les lectures
    def relier(self) -> None:
        self._appel("relier")
        self.reliee = True

    def fermer(self) -> None:
        self._appel("fermer")
        self.reliee = False

    def nombre_de_moteurs(self) -> int:
        self._appel("nombre_de_moteurs")
        return self.moteurs

    def positions(self) -> list[int]:
        self._appel("positions")
        return [int(round(p)) for p in self.position]

    def etats(self) -> list[int]:
        self._appel("etats")
        etats = []
        for i in range(MOTEURS):
            pousse = self.couple[i] and self._en_route[i]
            if self.alarme[i]:
                etats.append(EN_ALARME)
            elif self._depart_jusqu_a is not None or self._colle_en_depart:
                etats.append(EN_DEPART if self.dit_en_depart else ARRETE)
            elif self._en_route[i] and (i + 1) not in self.coinces and (not pousse or self.en_marche_sur_l_objet):
                etats.append(EN_MARCHE)
            else:
                etats.append(ARRETE)
        return etats

    def alarmes(self) -> list[int]:
        self._appel("alarmes")
        return list(self.alarme)

    def moteurs_allumes(self) -> list[bool]:
        self._appel("moteurs_allumes")
        return list(self.allume)

    def cibles_atteintes(self) -> list[bool]:
        self._appel("cibles_atteintes")
        return [not self._en_route[i] and abs(self.position[i] - self.cible[i]) < 1 for i in range(MOTEURS)]

    def couples_atteints(self) -> list[bool]:
        self._appel("couples_atteints")
        return [True] * MOTEURS if self.couple_colle else list(self.couple)

    # ---------------------------------------------------------------- les ordres
    def _refus(self, nom: str) -> None:
        if "refus" in self.pannes:  # la panne « refus » du faux kit : la main dit non
            raise ActionImpossible("robot_refuse", f"la fausse main refuse « {nom} » (panne provoquée)")

    def allumer_les_moteurs(self) -> None:
        self._appel("allumer_les_moteurs")
        self._refus("allumer_les_moteurs")
        if not self.refuser_d_allumer:
            self.allume = [True] * MOTEURS
            self.position = [p + self.saut_a_l_allumage for p in self.position]
        self._reponse("allumer_les_moteurs")

    def couper_les_moteurs(self) -> None:
        self._appel("couper_les_moteurs")
        # Inventé : moteurs coupés, plus rien ne bouge et les doigts restent où ils sont.
        self.allume, self._en_route, self._depart_jusqu_a = [False] * MOTEURS, [False] * MOTEURS, None
        self._reponse("couper_les_moteurs")

    def mise_en_position_de_depart(self) -> None:
        self._appel("mise_en_position_de_depart")
        self._refus("mise_en_position_de_depart")
        if not all(self.allume):
            raise ActionImpossible("robot_refuse", "la fausse main refuse la mise en position de départ : moteurs coupés (inventé)")
        self.depart_fait, self.departs_lances = False, self.departs_lances + 1
        self._en_route, self.couple = [False] * MOTEURS, [False] * MOTEURS
        self._colle_en_depart = False
        self._depart_bloque = min(self.courant_dans_la_main) < self.courant_min_pour_le_depart
        self._depart_jusqu_a = time.monotonic() + self.duree_depart_s / self.acceleration
        self._reponse("mise_en_position_de_depart")

    def donner_une_cible(self, moteur: int, position: int, vitesse: int, courant: int) -> None:
        self._appel("donner_une_cible", moteur, position, vitesse, courant)
        self.cible[moteur - 1], self.vitesse_reglee[moteur - 1], self.courant_regle[moteur - 1] = position, vitesse, courant

    def regler_vitesse_et_courant(self, vitesse: int, courant: int) -> None:
        self._appel("regler_vitesse_et_courant", vitesse, courant)
        if self.refuser_les_reglages:
            raise ActionImpossible("robot_refuse", "la fausse main refuse « regler_vitesse_et_courant » (pour l'essai)")
        self.vitesse_reglee, self.courant_regle = [vitesse] * MOTEURS, [courant] * MOTEURS  # côté kit : pas encore dans la main

    def envoyer_les_reglages(self) -> None:
        self._appel("envoyer_les_reglages")
        if self.refuser_les_reglages:
            raise ActionImpossible("robot_refuse", "la fausse main refuse « envoyer_les_reglages » (pour l'essai)")
        self.vitesse_dans_la_main, self.courant_dans_la_main = list(self.vitesse_reglee), list(self.courant_regle)

    def lancer_le_mouvement(self) -> None:
        self._appel("lancer_le_mouvement")
        if self.refus_a_moitie:
            self._en_route = [True, True, True, False, False, False]
            raise ActionImpossible("robot_refuse", "la fausse main refuse « lancer_le_mouvement » (mais trois doigts sont partis)")
        self._refus("lancer_le_mouvement")
        if not self.depart_fait:  # lu : sans mise en position de départ, la main refuse (« LER_NOT_HOME »)
            raise ActionImpossible("main_pas_preparee", "la fausse main refuse de bouger : mise en position de départ pas faite")
        # Lu : la vitesse et le courant réglés partent vers la main avec ce lancement.
        self.vitesse_dans_la_main, self.courant_dans_la_main = list(self.vitesse_reglee), list(self.courant_regle)
        if all(self.allume):  # inventé : moteurs coupés, l'ordre ne fait rien
            self._en_route, self.couple, self._glisse_jusqu_a = [True] * MOTEURS, [False] * MOTEURS, None
            self.mouvements_lances += 1
        self._reponse("lancer_le_mouvement")

    def arreter_les_moteurs(self) -> None:
        self._appel("arreter_les_moteurs")
        if "arret_ignore" in self.pannes:  # la panne du faux kit : l'arrêt logiciel est ignoré
            return
        if self._depart_jusqu_a is not None and self._depart_bloque and self.depart_colle:
            self._colle_en_depart = True  # la main se dit encore « en mise en position de départ » (voir depart_colle)
        self._depart_jusqu_a = None  # inventé : l'arrêt arrête aussi la mise en position de départ (à vérifier)
        if self.glisse_s > 0 and any(self._en_route):
            self._glisse_jusqu_a = time.monotonic() + self.glisse_s  # les doigts glissent encore un instant
        else:
            self._en_route = [False] * MOTEURS
        self._reponse("arreter_les_moteurs")
