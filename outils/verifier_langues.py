#!/usr/bin/env python3
"""Vérifier qu'une langue est complète partout où le robot en a besoin (hors ligne, rien n'est modifié).

    python3 outils/verifier_langues.py          toutes les langues de commun/langues.yaml
    python3 outils/verifier_langues.py rm       une seule langue (ici : le romanche, code « rm »)

Pour chaque fichier, dit « ok » ou ce qui manque. « manque » = le robot parlera mal cette langue (repli sur le
français, ou ordre non compris) ; « à faire à la main » = ce que ce contrôle ne sait pas vérifier.
Code de sortie : 0 si rien ne manque, 1 sinon. Testé dans tests_bout_en_bout/test_langues.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

A_LA_MAIN = [
    "nombres dits en lettres (« cinq », « fünf »…) : briques/b06_cerveau/branchements/regles.py → _MOTS_NOMBRES",
    "façons de dire une vitesse, une force, une distance : regles.py → _VITESSE, _FORCE, _DISTANCE",
    "« un peu » : regles.py → PETIT_DEPLACEMENT",
    "mot d'appel (« robot ») : reglages.exemple.yaml → voix.mots_d_appel",
    "voix du robot (Piper, voix du Mac) : outils/catalogue.yaml et briques/b04_oreilles_voix/branchements/",
    "étiquettes de l'écran du jury : briques/b13_ecran/static/jury.js",
    "mots du défi : briques/b17_kit_samedi/mots_cles.yaml (fr, de, en seulement)",
    "faire relire chaque phrase par quelqu'un qui parle la langue",
]


def _yaml(chemin: str) -> dict:
    return yaml.safe_load((RACINE / chemin).read_text(encoding="utf-8")) or {}


def _cles(bloc, prefixe: str = "") -> set[str]:
    """Toutes les clés « a.b.c » d'un bloc de phrases."""
    if not isinstance(bloc, dict):
        return {prefixe} if prefixe else set()
    res: set[str] = set()
    for k, v in bloc.items():
        res |= _cles(v, f"{prefixe}.{k}" if prefixe else str(k))
    return res


def _negations() -> dict:
    from commun.chaine import NEGATIONS

    return NEGATIONS


def verifier(langue: str) -> list[tuple[str, str]]:
    """[(fichier, ce qui manque)] ; vide si tout est là."""
    manques: list[tuple[str, str]] = []
    langues = _yaml("commun/langues.yaml")["langues"]
    if langue not in langues:
        return [("commun/langues.yaml", f"la langue « {langue} » n'y est pas (ajouter une ligne)")]
    reponse = langues[langue].get("reponse", langue)

    for fichier in ("commun/phrases.yaml", "briques/b15_chef_demo/phrases_chef.yaml"):
        phrases = _yaml(fichier)
        if reponse not in phrases:
            manques.append((fichier, f"pas de bloc « {reponse} » (copier le bloc fr et traduire)"))
            continue
        absentes = sorted(_cles(phrases["fr"]) - _cles(phrases[reponse]))
        if absentes:
            manques.append((fichier, f"bloc « {reponse} » : {len(absentes)} phrase(s) absente(s) : {', '.join(absentes[:8])}"))

    oui_non = _yaml("commun/oui_non.yaml")
    for cle in ("oui", "non"):
        if not (oui_non.get(cle) or {}).get(langue):
            manques.append(("commun/oui_non.yaml", f"pas de « {cle} » en « {langue} »"))

    lexique = _yaml("briques/b06_cerveau/branchements/regles_lexique.yaml")
    for section, entrees in lexique.items():
        if not isinstance(entrees, dict):
            continue
        sans = [nom for nom, par_langue in entrees.items() if isinstance(par_langue, dict) and not par_langue.get(langue)]
        if sans:
            grave = " (dont « arreter » : le robot ne comprendrait pas « stop » !)" if "arreter" in sans else ""
            manques.append(("briques/b06_cerveau/branchements/regles_lexique.yaml",
                            f"{section} sans mots en « {langue} » : {', '.join(sans[:8])}{grave}"))

    monde = _yaml("commun/monde.yaml")
    for sorte in ("lieux", "objets"):
        sans = [x.get("id", "?") for x in monde.get(sorte, []) if not (x.get("noms") or {}).get(langue)]
        if sans:
            manques.append(("commun/monde.yaml", f"{sorte} sans nom en « {langue} » : {', '.join(sans)}"))

    if langue not in _negations():
        manques.append(("commun/chaine.py", f"NEGATIONS : pas de mots de négation en « {langue} » (« ne … pas »)"))

    demandes = _yaml("briques/b06_cerveau/banc_demandes.yaml").get("demandes", [])
    sans = [d["id"] for d in demandes if langue not in (d.get("phrases") or {})]
    if sans:
        manques.append(("briques/b06_cerveau/banc_demandes.yaml",
                        f"{len(sans)} demande(s) du banc d'essai sans phrase en « {langue} » (pour mesurer le cerveau)"))
    return manques


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    langues = argv or list(_yaml("commun/langues.yaml")["langues"])
    tout_bon = True
    for lg in langues:
        if not re.fullmatch(r"[a-z]{2,3}", lg):
            print(f"  « {lg} » : un code de langue a 2 ou 3 lettres (fr, de, gsw, rm…)")
            return 1
        manques = verifier(lg)
        print(f"\n== {lg} : {'ok' if not manques else f'{len(manques)} manque(s)'}")
        for fichier, quoi in manques:
            print(f"  manque — {fichier} : {quoi}")
        tout_bon &= not manques
    print("\nÀ faire à la main (ce contrôle ne sait pas le vérifier) :")
    for ligne in A_LA_MAIN:
        print(f"  - {ligne}")
    return 0 if tout_bon else 1


if __name__ == "__main__":
    sys.exit(main())
