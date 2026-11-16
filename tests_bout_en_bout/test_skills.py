"""Nos skills (savoir-faire/*/SKILL.md) : bien formées, et chaque commande qu'elles citent existe vraiment."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

RACINE = Path(__file__).resolve().parents[1]
SKILLS = sorted((RACINE / "savoir-faire").glob("*/SKILL.md"))
LANCER = (RACINE / "lancer.py").read_text(encoding="utf-8")


def test_les_quatre_skills_demandees_par_hiba_sont_la_ou_en_route():
    noms = {s.parent.name for s in SKILLS}
    assert {"lire-le-defi", "ajouter-une-langue", "lancer-une-repetition"} <= noms


@pytest.mark.parametrize("chemin", SKILLS, ids=lambda p: p.parent.name)
def test_skill_bien_formee_et_commandes_reelles(chemin):
    texte = chemin.read_text(encoding="utf-8")
    entete = yaml.safe_load(texte.split("---")[1])
    assert entete["name"] == chemin.parent.name and len(entete["description"]) > 50
    for sous in set(re.findall(r"python3 lancer\.py ([a-z][a-z-]+)", texte)):
        if sous == "tests":
            continue
        assert f'"{sous}"' in LANCER, f"{chemin.parent.name} cite « lancer.py {sous} », absent de lancer.py"
    for module in set(re.findall(r"python3 -m ([\w.]+)", texte)):
        assert (RACINE / (module.replace(".", "/") + ".py")).is_file(), module
    for fichier in set(re.findall(r"`((?:briques|commun|outils)/[\w/.-]+\.(?:py|yaml|md|js))", texte)):
        assert (RACINE / fichier).exists(), f"{chemin.parent.name} cite {fichier}, introuvable"
    assert "feu orange" in texte.lower() or "Feu orange" in texte
