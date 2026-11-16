"""Brique 3 — La LIAISON : les seuls appels propres au fabricant. Modèle vide : tout est « à brancher ».

NON TESTÉ SUR VRAI ROBOT.

Un adaptateur = la mécanique commune (adaptateur.py, la même pour tous les robots) + une liaison (ce fichier).
La liaison parle au kit du fabricant (SDK : les fonctions Python livrées par le fabricant) ou à ROS 2 (un système
standard pour faire parler les programmes d'un robot). Elle ne décide rien et ne vérifie rien : le gardien et la prise
ont déjà tout vérifié ; l'adaptateur s'occupe du suivi, des limites, du chien de garde et de l'arrêt d'urgence.

Règles pour CHAQUE méthode de la liaison :
- Elle est appelée dans un « fil » à part (un thread : un petit programme qui tourne à côté du programme principal),
  une à la fois. Exception : les arrêts d'urgence partent chacun dans un fil NEUF (ils ne font jamais la queue) ;
  le kit doit donc accepter deux appels en même temps (à vérifier par kit).
- Elle rend la main vite (moins d'1 seconde). Ce qui est long (le robot marche, parle, fait un geste) se LANCE,
  puis l'adaptateur suit la fin dans lire_etat() (« occupe », « en_mouvement »).
- Robot injoignable : lever une exception (ConnectionError, TimeoutError…) ; l'adaptateur dit « liaison perdue »,
  et la prise déclenche l'arrêt d'urgence si une action était en cours.
- Le robot refuse : lever ActionImpossible(code, explication) (briques/b01_prise/adaptateur.py).
- Pas encore branchée : lever ABrancher (c'est ce que fait ce modèle vide, partout).

L'état rendu par lire_etat() est un dictionnaire. Clés connues (toutes facultatives) :
  batterie_pct (0 à 100) · x, y (m) et cap (degrés) de l'odomètre (le compteur de pas/roues du robot) ·
  en_mouvement (bool) · occupe (bool : un geste, une phrase, une prise en cours) · objet_tenu (texte ou None) ·
  erreurs (liste de textes) · arret_urgence (bool, vu par le robot) · entendu (texte, après « ecouter ») ·
  echec_action (texte : l'action lancée s'est arrêtée en route ; l'adaptateur la compte alors comme ratée).
"""
from __future__ import annotations

from typing import Any


class ABrancher(NotImplementedError):
    """Un appel au robot pas encore écrit. Le message dit quoi brancher et où chercher."""

    def __init__(self, quoi: str, conseil: str = "") -> None:
        self.quoi = quoi
        texte = f"À BRANCHER : {quoi}" + (f" — {conseil}" if conseil else "")
        super().__init__(texte + " (à vérifier dans la doc du fabricant)")


class LiaisonVide:
    """Le modèle vide. Copier, puis remplacer chaque « raise ABrancher » par l'appel du vrai kit."""

    chemin = "vide"
    # Vrai robot ? Les fausses liaisons (faux SDK, faux ROS 2) disent False. L'adaptateur l'affiche partout.
    vrai_robot = True
    # Les actions de la prise VRAIMENT branchées pour ce robot. La carte ne doit rien promettre de plus
    # (le test de conformité le vérifie). On en ajoute une seulement quand elle est écrite ET essayée.
    branchees: frozenset[str] = frozenset()
    # Le robot sait-il aller seul à un lieu nommé (« cuisine ») ? Sinon : seulement dx/dy (quelques mètres devant lui).
    sait_aller_au_lieu = False
    # Les x, y de l'odomètre sont-ils dans le repère du monde (commun/monde.yaml) ? Pour un vrai robot : NON tant que
    # ce n'est pas calé. Sinon le gardien croirait savoir où est le robot. Faux : la position n'est pas donnée au gardien.
    repere_du_monde = False

    def infos_simulation(self) -> dict[str, Any] | None:
        """Faux robot seulement : limites et gestes inventés pour la simulation. Vrai robot : None."""
        return None

    # ---------------------------------------------------------------- la connexion
    def ouvrir(self) -> None:
        """Ouvrir la connexion avec le robot et vérifier qu'il répond.
        DOIT durer moins de 2 s (délai de la prise) : chercher le robot sur le réseau se fait avant (création du kit).
        NE DOIT JAMAIS faire bouger le robot : pas de « se lever », pas de « mode marche », pas de moteur allumé."""
        raise ABrancher("ouvrir", "se connecter au robot, sans rien faire bouger")

    def fermer(self) -> None:
        """Fermer la connexion. L'adaptateur a déjà demandé l'arrêt normal juste avant."""
        raise ABrancher("fermer", "fermer la connexion")

    def tic(self) -> None:
        """Appelé toutes les 0,1 s. Rien à faire pour la plupart des kits. ROS 2 : traiter les messages reçus."""
        return None

    def signe_de_vie(self) -> None:
        """Appelé toutes les 0,2 s : vérifier que le robot répond (lire un état court suffit).
        Si le kit du fabricant a son propre signe de vie (« heartbeat »), l'envoyer ici. Robot muet : exception."""
        raise ABrancher("signe_de_vie", "un appel court qui prouve que le robot répond")

    def lire_etat(self) -> dict[str, Any]:
        """L'état du robot (voir les clés en haut du fichier). NE DOIT RIEN faire bouger."""
        raise ABrancher("lire_etat", "batterie, position de l'odomètre, en mouvement, erreurs")

    # ---------------------------------------------------------------- s'arrêter (à brancher EN PREMIER)
    def arreter_mouvement(self) -> None:
        """Arrêt NORMAL : vitesse nulle, gestes interrompus. Le robot reste debout et stable.
        Appelé à la fin de chaque déplacement, pour « arreter », pour annuler, et avant de fermer."""
        raise ABrancher("arreter_mouvement", "vitesse nulle, le robot reste stable (ex. un « stop » du kit)")

    def arret_urgence(self) -> None:
        """Le plus fort arrêt LOGICIEL que le kit permet, sans faire tomber le robot si possible.
        ATTENTION robots à jambes : certains « arrêts » du fabricant coupent les moteurs et le robot TOMBE
        (voir fiches/). Choix à faire avec le responsable sécurité, et à noter dans la fiche du robot.
        Un « arrêt de marche » (vitesse nulle) ne BLOQUE PAS le robot : il accepte l'ordre suivant.
        Choisir un appel qui rend un code (rien = arrêt « non confirmé ») et qui n'attend pas longtemps sa réponse.
        Ne remplace JAMAIS le bouton d'arrêt PHYSIQUE. Doit rendre la main vite ; une erreur ici est notée, jamais bloquante."""
        raise ABrancher("arret_urgence", "l'arrêt le plus sûr du kit (à choisir avec le responsable sécurité)")

    def rearmer(self) -> None:
        """Après un arrêt d'urgence, décision d'un humain : autoriser de nouveau les ordres.
        NE DOIT JAMAIS faire bouger le robot (ni le relever : ça se fait à la main, feu orange)."""
        raise ABrancher("rearmer", "lever le blocage du kit, sans mouvement")

    # ---------------------------------------------------------------- bouger
    def vitesse(self, vx: float, vy: float, vyaw: float) -> None:
        """Un ordre de vitesse COURT (m/s vers l'avant, m/s vers la gauche, rad/s pour tourner).
        L'adaptateur le répète toutes les 0,1 s ; s'il n'est plus répété, le robot doit s'arrêter seul
        (chien de garde du fabricant : à vérifier pour chaque robot, voir fiches/). La vitesse est déjà bridée."""
        raise ABrancher("vitesse", "un ordre de vitesse court, qui expire seul")

    def aller_au_lieu(self, lieu: str, vitesse_m_s: float) -> None:
        """Lancer la marche vers un lieu nommé (seulement si sait_aller_au_lieu). Fin suivie par en_mouvement."""
        raise ABrancher("aller_au_lieu", "navigation vers un lieu nommé (carte du lieu nécessaire)")

    def geste(self, nom: str, vitesse_relative: float) -> None:
        """Lancer un geste enregistré du robot, par son nom (les noms sont dans la carte). Fin suivie par « occupe »."""
        raise ABrancher("geste", "rejouer un geste enregistré du fabricant")

    def regarder(self, cible: str) -> None:
        """Tourner la tête ou la caméra vers une cible. Fin suivie par « occupe »."""
        raise ABrancher("regarder", "tourner la tête ou la caméra")

    def montrer(self, cible: str) -> None:
        """Montrer du doigt ou du corps. Fin suivie par « occupe »."""
        raise ABrancher("montrer", "montrer du bras ou du corps")

    def saisir(self, objet: str, force_n: float) -> None:
        """Lancer la prise d'un objet nommé (force déjà bridée). Fin : « occupe » faux et objet_tenu = objet."""
        raise ABrancher("saisir", "pince ou main du robot")

    def poser(self, lieu: str) -> None:
        """Lancer la pose de l'objet tenu (lieu nommé ou « ici »). Fin : « occupe » faux et objet_tenu vide."""
        raise ABrancher("poser", "ouvrir la pince ou la main")

    # ---------------------------------------------------------------- parler, écouter
    def parler(self, texte: str, langue: str) -> None:
        """Lancer la phrase par le haut-parleur du robot. Fin suivie par « occupe »."""
        raise ABrancher("parler", "haut-parleur du robot (ou laisser la voix au Mac : brique 4)")

    def ecouter(self, duree_s: float) -> None:
        """Lancer l'écoute avec les micros du robot ; le texte arrive ensuite dans lire_etat()['entendu']."""
        raise ABrancher("ecouter", "micros du robot (ou laisser l'écoute au Mac : brique 4)")
