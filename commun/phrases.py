"""Fabriquer les phrases du robot dans la langue de la personne."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

ICI = Path(__file__).parent


@lru_cache(maxsize=1)
def _phrases() -> dict:
    return yaml.safe_load((ICI / "phrases.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def langues() -> dict:
    return yaml.safe_load((ICI / "langues.yaml").read_text(encoding="utf-8"))


def langue_de_reponse(langue: str | None) -> str:
    info = langues()["langues"].get(langue or "")
    if info is None:
        return langues()["defaut"]
    return info["reponse"]


class _Souple(dict):
    def __missing__(self, cle):  # un trou dans le modèle ne fait jamais planter le robot
        return "…"


def dire(cle: str, langue: str | None, **valeurs: Any) -> str:
    """dire("annonce.se_deplacer", "de", lieu="Küche") -> "Ich gehe zu: Küche." """
    modele = _chercher(langue_de_reponse(langue), cle) or _chercher("fr", cle) or cle
    return modele.format_map(_Souple(valeurs))


def _chercher(langue: str, cle: str) -> str | None:
    bloc: Any = _phrases().get(langue)
    for morceau in cle.split("."):
        if not isinstance(bloc, dict):
            return None
        bloc = bloc.get(morceau)
    return bloc if isinstance(bloc, str) else None


def expliquer_refus(raisons: Iterable[Any], langue: str | None, intro: str = "refus_intro") -> str:
    """Le refus expliqué, dans la langue de la personne (idée 4).
    intro="main_levee" : « Je lève la main : j'ai besoin d'aide. » (le gardien demande un humain, brique 8)."""
    lr = langue_de_reponse(langue)
    morceaux = [dire(intro, langue)]
    for r in raisons:
        code = r.code if hasattr(r, "code") else r["code"]
        details = r.details if hasattr(r, "details") else r.get("details", {})
        valeurs = {k: v for k, v in details.items() if not isinstance(v, (list, dict))}
        valeurs.setdefault("unite", "")
        if "parametre" in valeurs:  # « vitesse » -> « Geschwindigkeit »
            valeurs["parametre"] = _chercher(lr, f"parametres.{valeurs['parametre']}") or valeurs["parametre"]
        if "action" in valeurs:  # « se_deplacer » -> « mich bewegen »
            valeurs["action"] = _chercher(lr, f"actions.{valeurs['action']}") or valeurs["action"]
        for cle in ("zone", "objet", "lieu"):  # « cuisine » -> « Küche » : le gardien donne les noms (« zone_noms »)
            noms = details.get(f"{cle}_noms")
            if cle in valeurs and isinstance(noms, dict):
                nom = noms.get(lr) or noms.get("fr") or valeurs[cle]
                valeurs[cle] = nom[:1].upper() + nom[1:] if lr == "de" else nom  # en allemand, les noms prennent une majuscule
        morceaux.append(dire(f"refus.{code}", langue, **valeurs).replace(" .", ".").replace(" ,", ","))
    return " ".join(morceaux)


@lru_cache(maxsize=1)
def _oui_non() -> dict:
    return yaml.safe_load((ICI / "oui_non.yaml").read_text(encoding="utf-8"))


def est_ordre_arret(texte: str) -> bool:
    """« Stop », « arrête », « halt », « 停 »… dans n'importe quelle langue. Toujours prioritaire."""
    from briques.b06_cerveau.branchements.regles import _lexique, contient, normaliser

    t = normaliser(texte)
    return any(contient(t, m) for mots in _lexique()["verbes"]["arreter"].values() for m in mots)


def oui_ou_non(texte: str, langue: str | None = None) -> bool | None:
    """True pour un « oui » net, False pour un « non », None sinon.
    Strict : réponse courte (3 mots au plus, 4 caractères en chinois), sans négation ni question ;
    mots de la langue de la question (et « ok »). En cas de doute : None, et le robot redemande."""
    import re

    from briques.b06_cerveau.branchements.regles import contient, normaliser

    t = normaliser(texte)
    on = _oui_non()
    langues_ok = None
    if langue:
        langues_ok = {langue, "de" if langue == "gsw" else langue, "gsw" if langue == "de" else langue}
    def trouve(cle: str, toutes: bool = False) -> bool:
        return any(contient(t, m) for lg, mots in on[cle].items() if toutes or not langues_ok or lg in langues_ok
                   for m in mots) or (cle == "oui" and any(contient(t, m) for m in on.get("partout", [])))
    if trouve("non", toutes=True) or any(contient(t, m) for m in on.get("negations", [])):
        return False if trouve("non", toutes=True) else None
    cjk = re.findall(r"[\u4e00-\u9fff]", texte)
    court = len(cjk) <= 4 if cjk else len(t.split()) <= 3
    if "吗" in texte or "?" in texte or "？" in texte or not court:
        return None
    return True if trouve("oui") else None
