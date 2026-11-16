"""Les cartes de rôle (cahier 5.10 et 6.6 ; tâche T22a) : le métier d'un robot, écrit dans un fichier lisible.

    python3 lancer.py cartes                 les cinq cartes, et la carte de chaque robot

    les_cartes = charger_cartes()            # Accueil, Étage, Thérapie, Visite, Nuit
    flotte = CartesDeLaFlotte()              # la carte de chaque robot, lue dans flotte.yaml
    flotte.carte_de("robot-r1").refus_lieu("Hall")     # None = permis ; sinon une phrase simple qui dit non
    flotte.changer("robot-r1", "Accueil", qui="...")   # changer de métier en route : c'est noté
    MondeDesRobots(cartes=flotte)            # dans le monde simulé, un robot s'arrête avant un lieu que sa carte ne permet pas
    dire_avec_la_carte(carte, texte, langue, sortie)   # la voix du Mac, au volume de la carte

Une carte dit quatre choses : les lieux permis, la vitesse la plus haute, le volume de la voix, les actions permises.
Changer la carte d'un robot = changer un mot dans `flotte.yaml`. On ne touche pas au code.

DIRE VRAI :
- Ici (T22a) la carte est appliquée dans le MONDE SIMULÉ (les lieux) et à la VOIX du Mac (le volume).
- Pour R1, le robot branché, c'est le gardien de l'ossature qui applique la carte (lieux, vitesse) : voir
  `cartes_gardien.py` (T22b). Essayé sur le faux robot seulement.
- Le volume de la voix n'est appliqué qu'à la voix du Mac : la prise du robot n'a pas de réglage de volume.
- Une carte ne fait que RETIRER des droits. Elle ne remplace jamais le gardien, ni l'arrêt d'urgence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from . import dossier

DOSSIER = Path(__file__).resolve().parent / "cartes_de_role"
FICHIER_FLOTTE = Path(__file__).resolve().parent / "flotte.yaml"
TOUJOURS_PERMIS = ("arreter", "etat")
CLES = {"marque", "nom", "phrase", "lieux_permis", "vitesse_max_m_s", "volume_voix", "actions_permises"}


class CarteInvalide(ValueError):
    """Une carte de rôle est mal écrite. Le message dit quoi, en clair."""


class RefusDeLaCarte(PermissionError):
    """La carte du robot ne permet pas cela."""


def plafond_de_vitesse() -> float:
    """La vitesse la plus haute de l'ossature (reglages, « securite »). Une carte ne va jamais au-dessus."""
    from commun.systeme import REGLAGES_EXEMPLE, charger_reglages

    return float(charger_reglages(REGLAGES_EXEMPLE)["securite"]["vitesse_m_s"])


def _actions_de_la_prise() -> set[str]:
    from briques.b01_prise.actions import ACTIONS

    return set(ACTIONS)


@dataclass(frozen=True)
class Carte:
    nom: str
    phrase: str
    lieux_permis: tuple[str, ...]
    vitesse_max_m_s: float
    volume_voix: float
    actions_permises: tuple[str, ...]

    def refus_lieu(self, lieu: str) -> str | None:
        """None : le lieu est permis. Sinon, la phrase qui dit non."""
        return None if lieu in self.lieux_permis else f"la carte {self.nom} ne permet pas le lieu « {lieu} »"

    def refus_action(self, action: str) -> str | None:
        if action in TOUJOURS_PERMIS or action in self.actions_permises:
            return None
        return f"la carte {self.nom} ne permet pas l'action « {action} »"

    def lisible(self) -> dict[str, Any]:
        return {"nom": self.nom, "phrase": self.phrase, "lieux_permis": list(self.lieux_permis),
                "vitesse_max_m_s": self.vitesse_max_m_s, "volume_voix": self.volume_voix,
                "actions_permises": list(self.actions_permises)}


def _lire_une_carte(fichier: Path, lieux: set[str], plafond: float, actions: set[str]) -> Carte:
    try:
        d = yaml.safe_load(fichier.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as erreur:
        raise CarteInvalide(f"{fichier.name} : illisible ({erreur})") from erreur

    def exiger(condition: bool, message: str) -> None:
        if not condition:
            raise CarteInvalide(f"{fichier.name} : {message}")

    exiger(isinstance(d, dict), "ce n'est pas une carte")
    exiger(d.get("marque") == "inventé", "la marque « inventé » manque")
    inconnues, manquantes = sorted(set(d) - CLES), sorted(CLES - set(d))
    exiger(not inconnues, f"ligne inconnue « {', '.join(inconnues)} » (faute de frappe ?)")
    exiger(not manquantes, f"il manque « {', '.join(manquantes)} »")
    nom, phrase = str(d["nom"]), str(d["phrase"])
    exiger(nom in phrase, f"la phrase ne nomme pas la carte « {nom} »")
    lieux_permis = d["lieux_permis"]
    exiger(isinstance(lieux_permis, list) and lieux_permis, "« lieux_permis » doit être une liste de lieux, pas vide")
    hors = [l for l in lieux_permis if l not in lieux]
    exiger(not hors, f"lieu inconnu « {', '.join(map(str, hors))} » (voir faux_dossier/lieux.yaml)")
    vitesse, volume = d["vitesse_max_m_s"], d["volume_voix"]
    exiger(isinstance(vitesse, (int, float)) and 0 < vitesse <= plafond,
           f"la vitesse doit être plus grande que 0 et pas plus que {plafond} m/s (reglages, securite)")
    exiger(isinstance(volume, (int, float)) and 0 < volume <= 1, "le volume de la voix va de 0 à 1 (1 = la voix normale)")
    permises = d["actions_permises"]
    exiger(isinstance(permises, list), "« actions_permises » doit être une liste")
    pas_connues = [a for a in permises if a not in actions]
    exiger(not pas_connues, f"action inconnue « {', '.join(map(str, pas_connues))} » (voir la prise universelle)")
    oubli = [a for a in TOUJOURS_PERMIS if a not in permises]
    exiger(not oubli, f"« {', '.join(oubli)} » doit toujours être permis : un robot peut toujours s'arrêter et dire son état")
    return Carte(nom, phrase, tuple(lieux_permis), float(vitesse), float(volume), tuple(permises))


def charger_cartes(dossier_des_cartes: Path = DOSSIER) -> dict[str, Carte]:
    """Toutes les cartes du dossier, contrôlées. Une carte mal écrite : rien ne se charge, et le message dit quoi."""
    lieux = {l["nom"] for l in dossier.charger().lieux["lieux"]}
    plafond, actions = plafond_de_vitesse(), _actions_de_la_prise()
    cartes: dict[str, Carte] = {}
    for fichier in sorted(Path(dossier_des_cartes).glob("*.yaml")):
        carte = _lire_une_carte(fichier, lieux, plafond, actions)
        if carte.nom in cartes:
            raise CarteInvalide(f"{fichier.name} : deux cartes portent le nom « {carte.nom} »")
        cartes[carte.nom] = carte
    return cartes


class CartesDeLaFlotte:
    """La carte de chaque robot. Au départ : celle de `flotte.yaml`. Un changement en route est noté."""

    def __init__(self, fichier: Path = FICHIER_FLOTTE, dossier_des_cartes: Path = DOSSIER) -> None:
        self.cartes = charger_cartes(dossier_des_cartes)
        donnees = yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))
        self._noms: dict[str, str] = {r["id"]: r["nom"] for r in donnees["robots"]}
        self._carte: dict[str, str] = {}
        for r in donnees["robots"]:
            self._carte[r["id"]] = self._connue(r["carte"], f"flotte.yaml, {r['nom']}")
        self.changements: list[dict[str, str]] = []

    def _connue(self, nom: str, ou: str) -> str:
        if nom not in self.cartes:
            raise CarteInvalide(f"{ou} : carte inconnue « {nom} » (cartes : {', '.join(sorted(self.cartes))})")
        return nom

    def carte_de(self, robot: str) -> Carte:
        if robot not in self._carte:
            raise ValueError(f"robot inconnu « {robot} »")
        return self.cartes[self._carte[robot]]

    def changer(self, robot: str, carte: str, qui: str) -> dict[str, str]:
        """Le robot change de métier. C'est noté : qui, avant, après. Vaut jusqu'à l'arrêt du programme."""
        avant = self.carte_de(robot).nom
        self._carte[robot] = self._connue(carte, "changement de carte")
        note = {"robot": robot, "avant": avant, "apres": carte, "qui": str(qui)}
        self.changements.append(note)
        return note

    def permis(self, robot: dict[str, Any], lieu: str) -> str | None:
        """Pour le monde des robots : None si la carte du robot permet ce lieu, sinon la phrase qui dit non."""
        return self.carte_de(robot["id"]).refus_lieu(lieu)

    def robots(self) -> list[dict[str, str]]:
        return [{"id": i, "nom": self._noms[i], "carte": self._carte[i]} for i in self._carte]


def dire_avec_la_carte(carte: Carte, texte: str, langue: str, sortie: str | Path, haut_parleur: bool = False,
                       parler: Callable[..., Path] | None = None) -> Path:
    """La voix du Mac dit la phrase au volume de la carte. Une carte sans « parler » : refus."""
    refus = carte.refus_action("parler")
    if refus:
        raise RefusDeLaCarte(refus)
    if parler is None:
        from .accueil_voix import dire as parler
    return parler(texte, langue, sortie, haut_parleur=haut_parleur, volume=carte.volume_voix)


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print) -> int:
    flotte = CartesDeLaFlotte()
    ecrire("LES CARTES DE RÔLE — données inventées — une carte = le métier d'un robot")
    for carte in flotte.cartes.values():
        ecrire(f"\n{carte.nom} — {carte.phrase}")
        ecrire(f"  lieux permis : {', '.join(carte.lieux_permis)}")
        ecrire(f"  vitesse la plus haute : {carte.vitesse_max_m_s} m/s ; volume de la voix : {carte.volume_voix} (1 = voix normale)")
        ecrire(f"  actions permises : {', '.join(carte.actions_permises)}")
    ecrire("\nLes robots (flotte.yaml) : " + " ; ".join(f"{r['nom']} : carte {r['carte']}" for r in flotte.robots()))
    ecrire("Changer de métier : changer le mot « carte » du robot dans briques/clinique/flotte.yaml. On ne touche pas au code.")
    ecrire("DIRE VRAI : pour les robots simulés, la carte est appliquée dans le monde simulé (lieux) et à la voix du Mac "
           "(volume). Pour R1, le robot branché, le gardien applique la carte (lieux, vitesse) : essayé sur le faux robot "
           "seulement, jamais sur un vrai robot.")
    return 0
