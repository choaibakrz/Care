"""Le scénario de la clinique : sept scènes, chacune avec son plan B (cahier 4.2, tâche T11).

    python3 lancer.py repetition

Le scénario est écrit dans scenario_clinique.yaml. Il est lu et vérifié AVANT de jouer, comme les scénarios du chef de
démonstration (brique 15) : une clé inconnue, une scène sans plan B, un repère inconnu, une étape oubliée ou rangée
dans deux scènes sont refusés, et le message dit quoi corriger.

Ce que fait ce petit chef :
  - il joue les scènes dans l'ordre ;
  - au début d'une scène, il fait sauter l'horloge de démonstration jusqu'au repère de la scène, et il écrit l'heure
    (avec la marque « TEMPS ACCÉLÉRÉ » dès le premier saut) ;
  - il joue les étapes de la scène à travers les vraies pièces (les contrôles de repetition.py) ;
  - si une étape rate ou n'est pas construite, il écrit le plan B de la scène, puis il continue.

Un plan B sauve la démonstration, jamais la répétition : une étape ratée ou manquante reste comptée, et la dernière
ligne dit « RATÉE ».

Limites, dites aussi dans NON_TESTE.md : le plan B est une consigne affichée, il n'est pas joué par le programme ;
chaque étape repart d'une clinique neuve (les scènes ne s'enchaînent pas dans une seule séance) ; le chef de
l'ossature (brique 15, « lancer.py scenario ») ne joue pas ces scènes : il ne connaît que les phrases dites au robot.
On lui reprend ses mots (tablette, main_humaine, mode_local, sauter) et ses phrases.
"""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from briques.b15_chef_demo.scenario import MOYENS

from . import horloge as horloge_clinique
from . import repetition

FICHIER = Path(__file__).resolve().parent / "scenario_clinique.yaml"


class ScenarioCliniqueInvalide(ValueError):
    """Le scénario ne suit pas le format : le message dit où et quoi corriger."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Moyen(_Strict):
    moyen: str
    consigne: str = Field(min_length=1)  # en clair : qui fait quoi

    @model_validator(mode="after")
    def _connu(self) -> "Moyen":
        if self.moyen not in MOYENS:
            raise ValueError(f"plan B inconnu « {self.moyen} » (connus : {', '.join(MOYENS)})")
        return self


class Scene(_Strict):
    numero: int
    titre: str = Field(min_length=1)
    repere: str | None = None  # un nom de heures_scenario.yaml ; sans repère, l'heure ne bouge pas
    etapes: list[int]
    annonce: str = ""
    plan_b: list[Moyen]

    @model_validator(mode="after")
    def _complete(self) -> "Scene":
        if not self.plan_b:
            raise ValueError(f"scène « {self.titre} » : il faut un plan B (au moins un moyen)")
        if not self.etapes:
            raise ValueError(f"scène « {self.titre} » : il faut au moins une étape de la répétition")
        if self.repere is not None and self.repere not in horloge_clinique.reperes():
            raise ValueError(f"scène « {self.titre} » : repère inconnu « {self.repere} » "
                             f"(connus : {', '.join(horloge_clinique.reperes())})")
        return self


class ScenarioClinique(_Strict):
    marque: str
    titre: str = Field(min_length=1)
    langue: str = "fr"
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> "ScenarioClinique":
        if self.marque != "inventé":
            raise ValueError("le scénario doit porter « marque: inventé »")
        if [s.numero for s in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("les scènes doivent être numérotées 1, 2, 3… dans l'ordre")
        connues = [e.numero for e in repetition.ETAPES]
        rangees = [n for s in self.scenes for n in s.etapes]
        for n in rangees:
            if n not in connues:
                raise ValueError(f"étape {n} : elle n'existe pas dans la grande répétition")
            if rangees.count(n) > 1:
                raise ValueError(f"étape {n} : elle est rangée dans deux scènes")
        oubliees = [n for n in connues if n not in rangees]
        if oubliees:
            raise ValueError("étapes de la répétition dans aucune scène : " + ", ".join(str(n) for n in oubliees))
        if rangees != sorted(rangees):
            raise ValueError("les scènes doivent suivre l'ordre des étapes de la répétition")
        heures = [_minutes(s.repere) for s in self.scenes if s.repere is not None]
        if any(b <= a for a, b in zip(heures, heures[1:])):
            raise ValueError("les repères des scènes doivent avancer : l'horloge ne revient pas en arrière")
        return self


def _minutes(repere: str) -> int:
    r = horloge_clinique.reperes()[repere]
    h, m = r["heure"].split(":")
    return r["jour"] * horloge_clinique.MINUTES_PAR_JOUR + int(h) * 60 + int(m)


def lire_fichier(chemin: Path = FICHIER) -> dict[str, Any]:
    """Le fichier, tel qu'il est écrit (une copie qu'on peut modifier dans un essai)."""
    donnees = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ScenarioCliniqueInvalide(f"{chemin} : le fichier doit commencer par « marque: inventé » puis « scenes: »")
    return copy.deepcopy(donnees)


def lire(donnees: dict[str, Any], origine: str = "le scénario de la clinique") -> ScenarioClinique:
    try:
        return ScenarioClinique.model_validate(donnees)
    except ValidationError as e:
        fautes = []
        for f in e.errors():
            ou = ".".join(str(x) for x in f["loc"])
            fautes.append(f"  - {ou or 'scénario'} : {f['msg'].removeprefix('Value error, ')}")
        raise ScenarioCliniqueInvalide(f"{origine} ne suit pas le format (voir briques/clinique/scenario_clinique.yaml) :\n"
                                       + "\n".join(fautes)) from None


def charger(chemin: Path = FICHIER) -> ScenarioClinique:
    return lire(lire_fichier(chemin), str(chemin))


def _phrase_du_chef(moyen: str, langue: str) -> str:
    """La phrase que le chef de démonstration (brique 15) dit pour ce moyen : « Je passe à la tablette. »"""
    from briques.b15_chef_demo.chef import dire_chef  # chargé au dernier moment : le chef de l'ossature est gros

    return dire_chef(moyen, langue)


def _ligne_plan_b(scene: Scene, langue: str) -> str:
    morceaux = [f"{m.moyen} : « {_phrase_du_chef(m.moyen, langue)} » {m.consigne}" for m in scene.plan_b]
    return f"    → plan B de la scène {scene.numero} (consigne affichée, pas jouée par le programme) — " + " ; puis ".join(morceaux)


def _sauter(horloge: horloge_clinique.HorlogeDeDemonstration, repere: str) -> None:
    try:
        asyncio.run(horloge.sauter(repere))
    except horloge_clinique.SautRefuse:
        attendu, etat = horloge_clinique.reperes()[repere], horloge.etat()
        if (etat["jour"], etat["heure"]) != (attendu["jour"], attendu["heure"]):
            raise  # un vrai retour en arrière : le scénario est mal écrit, on ne le cache pas


def jouer(controles: dict[int, Callable[[], repetition.Resultat]] | None = None,
          ecrire: Callable[[str], None] = print, scenario: ScenarioClinique | None = None,
          garder: list | None = None) -> int:
    """Joue le scénario, scène par scène. Rend 0 seulement si les quatorze étapes ont réussi."""
    controles = repetition.CONTROLES if controles is None else controles
    scenario = scenario or charger()
    etapes = {e.numero: e for e in repetition.ETAPES}
    horloge = horloge_clinique.HorlogeDeDemonstration(temps=lambda: 0.0)  # l'heure du scénario, sans la vraie montre
    ecrire("LA GRANDE RÉPÉTITION — la clinique en boîte — DONNÉES INVENTÉES")
    ecrire(f"{scenario.titre} — {len(scenario.scenes)} scènes, {len(etapes)} étapes. "
           "Chaque étape repart d'une clinique neuve ; l'heure est celle du scénario.")
    manquantes: list[int] = []
    ratees: list[int] = []
    with repetition.seance() as seance:
        if garder is not None:  # les essais comptés gardent ce que la séance a noté
            garder.append(seance)
        # tout est noté pour la fiche ; toute connexion vers l'extérieur est comptée et bloquée
        for scene in scenario.scenes:
            if scene.repere is not None:
                _sauter(horloge, scene.repere)
            seance.sauts = len(horloge.sauts)
            ecrire(f"Scène {scene.numero} — {scene.titre} — {horloge.etat()['texte']}")
            a_rattraper = False
            for numero in scene.etapes:
                issue = repetition.jouer_etape(etapes[numero], controles, ecrire)
                if issue == "manquante":
                    manquantes.append(numero)
                elif issue != "reussie":
                    ratees.append(numero)
                a_rattraper = a_rattraper or issue != "reussie"
            if a_rattraper:
                ecrire(_ligne_plan_b(scene, scenario.langue))
    return repetition.conclure(manquantes, ratees, ecrire)
