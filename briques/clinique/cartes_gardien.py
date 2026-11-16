"""Le gardien applique la carte de rôle du robot branché, R1 (cahier 5.10 ; tâche T22b).

    carte_r1 = CarteDuRobotBranche(systeme, cartes, fichier)   # cartes : cartes.CartesDeLaFlotte
    await carte_r1.appliquer()                                 # la carte devient des règles ; le gardien les relit
    await carte_r1.changer("Accueil", qui="...")               # R1 change de métier : noté dans la boîte noire
    coursier.carte_de_role = carte_r1                          # le coursier la donne au gardien avant son premier geste

Comment : le gardien de l'ossature lit déjà un fichier de règles en phrases simples. On fabrique ce fichier : toutes les
règles de l'ossature, PLUS les règles de la carte. La brique 7 n'est pas modifiée.
- Les lieux : pour chaque lieu du plan que la carte ne permet pas, une règle « le robot n'y va jamais, et n'y passe
  jamais » (un cercle de 0,3 m autour du lieu). C'est le gardien qui dit non.
- La vitesse : une règle de vitesse, que personne ne change en direct (ni l'écran, ni le vote du public).
- Les actions : le gardien n'a pas de règle « action interdite ». Une action hors de la carte est donc refusée AVANT le
  gardien : rien ne lui est demandé, rien ne part. Pareil pour un lieu nommé hors de la carte (deux contrôles valent
  mieux qu'un). Ce contrôle ne fait que refuser : il ne donne jamais un « oui » à la place du gardien.
- Si la carte ne peut pas être donnée au gardien (fichier impossible à écrire, règles refusées) : rien ne part.

DIRE VRAI : essayé sur le FAUX ROBOT seulement. Un déplacement « de tant de mètres » (sans nom de lieu) n'est arrêté que
s'il arrive dans le cercle d'un lieu interdit. Le volume de la voix du robot n'est pas appliqué ici (la prise n'a pas
de réglage de volume) : il l'est pour la voix du Mac (T22a).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from briques.b01_prise.actions import ActionDemandee
from briques.b07_gardien.regles import CHEMIN_REGLES, en_francais

from . import dossier
from .cartes import Carte, CartesDeLaFlotte

RAYON_M = 0.3
SOURCE = "clinique"
ENTETE = ("# FICHIER FABRIQUÉ par briques/clinique/cartes_gardien.py — ne pas le modifier à la main.\n"
          "# Ce sont les règles du gardien (briques/b07_gardien/regles.yaml), plus celles de la carte de rôle « {nom} ».\n"
          "# Pour changer : la carte (briques/clinique/cartes_de_role/) ou le mot « carte » du robot (flotte.yaml).\n")


AUTRES_ACTIONS = ("montrer", "rejouer_geste")  # ni un lieu ni un objet : le gardien n'a pas de « non » pour elles, il demande un humain


def _nom_fr(chose) -> str:
    """Le nom que le gardien veut lire dans la phrase d'une règle (comme briques/b07_gardien/regles.py)."""
    return (chose.noms.get("fr") or [chose.id])[0]


def lieux_du_plan() -> list[str]:
    return [l["nom"] for l in dossier.charger().lieux["lieux"]]


def _mot(texte: str) -> str:
    sans = "".join(c for c in unicodedata.normalize("NFKD", texte.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sans).strip("_")


def regles_avec_la_carte(carte: Carte, monde, base: Path = CHEMIN_REGLES) -> dict[str, Any]:
    """Les règles de l'ossature, plus celles de la carte. La carte ne retire aucune règle : elle en ajoute."""
    regles = yaml.safe_load(Path(base).read_text(encoding="utf-8"))
    regles["regles"].append({
        "id": "carte_vitesse", "sorte": "vitesse_max", "valeurs": {"m_s": carte.vitesse_max_m_s}, "en_direct": False,
        "phrase": f"Carte {carte.nom} : le robot ne va jamais plus vite que {en_francais(carte.vitesse_max_m_s)} mètre par seconde."})
    for lieu in lieux_du_plan():
        if monde.lieu(lieu) is not None and lieu not in carte.lieux_permis:
            regles["regles"].append({
                "id": f"carte_lieu_{_mot(lieu)}", "sorte": "zone_interdite", "valeurs": {"lieu": lieu, "rayon_m": RAYON_M},
                "en_direct": False,
                "phrase": f"Carte {carte.nom} : le robot ne va jamais à « {lieu} », et n'y passe jamais."})
    # H11 (relecture de la tranche 3) : la carte ne se contourne pas. Le gardien LUI-MÊME refuse, même si l'ordre ne
    # vient pas du coursier : les lieux du monde qui ne sont pas du plan de la clinique (cuisine, entrée, table, scène),
    # tous les objets si la carte ne permet pas de saisir, et il demande un humain pour toute autre action hors carte.
    du_plan = set(lieux_du_plan())
    for chose in monde.lieux:
        if chose.id not in du_plan and chose.id not in carte.lieux_permis:
            nom = _nom_fr(chose)
            regles["regles"].append({
                "id": f"carte_hors_plan_{_mot(chose.id)}", "sorte": "zone_interdite",
                "valeurs": {"lieu": chose.id, "rayon_m": RAYON_M}, "en_direct": False,
                "phrase": f"Carte {carte.nom} : le robot ne va jamais à « {nom} », et n'y passe jamais."})
    if carte.refus_action("saisir") or carte.refus_action("poser"):
        for chose in monde.objets:
            regles["regles"].append({
                "id": f"carte_objet_{_mot(chose.id)}", "sorte": "objets_interdits", "valeurs": {"objets": [chose.id]},
                "en_direct": False,
                "phrase": f"Carte {carte.nom} : le robot ne prend rien. Il ne touche jamais « {_nom_fr(chose)} »."})
    hors_carte = [a for a in AUTRES_ACTIONS if carte.refus_action(a)]
    if hors_carte:
        regles["regles"].append({
            "id": "carte_actions", "sorte": "demander_humain", "valeurs": {"actions": hors_carte}, "en_direct": False,
            "phrase": f"Carte {carte.nom} : ces actions ne sont pas dans la carte. Sans l'accord d'un humain, elles ne partent pas."})
    return regles


def ecrire_les_regles(carte: Carte, monde, fichier: str | Path, en_plus: list[dict[str, Any]] | tuple = ()) -> Path:
    """`en_plus` : d'autres règles à ajouter (les pauses des soignants, J05). Elles aussi ne font que retirer des droits."""
    fichier = Path(fichier)
    regles = regles_avec_la_carte(carte, monde)
    regles["regles"] += list(en_plus)
    texte = ENTETE.format(nom=carte.nom) + yaml.safe_dump(regles, allow_unicode=True, sort_keys=False)
    fichier.write_text(texte, encoding="utf-8")
    return fichier


class CarteDuRobotBranche:
    def __init__(self, systeme, cartes: CartesDeLaFlotte, fichier: str | Path, robot: str = "robot-r1") -> None:
        self.systeme, self.cartes, self.fichier, self.robot = systeme, cartes, Path(fichier), robot
        self._chez_le_gardien: Any = None  # ce que le gardien applique en ce moment : la carte, et les pauses en cours
        self.pauses = None  # les pauses des soignants (pauses.Pauses), si elles sont branchées (J05)

    def _signature(self) -> tuple:
        return (self.carte.nom, self.pauses.signature() if self.pauses is not None else ())

    @property
    def carte(self) -> Carte:
        return self.cartes.carte_de(self.robot)

    def appliquee(self) -> bool:
        return self._chez_le_gardien == self._signature()

    def refus(self, action: ActionDemandee) -> str | None:
        """Ce que la carte refuse, avant même de demander au gardien. None : la carte ne dit pas non."""
        carte = self.carte
        refus = carte.refus_action(action.nom)
        lieu = action.parametres.get("lieu") if action.nom in ("se_deplacer", "poser") else None
        if refus is None and lieu is not None and lieu != "ici":
            refus = carte.refus_lieu(str(lieu))
        return refus

    def refus_de_la_course(self, tache: dict[str, Any], a_un_bras: bool) -> str | None:
        """Une course entière : les deux lieux, et les gestes qu'il faudra. None : la carte la permet."""
        carte = self.carte
        actions = ("se_deplacer", "saisir", "poser") if a_un_bras else ("se_deplacer",)
        refus = [carte.refus_action(a) for a in actions] + [carte.refus_lieu(str(tache[c])) for c in ("de", "ou") if tache.get(c)]
        return next((r for r in refus if r), None)

    async def appliquer(self, qui: str = SOURCE) -> dict[str, Any]:
        """Écrire les règles de la carte et les faire relire par le gardien. Une erreur : les règles d'avant restent."""
        carte, gardien = self.carte, self.systeme.gardien
        signature = self._signature()
        en_plus = self.pauses.regles(self.systeme.monde) if self.pauses is not None else []
        ecrire_les_regles(carte, self.systeme.monde, self.fichier, en_plus=en_plus)
        avant = gardien.chemin_regles
        gardien.chemin_regles = self.fichier
        try:
            relu = await gardien.recharger(qui=qui)
        except Exception:
            gardien.chemin_regles = avant
            raise
        self._chez_le_gardien = signature
        return relu

    async def avant_le_gardien(self, action: ActionDemandee, conversation: str | None = None) -> str | None:
        """Appelé par le coursier avant chaque geste. Rend None si la carte laisse passer ; sinon la raison du refus."""
        if not self.appliquee():
            try:
                await self.appliquer()
            except Exception as erreur:  # sans la carte chez le gardien, on ne bouge pas
                return f"la carte de rôle n'a pas pu être donnée au gardien ({erreur})"
        if self.pauses is not None:
            await self.pauses.ecrire_dans_la_boite()  # une pause mise, levée ou finie seule : c'est dans la boîte noire
        refus = self.refus(action)
        if refus:
            await self.systeme.bus.emettre("note", SOURCE, quoi="refus_de_la_carte", robot=self.robot, carte=self.carte.nom,
                                           action=action.nom, raison=refus, conversation=conversation)
        return refus

    async def changer(self, carte: str, qui: str) -> dict[str, str]:
        """R1 change de métier : noté, donné au gardien tout de suite, écrit dans la boîte noire."""
        note = self.cartes.changer(self.robot, carte, qui)
        try:
            await self.appliquer(qui=qui)
        except Exception:
            self._chez_le_gardien = None  # le prochain geste réessaiera ; d'ici là, rien ne part
            raise
        await self.systeme.bus.emettre("note", SOURCE, quoi="carte_changee", **note)
        return note


def brancher_les_cartes(coursier, systeme) -> tuple[CartesDeLaFlotte, CarteDuRobotBranche | None]:
    """Pour les écrans : les cartes de la flotte, et, si un robot est branché, sa carte prête pour le gardien.
    Le fichier de règles fabriqué va dans le dossier de la boîte noire de la séance."""
    cartes = CartesDeLaFlotte()
    if coursier is None or systeme is None:
        return cartes, None
    dossier_regles = Path(systeme.boite_noire.dossier)
    dossier_regles.mkdir(parents=True, exist_ok=True)
    carte_r1 = CarteDuRobotBranche(systeme, cartes, dossier_regles / "regles_avec_la_carte_de_r1.yaml", robot=coursier.badge.id)
    coursier.carte_de_role = carte_r1  # le coursier la donne au gardien avant son premier geste
    from .monde_robots import MondeDesRobots
    from .repartiteur import Repartiteur

    coursier.repartiteur = Repartiteur(MondeDesRobots(cartes=cartes), cartes)  # le choix expliqué (avenant 2, K04)
    return cartes, carte_r1
