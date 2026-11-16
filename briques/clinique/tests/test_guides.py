"""La clinique en boîte — T32, les guides pour l'équipe (cahier, T32).

« Un guide d'une page et un TACHES.md par pièce, avec de petites tâches prêtes à distribuer à 35 personnes. NON_TESTE.md à
jour. Fini quand : chaque pièce de la partie 5 a son guide et ses tâches. »
Et la règle du kit : « une tâche = une personne, moins d'une heure, avec son test ».
Cette vérification contrôle aussi que les guides ne mentent pas : chaque fichier cité existe, chaque commande citée existe.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
GUIDES = RACINE / "briques" / "clinique" / "guides"
PIECES = {"5.1": "01_faux_dossier", "5.2": "02_porte", "5.3": "03_horloge", "5.4": "04_ecrans", "5.5": "05_listes_de_soin",
          "5.6": "06_taches_et_robot", "5.7": "07_resume", "5.8": "08_papiers", "5.9": "09_accueil", "5.10": "10_flotte",
          "5.11": "11_fiche_et_rejeu", "5.12": "12_robot_a_roues"}
SECTIONS = ("## Rôle", "## Fichiers", "## Lancer et voir", "## Les essais", "## Ce qui n'est pas testé")


def _cahier_pieces() -> list[str]:
    texte = (RACINE / "docs/projet/CAHIER_CLINIQUE.md").read_text(encoding="utf-8")
    return re.findall(r"^### (5\.\d+) ", texte, re.M)


def test_chaque_piece_de_la_partie_5_a_son_guide_et_ses_taches():
    assert _cahier_pieces() == list(PIECES)
    for section, dossier in PIECES.items():
        for nom in ("GUIDE.md", "TACHES.md"):
            assert (GUIDES / dossier / nom).exists(), (section, nom)
        guide = (GUIDES / dossier / "GUIDE.md").read_text(encoding="utf-8")
        assert f"(cahier {section})" in guide.splitlines()[0], dossier


@pytest.mark.parametrize("dossier", PIECES.values())
def test_un_guide_tient_sur_une_page_et_a_ses_cinq_parties(dossier):
    guide = (GUIDES / dossier / "GUIDE.md").read_text(encoding="utf-8")
    assert len(guide.splitlines()) <= 45 and len(guide) <= 4200, (dossier, len(guide.splitlines()), len(guide))
    for section in SECTIONS:
        assert section in guide, (dossier, section)


@pytest.mark.parametrize("dossier", PIECES.values())
def test_chaque_tache_est_petite_et_a_son_test(dossier):
    lignes = [l for l in (GUIDES / dossier / "TACHES.md").read_text(encoding="utf-8").splitlines() if l.startswith("- [ ]")]
    assert len(lignes) >= 3, dossier
    for ligne in lignes:
        assert " Test : " in ligne, (dossier, ligne)
        assert len(ligne) <= 420, (dossier, ligne)


def test_il_y_a_assez_de_taches_pour_35_personnes():
    total = sum(len([l for l in (GUIDES / d / "TACHES.md").read_text(encoding="utf-8").splitlines() if l.startswith("- [ ]")])
                for d in PIECES.values())
    assert total >= 35, total


def _textes():
    for d in PIECES.values():
        for nom in ("GUIDE.md", "TACHES.md"):
            yield f"{d}/{nom}", (GUIDES / d / nom).read_text(encoding="utf-8")
    yield "LISEZ_MOI.md", (GUIDES / "LISEZ_MOI.md").read_text(encoding="utf-8")


def _dossier_de(nom: str) -> Path:
    return (GUIDES / nom).parent


def test_chaque_fichier_cite_existe():
    for nom, texte in _textes():
        for cite in re.findall(r"`([^`\s]+)`", texte):
            if "/" in cite or re.search(r"\.(py|yaml|md|jsonl|json)$", cite):
                chemin = cite.split("::")[0].split("?")[0]
                if chemin.startswith("/clinique") or chemin.startswith("http"):
                    continue  # une adresse de page, pas un fichier
                ou = (RACINE, RACINE / "briques" / "clinique", _dossier_de(nom))  # la racine, la clinique, ou à côté
                assert any((base / chemin).exists() for base in ou), (nom, cite)


def test_chaque_commande_citee_existe():
    import lancer

    for nom, texte in _textes():
        for commande in re.findall(r"python3 lancer\.py ([a-z][a-z-]*)", texte):
            assert f"python3 lancer.py {commande}" in lancer.__doc__, (nom, commande)


def test_chaque_page_citee_repond():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from briques.clinique.ecrans import brancher_ecrans

    app = FastAPI()
    brancher_ecrans(app, code_equipe="")
    client = TestClient(app)
    for nom, texte in _textes():
        for page in set(re.findall(r"`(/clinique[^`\s]*)`", texte)):
            assert client.get(page).status_code in (200, 403), (nom, page)  # 403 : une page de l'équipe, avec le code


def test_aucune_promesse():
    for nom, texte in _textes():
        bas = texte.lower()
        for mot in ("compatible", "bientôt", "garanti", "100 %"):
            assert mot not in bas, (nom, mot)


def test_le_guide_general_mene_aux_guides_et_non_teste_est_a_jour():
    assert "guides/LISEZ_MOI.md" in (RACINE / "briques" / "clinique" / "GUIDE.md").read_text(encoding="utf-8")
    index = (GUIDES / "LISEZ_MOI.md").read_text(encoding="utf-8")
    for dossier in PIECES.values():
        assert f"{dossier}/GUIDE.md" in index, dossier
    assert "T32" in (RACINE / "NON_TESTE.md").read_text(encoding="utf-8").split("Les guides pour l'équipe")[-1]
