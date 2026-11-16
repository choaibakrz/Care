"""Brique 6 — Le formulaire du cerveau : la SEULE forme de réponse permise.

Le cerveau (un modèle de langue) répond par un petit texte JSON (un « formulaire » rempli), et rien d'autre :
- {"type": "action", "action": <une action de la carte d'identité>, "parametres": {...}}
- {"type": "question", "question": "<question courte dans la langue de la personne>"}

Le formulaire est fabriqué à partir de la carte d'identité du robot et du monde (lieux, objets) :
une action absente de la carte, un lieu ou un objet inconnu sont impossibles à écrire.
Avec llama.cpp, le modèle est FORCÉ de suivre ce formulaire (« grammaire »). Avec les autres moteurs,
la réponse est vérifiée ici, et refusée si elle ne le suit pas.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from briques.b01_prise.actions import ACTIONS, ActionDemandee
from briques.b01_prise.carte import CarteIdentite
from commun.monde import Monde

from .prise_cerveau import Decision

DIRECTIONS = ["devant", "gauche", "droite", "derriere"]


class FormulaireInvalide(Exception):
    """La réponse du modèle ne suit pas le formulaire (le modèle marche, mais sa réponse est inutilisable)."""


def _parametres(nom: str, carte: CarteIdentite, monde: Monde) -> dict:
    lieux = [l.id for l in monde.lieux]
    objets = [o.id for o in monde.objets if o.id != "objet_test"]
    nombre = {"type": "number"}
    p: dict[str, dict] = {}
    requis: list[str] = []
    if nom == "se_deplacer":  # deux variantes dans schema() : vers un lieu, ou d'une distance
        p = {"lieu": {"enum": lieux}, "dx": nombre, "dy": nombre, "vitesse": nombre}
    elif nom in ("regarder", "montrer"):
        p, requis = {"cible": {"enum": lieux + objets + DIRECTIONS}}, ["cible"]
    elif nom == "saisir":
        p, requis = {"objet": {"enum": objets}, "force": nombre}, ["objet"]
    elif nom == "poser":
        p = {"lieu": {"enum": lieux + ["ici"]}}
    elif nom == "rejouer_geste":
        p, requis = {"nom": {"enum": list(carte.gestes) or ["aucun"]}}, ["nom"]
    elif nom == "parler":
        p, requis = {"texte": {"type": "string", "maxLength": 200}}, ["texte"]
    elif nom == "ecouter":
        p = {"duree_s": nombre}
    return {"type": "object", "properties": p, "required": requis, "additionalProperties": False}


def schema(carte: CarteIdentite, monde: Monde) -> dict:
    """Le formulaire, au format « JSON Schema » (compris par llama.cpp pour forcer la réponse)."""
    variantes: list[dict] = []

    def variante(nom: str, parametres: dict) -> dict:
        return {"type": "object",
                "properties": {"type": {"const": "action"}, "action": {"const": nom}, "parametres": parametres},
                "required": ["type", "action", "parametres"], "additionalProperties": False}

    for nom in carte.capacites:
        params = _parametres(nom, carte, monde)
        if nom == "se_deplacer":  # un lieu OU une distance : jamais ni l'un ni l'autre
            pr = params["properties"]
            variantes.append(variante(nom, {"type": "object", "additionalProperties": False, "required": ["lieu"],
                                            "properties": {"lieu": pr["lieu"], "vitesse": pr["vitesse"]}}))
            variantes.append(variante(nom, {"type": "object", "additionalProperties": False, "required": ["dx"],
                                            "properties": {"dx": pr["dx"], "dy": pr["dy"], "vitesse": pr["vitesse"]}}))
        else:
            variantes.append(variante(nom, params))
    variantes.append({
        "type": "object",
        "properties": {"type": {"const": "question"}, "question": {"type": "string", "minLength": 2, "maxLength": 200}},
        "required": ["type", "question"], "additionalProperties": False,
    })
    return {"oneOf": variantes}


def _conforme(valeur: Any, regle: dict) -> bool:
    if "enum" in regle:
        return valeur in regle["enum"]
    if regle.get("type") == "number":
        if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
            return False
        try:
            return math.isfinite(float(valeur))
        except OverflowError:  # entier géant
            return False
    if regle.get("type") == "string":
        return isinstance(valeur, str) and 0 < len(valeur) <= regle.get("maxLength", 10_000)
    return False


def lire_reponse(contenu: str, carte: CarteIdentite, monde: Monde) -> Decision:
    """Transforme la réponse du modèle en Décision. Lève FormulaireInvalide si elle ne suit pas le formulaire."""
    try:
        obj = json.loads(contenu)
    except (json.JSONDecodeError, TypeError) as e:
        raise FormulaireInvalide(f"pas du JSON : {contenu[:80]!r}") from e
    if not isinstance(obj, dict):
        raise FormulaireInvalide("pas un objet")
    if obj.get("type") == "question" and set(obj) == {"type", "question"}:
        q = obj["question"]
        if not isinstance(q, str) or len(q.strip()) < 2 or len(q) > 200:
            raise FormulaireInvalide("question vide ou trop longue")
        return Decision(genre="question", texte=q.strip(), confiance=0.8)
    if obj.get("type") != "action" or set(obj) != {"type", "action", "parametres"}:
        raise FormulaireInvalide(f"forme inconnue : {list(obj)}")
    nom, params = obj["action"], obj["parametres"]
    if nom not in carte.capacites or nom not in ACTIONS:
        raise FormulaireInvalide(f"action hors de la carte : {nom!r}")
    if not isinstance(params, dict):
        raise FormulaireInvalide("parametres n'est pas un objet")
    regles = _parametres(nom, carte, monde)
    for k, v in params.items():
        if k not in regles["properties"] or not _conforme(v, regles["properties"][k]):
            raise FormulaireInvalide(f"précision non permise : {k}={v!r}")
    for k in regles["required"]:
        if k not in params:
            raise FormulaireInvalide(f"précision manquante : {k}")
    if nom == "se_deplacer" and not ({"lieu", "dx", "dy"} & set(params)):
        raise FormulaireInvalide("déplacement sans lieu ni distance")
    # Confiance : non mesurée pour un modèle de langue (0,8 fixe, au-dessus du seuil de 0,5). À améliorer.
    return Decision(genre="action", action=ActionDemandee(nom=nom, parametres=params), confiance=0.8)


def consigne(carte: CarteIdentite, monde: Monde) -> str:
    """Les instructions données au modèle. Elles ne changent pas d'une demande à l'autre (le moteur peut les garder
    en mémoire et répondre plus vite). La langue de la personne est donnée avec chaque demande."""
    def noms(chose) -> str:
        tous = [n for liste in chose.noms.values() for n in liste]
        return f"{chose.id} (= {', '.join(dict.fromkeys(tous))})"

    lignes = [f"- {n}: {ACTIONS[n].explication}" for n in carte.capacites]
    return "\n".join([
        f"You are the brain of a robot called « {carte.nom} » (kind: {carte.genre}). You never move motors yourself:",
        "you choose ONE action for a safety guard to check, or you ask ONE short question.",
        "Answer ONLY with JSON, exactly one of:",
        '  {"type":"action","action":"<name>","parametres":{...}}',
        '  {"type":"question","question":"<short question in the language of the person>"}',
        "Actions this robot can do (no other action exists):",
        *lignes,
        "Known places: " + "; ".join(noms(l) for l in monde.lieux),
        "Known objects: " + "; ".join(noms(o) for o in monde.objets if o.id != "objet_test"),
        f"Gestures: {', '.join(carte.gestes) or 'none'}. Directions for cible: {', '.join(DIRECTIONS)}.",
        "Rules:",
        "- Use the place/object ids above in parametres (e.g. cuisine, bouteille).",
        "- Choose an action only if the request clearly asks for it.",
        "- If the request is unclear, ambiguous, impossible for this robot, or not a request: ask a short question.",
        "- If the person says a speed (m/s), a distance (m) or a force (N), copy the number into vitesse, dx or force.",
        "  Never change it: the safety guard decides.",
        "- « stop », « arrête », « halt », « 停 » always mean the action arreter.",
        "- Questions must be in the language of the person (Swiss German: answer in standard German).",
    ])


def exemples(carte: CarteIdentite) -> list[dict]:
    """Quelques exemples de questions-réponses, seulement avec des actions que CE robot sait faire."""
    import json as _json

    modeles = [
        ("French", "Va à la table", "se_deplacer", {"lieu": "table"}),
        ("German", "Nimm die Tasse", "saisir", {"objet": "tasse"}),
        ("English", "Look at the kitchen", "regarder", {"cible": "cuisine"}),
        ("French", "Va à l'entrée à 4 mètres par seconde", "se_deplacer", {"lieu": "entree", "vitesse": 4}),
        ("Chinese", "停下", "arreter", {}),
    ]
    sortie = []
    for langue, phrase, action, params in modeles:
        if carte.sait(action):
            sortie += [{"role": "user", "content": f"[language: {langue}] {phrase}"},
                       {"role": "assistant", "content": _json.dumps({"type": "action", "action": action,
                                                                       "parametres": params}, ensure_ascii=False)}]
    for langue, phrase, question in [("English", "Bring me that", "Which object do you mean?"),
                                     ("Italian", "Che bella giornata!", "Cosa vuoi che faccia?"),
                                     ("German", "Flieg zur Decke", "Das kann ich nicht. Was soll ich stattdessen tun?")]:
        sortie += [{"role": "user", "content": f"[language: {langue}] {phrase}"},
                   {"role": "assistant", "content": _json.dumps({"type": "question", "question": question}, ensure_ascii=False)}]
    return sortie


def nomme(texte_norm: str, nom: str) -> bool:
    """Le nom (ou son pluriel, ou un mot composé allemand qui le contient) est-il dit ?
    « tasses », « bottles », « tazze » ; « Kaffeetasse », « Wasserflasche » ; en chinois, n'importe où."""
    from .branchements.regles import contient, normaliser

    if contient(texte_norm, nom):
        return True
    n = normaliser(nom).strip()
    if not n or " " in n or re.search(r"[\u4e00-\u9fff]", n) or len(n) < 3:
        return False
    for m in texte_norm.split():
        if m in (n + "s", n + "es", n + "n", n + "en", n + "e"):  # pluriels simples
            return True
        if len(m) == len(n) and len(n) >= 4 and m[:-1] == n[:-1] and m[-1] in "aeiou":  # tazza → tazze
            return True
        if len(m) > len(n) and m.endswith(n):  # mots composés allemands : Kaffeetasse, Haustür
            return True
    return False


def choses_inventees(decision: Decision, texte: str, monde: Monde) -> str | None:
    """Filet de sécurité : le modèle a-t-il choisi quelque chose que la personne n'a PAS dit ?
    (Le formulaire l'oblige à choisir dans des listes : face à « va là-bas », il peut inventer.)
    - un lieu, un objet ou une cible jamais nommés ;
    - une distance (dx, dy) sans aucun chiffre ni « un peu » dans la phrase ;
    - un geste jamais nommé.
    Rend la clé de la question à poser, ou None si tout va bien."""
    from .branchements.regles import _lexique, contient, lire_distance, normaliser, petit_deplacement_demande

    if decision.genre != "action" or decision.action is None:
        return None
    t = normaliser(texte)
    p = decision.action.parametres
    for cle, question in (("lieu", "question_lieu"), ("objet", "question_objet"), ("cible", "question_objet")):
        valeur = p.get(cle)
        if valeur is None or valeur in ("ici", *DIRECTIONS):
            continue
        chose = monde.lieu(valeur) or monde.objet(valeur)
        noms = [n for _, n in chose.tous_les_noms()] if chose else []
        if not any(nomme(t, n) for n in noms):
            return question
    if decision.action.nom == "se_deplacer" and ("dx" in p or "dy" in p):
        if lire_distance(texte) is None and not petit_deplacement_demande(texte):
            return "question_lieu"
    if decision.action.nom == "rejouer_geste":
        mots = [m for liste in _lexique()["gestes"].get(p.get("nom"), {}).values() for m in liste] + [str(p.get("nom", ""))]
        if not any(contient(t, m) for m in mots):
            return "incompris"
    return None


cible_non_nommee = choses_inventees  # ancien nom, gardé pour les tests
