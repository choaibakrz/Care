"""Chaque langue du projet est complète partout où le robot en a besoin (outils/verifier_langues.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

RACINE = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verifier_langues", RACINE / "outils" / "verifier_langues.py")
verifier_langues = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verifier_langues)

LANGUES = list(yaml.safe_load((RACINE / "commun" / "langues.yaml").read_text(encoding="utf-8"))["langues"])


@pytest.mark.parametrize("langue", LANGUES)
def test_chaque_langue_est_complete(langue):
    assert verifier_langues.verifier(langue) == []


def test_le_controle_voit_ce_qui_manque(monkeypatch):
    """Une langue presque vide : le contrôle doit tout signaler, surtout « stop » non compris."""
    vrai = verifier_langues._yaml

    def faux(chemin):
        d = vrai(chemin)
        if chemin == "commun/langues.yaml":
            d["langues"]["rm"] = {"nom": "rumantsch", "reponse": "rm", "code_ecoute": "rm"}
        return d

    monkeypatch.setattr(verifier_langues, "_yaml", faux)
    manques = verifier_langues.verifier("rm")
    fichiers = {f for f, _ in manques}
    assert {"commun/phrases.yaml", "commun/oui_non.yaml", "commun/monde.yaml", "commun/chaine.py",
            "briques/b06_cerveau/branchements/regles_lexique.yaml"} <= fichiers
    assert any("stop" in quoi for _, quoi in manques)
    assert verifier_langues.main(["rm"]) == 1
