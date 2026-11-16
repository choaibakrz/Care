"""Brique 7 — Les règles du gardien, écrites en phrases simples (fichier regles.yaml).

Une règle = une PHRASE en français simple (pour les humains) + une SORTE + des VALEURS (pour le gardien).
La phrase et les valeurs doivent dire la même chose : le chiffre principal et les noms (lieu, objets, gestes)
sont écrits dans la phrase. Sinon le gardien refuse de démarrer, et dit pourquoi.

Changer une règle en direct (écran, vote du public) : seulement si la règle dit `en_direct: true` (sans cette ligne :
jamais). Seulement l'allumer, l'éteindre, ou changer son chiffre principal. Jamais au-dessus des limites de
reglages.yaml (securite). La phrase est mise à jour avec le nouveau chiffre.
La distance aux personnes ne peut que GRANDIR en direct ; elle et la zone permise ne s'éteignent jamais en direct.
Les listes (objets, gestes) et les zones ne changent que dans le fichier (puis « relire les règles »).

Le fichier doit avoir au moins une règle de distance aux personnes et une zone permise, allumées. Une clé inconnue
(faute de frappe, ex. « en_dirct ») est refusée. Sinon : pas de démarrage, et le message dit quoi corriger.
"""
from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from briques.b01_prise.actions import ACTIONS
from commun.monde import Monde

from .geometrie import Cercle, Rectangle

CHEMIN_REGLES = Path(__file__).with_name("regles.yaml")

# Les sortes de règles, et les valeurs que chacune accepte.
SORTES: dict[str, str] = {
    "vitesse_max": "Vitesse maximale, en mètres par seconde (valeurs : m_s).",
    "force_max": "Force de serrage maximale, en newtons (valeurs : n).",
    "distance_personnes": "Distance minimale aux personnes, en mètres (valeurs : m, actions, si_personnes_inconnues).",
    "zone_interdite": "Le robot n'y va jamais, ni n'y passe (valeurs : lieu et rayon_m, ou rectangle).",
    "zone_permise": "Le robot reste dedans (valeurs : rectangle, ou « halle » = tout le monde de monde.yaml).",
    "objets_interdits": "Le robot ne les touche jamais (valeurs : objets).",
    "poids_max": "Poids maximal d'un objet saisi, en kilos (valeurs : kg, un nombre ou « carte »).",
    "objets_fragiles": "Pour les saisir, demander d'abord à un humain (valeurs : objets).",
    "demander_humain": "Ces actions ou ces gestes demandent d'abord l'accord d'un humain (valeurs : actions, gestes).",
}
CLES: dict[str, set[str]] = {
    "vitesse_max": {"m_s"}, "force_max": {"n"}, "distance_personnes": {"m", "actions", "si_personnes_inconnues"},
    "zone_interdite": {"lieu", "rayon_m", "rectangle"}, "zone_permise": {"lieu", "rayon_m", "rectangle"},
    "objets_interdits": {"objets"}, "poids_max": {"kg"}, "objets_fragiles": {"objets"},
    "demander_humain": {"actions", "gestes"},
}
# Le chiffre principal de chaque sorte : il est écrit dans la phrase, et c'est le seul qu'on change en direct.
VALEUR_PRINCIPALE = {"vitesse_max": "m_s", "force_max": "n", "distance_personnes": "m", "poids_max": "kg"}
ACTIONS_PRES_DES_PERSONNES = ["se_deplacer", "saisir", "poser", "rejouer_geste"]
RAYON_DEFAUT_M = 1.0
# Sans ces règles (au moins une de chaque sorte, allumée), le gardien refuse de démarrer.
# Elles ne s'éteignent jamais en direct (seulement dans le fichier, puis « relire les règles »).
OBLIGATOIRES = {"distance_personnes": "la distance aux personnes", "zone_permise": "la zone permise"}
# Pour ces sortes, un chiffre plus GRAND est plus strict : en direct, il ne peut que grandir.
# Pour les autres (vitesse, force, poids), plus petit = plus strict ; en direct, jamais au-dessus de reglages.yaml.
PLUS_GRAND_PLUS_STRICT = {"distance_personnes"}


class _Strict(BaseModel):
    """Une clé inconnue (faute de frappe, ex. « en_dirct ») est refusée au lieu d'être ignorée en silence."""

    model_config = ConfigDict(extra="forbid")


class Regle(_Strict):
    id: str
    phrase: str
    sorte: str
    valeurs: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    en_direct: bool = False  # true : peut se changer en direct (écran, vote). Sans cette ligne : jamais.
    noms: dict[str, str] = Field(default_factory=dict)  # nom de la zone dans chaque langue (zone sans lieu du monde)

    def lisible(self) -> dict[str, Any]:
        return {"id": self.id, "phrase": self.phrase, "active": self.active, "sorte": self.sorte,
                "en_direct": self.en_direct, "valeurs": dict(self.valeurs)}


class ChoixVote(_Strict):
    texte: str
    active: bool | None = None
    valeurs: dict[str, Any] = Field(default_factory=dict)


class Vote(_Strict):
    """Idée 9 : le public vote, le choix gagnant change une règle (choix écrits à l'avance par l'équipe)."""

    id: str
    question: str
    regle: str
    choix: dict[str, ChoixVote]


class Regles(_Strict):
    regles: list[Regle]
    votes: list[Vote] = Field(default_factory=list)

    def regle(self, ident: str) -> Regle | None:
        return next((r for r in self.regles if r.id == ident), None)

    def vote(self, ident: str) -> Vote | None:
        return next((v for v in self.votes if v.id == ident), None)

    def actives(self, sorte: str) -> list[Regle]:
        return [r for r in self.regles if r.active and r.sorte == sorte]

    def lisibles(self) -> list[dict[str, Any]]:
        return [r.lisible() for r in self.regles]


class ReglesInvalides(ValueError):
    def __init__(self, problemes: list[str]):
        self.problemes = problemes
        super().__init__("Règles du gardien à corriger (briques/b07_gardien/regles.yaml) :\n- " + "\n- ".join(problemes))


# ---------------------------------------------------------------- petits outils
def en_francais(x: Any) -> str:
    """0.3 -> « 0,3 » ; 15.0 -> « 15 »."""
    if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
        return str(int(x)) if float(x).is_integer() else f"{x:g}".replace(".", ",")
    return str(x)


def _nombre_positif(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def _simple(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _chiffre(x: float) -> str:
    """Le motif d'un chiffre dans une phrase : « 0,3 » ou « 0.3 », pas au milieu d'un autre nombre."""
    f = re.escape(en_francais(x)).replace(",", "[,.]")
    return rf"(?<![\d,.]){f}(?![\d]|[,.]\d)"


def chiffre_dans_la_phrase(x: float, phrase: str) -> bool:
    return re.search(_chiffre(x), phrase) is not None


def _nom_fr(chose) -> str:
    return (chose.noms.get("fr") or [chose.id])[0]


def noms_par_langue(chose) -> dict[str, str]:
    """Le premier nom de la chose dans chaque langue (pour les explications)."""
    return {lg: liste[0] for lg, liste in chose.noms.items() if liste}


# ---------------------------------------------------------------- vérifier le fichier
def _probleme_regle(r: Regle, monde: Monde) -> list[str]:
    P: list[str] = []
    v = r.valeurs
    if r.sorte not in SORTES:
        return [f"{r.id} : sorte inconnue « {r.sorte} ». Connues : {', '.join(SORTES)}"]
    if not r.phrase.strip():
        P.append(f"{r.id} : il manque la phrase")
    inconnues = set(v) - CLES[r.sorte]
    if inconnues:
        P.append(f"{r.id} : valeurs inconnues {sorted(inconnues)} (permises : {sorted(CLES[r.sorte])})")
    phrase = _simple(r.phrase)

    if r.sorte in VALEUR_PRINCIPALE:
        cle = VALEUR_PRINCIPALE[r.sorte]
        x = v.get(cle)
        if r.sorte == "poids_max" and x == "carte":
            pass
        elif not _nombre_positif(x):
            P.append(f"{r.id} : « {cle} » doit être un nombre plus grand que zéro")
        elif not chiffre_dans_la_phrase(x, r.phrase):
            P.append(f"{r.id} : la phrase ne dit pas le chiffre {en_francais(x)} (phrase et valeur doivent dire la même chose)")

    if r.sorte == "distance_personnes":
        actions = v.get("actions", ACTIONS_PRES_DES_PERSONNES)
        if not isinstance(actions, list) or any(a not in ACTIONS for a in actions):
            P.append(f"{r.id} : « actions » doit être une liste d'actions de la prise universelle")
        elif not actions:
            P.append(f"{r.id} : « actions » est vide : la règle ne protégerait personne")
        if v.get("si_personnes_inconnues", "humain") not in ("humain", "oui"):
            P.append(f"{r.id} : « si_personnes_inconnues » vaut « humain » ou « oui »")

    if r.sorte in ("zone_interdite", "zone_permise"):
        lieu, rect = v.get("lieu"), v.get("rectangle")
        if lieu is None and rect is None:
            P.append(f"{r.id} : une zone a besoin d'un « lieu » ou d'un « rectangle »")
        if lieu is not None:
            chose = monde.lieu(lieu)
            if chose is None:
                P.append(f"{r.id} : lieu inconnu « {lieu} » (voir commun/monde.yaml)")
            elif _simple(_nom_fr(chose)) not in phrase:
                P.append(f"{r.id} : la phrase ne nomme pas le lieu « {_nom_fr(chose)} »")
        elif not r.noms.get("fr"):
            P.append(f"{r.id} : une zone sans lieu a besoin d'un nom dans chaque langue (noms: {{fr: ..., de: ...}})")
        elif _simple(r.noms["fr"]) not in phrase:
            P.append(f"{r.id} : la phrase ne nomme pas la zone « {r.noms['fr']} »")
        if rect is not None and rect != "halle":
            try:
                rr = Rectangle(**{k: float(rect[k]) for k in ("x_min", "y_min", "x_max", "y_max")})
                if not all(math.isfinite(c) for c in (rr.x_min, rr.y_min, rr.x_max, rr.y_max)) \
                        or rr.x_min >= rr.x_max or rr.y_min >= rr.y_max:
                    raise ValueError
                if lieu is not None and monde.lieu(lieu) and not rr.contient(
                        (monde.lieu(lieu).position.x, monde.lieu(lieu).position.y)):
                    P.append(f"{r.id} : le lieu « {lieu} » n'est pas dans son rectangle")
            except (KeyError, TypeError, ValueError):
                P.append(f"{r.id} : « rectangle » = {{x_min, y_min, x_max, y_max}} en mètres (min < max), ou « halle »")
        if "rayon_m" in v and not _nombre_positif(v["rayon_m"]):
            P.append(f"{r.id} : « rayon_m » doit être un nombre plus grand que zéro")

    if r.sorte in ("objets_interdits", "objets_fragiles"):
        objets = v.get("objets")
        if not isinstance(objets, list) or not objets:
            P.append(f"{r.id} : « objets » doit être une liste d'objets de commun/monde.yaml")
        else:
            for o in objets:
                chose = monde.objet(o)
                if chose is None:
                    P.append(f"{r.id} : objet inconnu « {o} » (voir commun/monde.yaml)")
                elif _simple(_nom_fr(chose)) not in phrase:
                    P.append(f"{r.id} : la phrase ne nomme pas l'objet « {_nom_fr(chose)} »")

    if r.sorte == "demander_humain":
        actions, gestes = v.get("actions", []), v.get("gestes", [])
        if not isinstance(actions, list) or not isinstance(gestes, list) or not (actions or gestes):
            P.append(f"{r.id} : il faut des « actions » ou des « gestes » (listes)")
        elif any(a not in ACTIONS for a in actions):
            P.append(f"{r.id} : « actions » doit contenir des actions de la prise universelle")
        for g in gestes if isinstance(gestes, list) else []:
            if _simple(str(g)) not in phrase:
                P.append(f"{r.id} : la phrase ne nomme pas le geste « {g} »")
    return P


def problemes(regles: Regles, monde: Monde) -> list[str]:
    """Tout ce qui ne va pas dans les règles (liste vide = tout va bien).
    Un choix de vote au-dessus de reglages.yaml n'empêche pas de démarrer : il sera refusé au moment du vote."""
    P: list[str] = []
    if not regles.regles:
        P.append("aucune règle (« regles: [] ») : le gardien ne démarre pas sans règles")
    for sorte, nom in OBLIGATOIRES.items():
        if regles.regles and not regles.actives(sorte):
            P.append(f"il manque la règle de {nom} (sorte « {sorte} », allumée) : le gardien ne démarre pas sans elle")
    vus: set[str] = set()
    for r in regles.regles:
        if r.id in vus:
            P.append(f"{r.id} : deux règles ont le même nom")
        vus.add(r.id)
        P += _probleme_regle(r, monde)
    for vote in regles.votes:
        regle = regles.regle(vote.regle)
        if regle is None:
            P.append(f"vote {vote.id} : règle inconnue « {vote.regle} »")
            continue
        if len(vote.choix) < 2:
            P.append(f"vote {vote.id} : il faut au moins deux choix")
        for nom, choix in vote.choix.items():
            try:
                changer(regle, choix.active, choix.valeurs or None)
            except ValueError as e:
                P.append(f"vote {vote.id}, choix « {nom} » : {e}")
    return P


def charger_regles(chemin: str | Path, monde: Monde) -> Regles:
    """Lire et vérifier regles.yaml. Lève ReglesInvalides (avec la liste des problèmes) si quelque chose ne va pas."""
    try:
        donnees = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReglesInvalides([f"fichier introuvable : {chemin}"])
    except yaml.YAMLError as e:
        raise ReglesInvalides([f"le fichier n'a pas la bonne forme : {e}"])
    try:
        regles = Regles.model_validate(donnees)
    except ValidationError as e:
        raise ReglesInvalides(_erreurs_de_forme(e, donnees))
    P = problemes(regles, monde)
    if P:
        raise ReglesInvalides(P)
    return regles


def _erreurs_de_forme(e: ValidationError, donnees: Any) -> list[str]:
    """Les erreurs de forme en français simple : où (quelle règle, quel vote) et quoi corriger."""
    permises = {"regle": sorted(Regle.model_fields), "vote": sorted(Vote.model_fields),
                "choix": sorted(ChoixVote.model_fields), "fichier": sorted(Regles.model_fields)}
    P: list[str] = []
    for err in e.errors():
        loc = list(err["loc"])
        ou, sorte = "le fichier", "fichier"
        if len(loc) >= 2 and loc[0] in ("regles", "votes") and isinstance(loc[1], int):
            liste = donnees.get(loc[0]) if isinstance(donnees, dict) else None
            element = liste[loc[1]] if isinstance(liste, list) and loc[1] < len(liste) else None
            ident = element.get("id") if isinstance(element, dict) else None
            mot = "règle" if loc[0] == "regles" else "vote"
            ou = f"{mot} « {ident} »" if ident else f"{mot} n° {loc[1] + 1}"
            sorte = "regle" if loc[0] == "regles" else "vote"
            if loc[0] == "votes" and len(loc) >= 5 and loc[2] == "choix":
                ou, sorte = f"{ou}, choix « {loc[3]} »", "choix"
        if err["type"] == "extra_forbidden":
            P.append(f"{ou} : clé inconnue « {loc[-1]} » (faute de frappe ?). Clés permises : {', '.join(permises[sorte])}")
        elif err["type"] == "missing":
            P.append(f"{ou} : il manque « {loc[-1]} »")
        else:
            champ = f" « {loc[-1]} »" if loc and not isinstance(loc[-1], int) else ""
            P.append(f"{ou}{champ} : forme fausse ({err['msg']})")
    return P or [f"le fichier n'a pas la bonne forme : {e}"]


# ---------------------------------------------------------------- changer en direct
def changer(regle: Regle, active: bool | None = None, valeurs: dict[str, Any] | None = None,
            maxima: dict[str, float] | None = None) -> Regle:
    """La règle changée (l'originale ne bouge pas). Lève ValueError, en français, si ce n'est pas permis.
    maxima : les limites de reglages.yaml qu'une règle ne peut jamais dépasser (ex. {"vitesse_max": 0.3})."""
    if not regle.en_direct:
        raise ValueError(f"la règle « {regle.id} » ne se change pas en direct (seulement dans regles.yaml)")
    if active is None and not valeurs:
        raise ValueError("rien à changer (active, ou une nouvelle valeur)")
    nouvelle = regle.model_copy(deep=True)
    if active is not None:
        if not isinstance(active, bool):
            raise ValueError("« active » vaut true ou false")
        if active is False and regle.sorte in OBLIGATOIRES:
            raise ValueError(f"la règle « {regle.id} » ({OBLIGATOIRES[regle.sorte]}) ne s'éteint jamais en direct")
        nouvelle.active = active
    if valeurs:
        cle = VALEUR_PRINCIPALE.get(regle.sorte)
        if cle is None or set(valeurs) != {cle}:
            permis = f"seulement « {cle} »" if cle else "seulement l'allumer ou l'éteindre"
            raise ValueError(f"en direct, pour la règle « {regle.id} » : {permis}")
        x = valeurs[cle]
        if not (regle.sorte == "poids_max" and x == "carte") and not _nombre_positif(x):
            raise ValueError(f"« {cle} » doit être un nombre plus grand que zéro")
        maxi = (maxima or {}).get(regle.sorte)
        if maxi is not None and _nombre_positif(x) and x > maxi:
            raise ValueError(f"« {cle} » ne peut pas dépasser {en_francais(maxi)} (limite de reglages.yaml → securite)")
        ancien = regle.valeurs.get(cle)
        if regle.sorte in PLUS_GRAND_PLUS_STRICT and _nombre_positif(ancien) and x < ancien:
            raise ValueError(f"en direct, « {cle} » de la règle « {regle.id} » ne peut que grandir (plus strict) : "
                             f"aujourd'hui {en_francais(ancien)}, demandé {en_francais(x)}")
        nouvelle.valeurs[cle] = x
        nouvelle.phrase = _phrase_mise_a_jour(regle.phrase, ancien, x, cle)
    return nouvelle


def _plus_strict(sorte: str, a: Any, b: Any) -> bool:
    """Le chiffre b est-il plus strict que a ? (distance : plus grand ; vitesse, force, poids : plus petit)."""
    if sorte == "poids_max":  # « carte » = la limite de la carte ; un nombre ne fait que la baisser
        if a == "carte":
            return _nombre_positif(b)
        return _nombre_positif(b) and _nombre_positif(a) and b < a
    if not (_nombre_positif(a) and _nombre_positif(b)):
        return False
    return b > a if sorte in PLUS_GRAND_PLUS_STRICT else b < a


def garder_le_plus_strict(fichier: Regle, direct: Regle) -> tuple[Regle, list[str]]:
    """« Relire les règles » après un changement en direct : la règle du fichier, sauf ce que le direct a rendu
    PLUS STRICT (allumée, chiffre plus strict) : cela est gardé. Rend (la règle, ce qui a été gardé, en mots).
    Rien de ce qui a été rendu plus strict en direct n'est annulé en silence."""
    if fichier.sorte != direct.sorte:  # le fichier a changé la sorte : rien à comparer (noté par l'appelant)
        return fichier, []
    garde: list[str] = []
    nouvelle = fichier.model_copy(deep=True)
    if direct.active and not fichier.active:
        nouvelle.active = True
        garde.append("allumée en direct : elle reste allumée")
    cle = VALEUR_PRINCIPALE.get(fichier.sorte)
    if cle is not None:
        a, b = fichier.valeurs.get(cle), direct.valeurs.get(cle)
        if _plus_strict(fichier.sorte, a, b):
            nouvelle.valeurs[cle] = b
            nouvelle.phrase = _phrase_mise_a_jour(fichier.phrase, a, b, cle)
            garde.append(f"{cle} = {en_francais(b)} (changé en direct, plus strict que le fichier : {en_francais(a)})")
    return nouvelle, garde


def _phrase_mise_a_jour(phrase: str, ancien: Any, nouveau: Any, cle: str) -> str:
    if _nombre_positif(ancien) and _nombre_positif(nouveau) and chiffre_dans_la_phrase(ancien, phrase):
        return re.sub(_chiffre(ancien), en_francais(nouveau), phrase, count=1)
    return f"{phrase} (changé en direct : {cle} = {en_francais(nouveau)})"


# ---------------------------------------------------------------- formes et noms des zones
def forme_zone(regle: Regle, monde: Monde) -> Cercle | Rectangle:
    v = regle.valeurs
    rect = v.get("rectangle")
    if rect == "halle":
        return Rectangle(0.0, 0.0, float(monde.taille["largeur"]), float(monde.taille["hauteur"]))
    if rect:
        return Rectangle(*(float(rect[k]) for k in ("x_min", "y_min", "x_max", "y_max")))
    lieu = monde.lieu(v["lieu"])
    return Cercle((lieu.position.x, lieu.position.y), float(v.get("rayon_m", RAYON_DEFAUT_M)))


def noms_zone(regle: Regle, monde: Monde) -> dict[str, str]:
    if regle.noms:
        return dict(regle.noms)
    lieu = monde.lieu(regle.valeurs.get("lieu", ""))
    return noms_par_langue(lieu) if lieu else {}
