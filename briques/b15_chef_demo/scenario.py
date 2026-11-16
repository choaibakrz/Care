"""Brique 15 — Le format des scénarios (YAML), lu et vérifié AVANT de jouer.

Une faute de frappe dans un scénario doit se voir à la lecture, pas devant le jury.
Toute clé inconnue est refusée. Le format est décrit dans GUIDE.md ; un modèle commenté : scenarios/modele.yaml.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from briques.b01_prise.actions import ACTIONS
from briques.b02_faux_robot.faux_robot import PANNES as PANNES_FAUX_ROBOT
from commun.phrases import langues

DOSSIER_SCENARIOS = Path(__file__).with_name("scenarios")

# Les moyens de secours, dans l'ordre où on les écrit dans `plan_b`.
MOYENS: dict[str, str] = {
    "tablette": "Rejouer la même phrase en texte, par le clavier ou l'écran, au lieu de la voix.",
    "main_humaine": "Un humain prend la main (pilotage, brique 11 : place prête), puis la rend.",
    "mode_local": "Mettre de côté les cerveaux par le réseau ou en échec ; garder ceux de cet ordinateur et les règles.",
    "sauter": "Passer à l'étape suivante, en le disant.",
}
# Les pannes qu'on peut provoquer en répétition. « robot » = le faux robot refuse tout.
PANNES_CHEF: dict[str, str] = {
    "robot": "Le faux robot refuse toutes les nouvelles actions (panne « refus »).",
    "voix": "Les oreilles entendent mal : la phrase arrive brouillée, avec une confiance très basse.",
    "reseau": "Les cerveaux joints par le réseau ne répondent plus (le cerveau de secours prend le relais).",
}
PANNES = {**PANNES_CHEF, **PANNES_FAUX_ROBOT}
GENRES_ATTENDUS = ("action", "refus", "question", "confirmation", "aide", "reponse", "rien")
CHOSES = ("dire", "annonce", "attendre_s", "provoquer_panne", "reparer", "fiche", "controle")


class ScenarioInvalide(ValueError):
    """Le scénario ne suit pas le format : le message dit où et quoi corriger."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _langue_connue(v: str) -> str:
    if v not in langues()["langues"]:
        raise ValueError(f"langue inconnue : {v!r} (connues : {', '.join(langues()['langues'])})")
    return v


class Phrase(_Strict):
    """Une phrase et sa langue (fr, de, gsw, it, en, zh)."""

    texte: str = Field(min_length=1)
    langue: str = "fr"

    _verifier_langue = field_validator("langue")(_langue_connue)


class LangueFiche(_Strict):
    """« fiche: true » (langue du scénario), « fiche: de » ou « fiche: {langue: de} »."""

    langue: str = "fr"

    _verifier_langue = field_validator("langue")(_langue_connue)


class Attendu(_Strict):
    """Ce qui doit se passer pour que l'étape soit réussie (lu dans les événements du bus)."""

    genre: Literal["action", "refus", "question", "confirmation", "aide", "reponse", "rien"] = "action"
    action: str | None = None  # action : son nom ; confirmation : facultatif
    parametres: dict[str, Any] = Field(default_factory=dict)  # facultatif : ces précisions doivent correspondre
    statut: Literal["reussie", "demarree"] = "reussie"  # action : terminée et réussie, ou seulement démarrée
    contient: str | None = None  # reponse : un morceau du texte dit par le robot

    @model_validator(mode="before")
    @classmethod
    def _forme_courte(cls, v: Any) -> Any:
        if isinstance(v, str):  # « attendu: question » = {genre: question}
            return {"genre": v}
        if isinstance(v, dict) and "genre" not in v and "action" in v:
            return {"genre": "action", **v}
        return v

    @model_validator(mode="after")
    def _coherent(self) -> "Attendu":
        if self.action is not None and self.action not in ACTIONS:
            raise ValueError(f"action inconnue : {self.action!r} (voir briques/b01_prise/PRISE.md)")
        if self.genre == "action" and not self.action:
            raise ValueError("attendu « action » : il faut le nom de l'action (ex. action: se_deplacer)")
        if self.genre == "reponse" and not self.contient:
            raise ValueError("attendu « reponse » : il faut « contient: … »")
        return self

    def decrire(self) -> str:
        if self.genre == "action":
            precis = ", ".join(f"{k}={v}" for k, v in self.parametres.items())
            fin = "démarrée" if self.statut == "demarree" else "réussie"
            return f"action {self.action}{f' ({precis})' if precis else ''} {fin}"
        return {"refus": "refus du gardien, expliqué", "question": "une question du robot",
                "confirmation": "le robot demande « vous confirmez ? »", "rien": "rien de précis",
                "aide": "le robot lève la main et demande l'accord d'un humain (gardien)",
                "reponse": f"une réponse qui contient « {self.contient} »"}[self.genre]


class Etape(_Strict):
    nom: str = Field(min_length=1)
    # Une seule chose à faire :
    dire: Phrase | None = None  # passée à la chaîne comme une phrase entendue
    annonce: Phrase | None = None  # affichée à l'écran et dite par la voix (pas un ordre au robot)
    attendre_s: float | None = Field(default=None, ge=0)
    provoquer_panne: str | None = None  # répétition seulement
    reparer: bool | None = None  # répétition seulement : réparer les pannes provoquées
    fiche: LangueFiche | bool | None = None  # dire la fiche de vérité de la démonstration
    # Ajouté le 12.11.2026 (clinique en boîte, H05, accord de Hiba à Q20) : appeler par son nom un contrôle donné au chef
    # (ChefDemo(..., controles={nom: fonction})). La fonction rend (réussi, détail) ou un objet avec .reussie et .detail.
    controle: str | None = Field(default=None, min_length=1)
    # Facultatif :
    attendu: Attendu | None = None  # seulement avec « dire »
    duree_max_s: float | None = Field(default=None, gt=0)
    plan_b: list[str] | None = None  # remplace celui du scénario ; [] = aucun plan B
    attendre_fin: bool = True  # « dire » : attendre la fin de l'action avant l'étape suivante
    pause_apres_s: float = Field(default=0.0, ge=0)
    remarque: str = ""  # pour les humains, ignorée par le chef

    @model_validator(mode="before")
    @classmethod
    def _formes_courtes(cls, v: Any) -> Any:
        if isinstance(v, dict):
            v = dict(v)
            if isinstance(v.get("annonce"), str):  # « annonce: Bonjour ! » = en français
                v["annonce"] = {"texte": v["annonce"]}
            if isinstance(v.get("dire"), str):
                v["dire"] = {"texte": v["dire"]}
            if isinstance(v.get("fiche"), str):  # « fiche: de » = la fiche en allemand
                v["fiche"] = {"langue": v["fiche"]}
        return v

    def _choses(self) -> dict[str, Any]:
        return {"dire": self.dire, "annonce": self.annonce, "attendre_s": self.attendre_s,
                "provoquer_panne": self.provoquer_panne, "reparer": self.reparer, "fiche": self.fiche,
                "controle": self.controle}

    @model_validator(mode="after")
    def _une_seule_chose(self) -> "Etape":
        faites = [c for c, v in self._choses().items() if v is not None and v is not False]
        if len(faites) != 1:
            raise ValueError(f"étape « {self.nom} » : une seule chose à faire parmi {', '.join(CHOSES)} "
                             f"(trouvé : {', '.join(faites) or 'aucune'})")
        if self.attendu is not None and self.dire is None:
            raise ValueError(f"étape « {self.nom} » : « attendu » ne va qu'avec « dire »")
        if self.provoquer_panne is not None and self.provoquer_panne not in PANNES:
            raise ValueError(f"étape « {self.nom} » : panne inconnue {self.provoquer_panne!r} "
                             f"(connues : {', '.join(PANNES)})")
        if not self.attendre_fin and self.attendu and self.attendu.genre == "action" and self.attendu.statut == "reussie":
            raise ValueError(f"étape « {self.nom} » : avec « attendre_fin: false », écrire « statut: demarree » "
                             "dans l'attendu (le chef n'attend pas la fin de l'action)")
        _verifier_moyens(self.plan_b, f"étape « {self.nom} »")
        return self

    @property
    def genre(self) -> str:
        return next(c for c, v in self._choses().items() if v is not None and v is not False)


def _verifier_moyens(moyens: list[str] | None, ou: str) -> None:
    for m in moyens or []:
        if m not in MOYENS:
            raise ValueError(f"{ou} : plan B inconnu {m!r} (connus : {', '.join(MOYENS)})")


class Scenario(_Strict):
    titre: str = Field(min_length=1)
    description: str = ""
    robot: Literal["humanoide", "chien", "bras"] | None = None  # carte du faux robot pour laquelle il est écrit
    duree_visee_s: float | None = Field(default=None, gt=0)  # à vitesse normale
    langue: str = "fr"  # langue des phrases du chef (plan B, « on passe à la suite », fiche)
    duree_max_s: float = Field(default=20.0, gt=0)  # par défaut pour chaque étape « dire »
    plan_b: list[str] = Field(default_factory=list)  # par défaut pour chaque étape « dire »
    etapes: list[Etape] = Field(min_length=1)

    _verifier_langue = field_validator("langue")(_langue_connue)

    @model_validator(mode="after")
    def _noms_uniques(self) -> "Scenario":
        _verifier_moyens(self.plan_b, "scénario")
        vus: set[str] = set()
        for e in self.etapes:
            if e.nom in vus:
                raise ValueError(f"deux étapes s'appellent « {e.nom} » : chaque nom doit être unique")
            vus.add(e.nom)
        return self

    def plan_b_de(self, etape: Etape) -> list[str]:
        return list(self.plan_b if etape.plan_b is None else etape.plan_b)

    def duree_max_de(self, etape: Etape) -> float:
        return etape.duree_max_s or self.duree_max_s

    def numero(self, ref: str) -> int:
        """« 3 » ou « salut_gsw » → numéro de l'étape (à partir de 1)."""
        if ref.isdigit():
            n = int(ref)
            if not 1 <= n <= len(self.etapes):
                raise ScenarioInvalide(f"étape {n} : le scénario a {len(self.etapes)} étapes (de 1 à {len(self.etapes)})")
            return n
        for i, e in enumerate(self.etapes, 1):
            if e.nom == ref:
                return i
        raise ScenarioInvalide(f"aucune étape ne s'appelle « {ref} »")


def lire(donnees: dict, origine: str = "scénario") -> Scenario:
    try:
        return Scenario.model_validate(donnees)
    except ValidationError as e:
        fautes = []
        for f in e.errors():
            ou = ".".join(str(x) for x in f["loc"])
            fautes.append(f"  - {ou or 'scénario'} : {f['msg'].removeprefix('Value error, ')}")
        raise ScenarioInvalide(f"{origine} ne suit pas le format (voir briques/b15_chef_demo/GUIDE.md) :\n"
                               + "\n".join(fautes)) from None


def charger(chemin: str | Path) -> Scenario:
    chemin = Path(chemin)
    if not chemin.exists() and (DOSSIER_SCENARIOS / chemin).exists():
        chemin = DOSSIER_SCENARIOS / chemin
    with open(chemin, encoding="utf-8") as f:
        donnees = yaml.safe_load(f)
    if not isinstance(donnees, dict):
        raise ScenarioInvalide(f"{chemin} : le fichier doit commencer par « titre: … » puis « etapes: »")
    return lire(donnees, str(chemin))


def lire_pannes(textes: list[str], scenario: Scenario) -> dict[int, str]:
    """["robot@3", "voix@salut_gsw"] → {3: "robot", 4: "voix"}. Une panne par étape."""
    pannes: dict[int, str] = {}
    for t in textes:
        nom, sep, ref = t.partition("@")
        if not sep or not nom or not ref:
            raise ScenarioInvalide(f"--panne {t!r} : écrire NOM@ÉTAPE, par exemple robot@3 ou voix@salut_gsw")
        if nom not in PANNES:
            raise ScenarioInvalide(f"--panne {t!r} : panne inconnue (connues : {', '.join(PANNES)})")
        pannes[scenario.numero(ref)] = nom
    return pannes
