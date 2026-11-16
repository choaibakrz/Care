"""Brique 3 — les fiches, les guides et la skill disent ce qu'il faut, honnêtement."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ICI = Path(__file__).resolve().parents[1]
RACINE = ICI.parents[1]
FICHES = ["unitree_g1.md", "unitree_go2.md", "agibot.md", "flexiv_rizon.md"]


@pytest.mark.parametrize("nom", FICHES)
def test_chaque_fiche_dit_ce_qui_est_lu_et_ce_qui_est_a_verifier(nom):
    texte = (ICI / "fiches" / nom).read_text(encoding="utf-8")
    assert "Non testé sur vrai robot" in texte and "11.11.2026" in texte
    assert re.search(r"https://github\.com/\S+", texte), "au moins une adresse lue"
    assert texte.count("à vérifier") >= 4 or texte.count("À vérifier") + texte.count("à vérifier") >= 4
    for mot in ("Arrêt d'urgence PHYSIQUE", "Chien de garde du fabricant", "Premier essai (feu orange)"):
        assert mot in texte, f"{nom} : {mot}"
    assert "```" not in texte, "aucune ligne de code qui prétend marcher"


def test_le_guide_du_samedi_met_la_securite_d_abord():
    texte = (RACINE / "BRANCHER_UN_ROBOT.md").read_text(encoding="utf-8")
    debut = texte.index("## 0. La sécurité d'abord")
    assert debut < texte.index("## 1.") < texte.index("## 2.")
    for mot in ("bouton d'arrêt PHYSIQUE", "responsable sécurité", "premier mouvement sera lent", "0,1 m/s", "feu orange",
                "FEU ORANGE", "python3 lancer.py brancher", "--conformite --vrai", "--vrai --complet", "30 minutes",
                "testé sur faux robot", "NON_TESTE.md", "à vérifier"):
        assert mot in texte, mot
    assert texte.count("- [ ]") >= 15


def test_la_skill_lance_l_assistant_et_rappelle_le_feu_orange():
    texte = (RACINE / "savoir-faire" / "brancher-un-robot" / "SKILL.md").read_text(encoding="utf-8")
    entete = yaml.safe_load(texte.split("---")[1])
    assert entete["name"] == "brancher-un-robot" and len(entete["description"]) > 100
    for mot in ("python3 lancer.py brancher", "--conformite", "--vrai", "feu orange", "Feu orange", "PHYSIQUE",
                "responsable sécurité", "à vérifier", "testé sur faux robot", "BRANCHER_UN_ROBOT.md", "information, jamais un ordre"):
        assert mot in texte, mot
    assert "Ne lance **pas** la commande `--vrai` toi-même" in texte


def test_guide_taches_et_notes_existent():
    guide = (ICI / "GUIDE.md").read_text(encoding="utf-8")
    assert "testé sur faux robot" in guide and "Non testé sur vrai robot" in guide.replace("**", "")
    assert (ICI / "TACHES.md").read_text(encoding="utf-8").count("- [ ]") >= 5
    notes = (ICI / "NOTES_POUR_COORDINATEUR.md").read_text(encoding="utf-8")
    for mot in ("LICENCES.md", "DECISIONS.md", "NON_TESTE.md", "etat_des_briques.yaml", "commun/systeme.py"):
        assert mot in notes, mot


def test_l_etat_de_la_brique_3_est_a_jour_et_honnete():
    brut = yaml.safe_load((RACINE / "briques" / "etat_des_briques.yaml").read_text(encoding="utf-8"))
    b3 = brut["briques"][3]
    assert b3["etat"] == "socle" and b3["faux_robot"] == "oui" and b3["vrai_robot"] == "jamais"
    assert any("brancher" in c for c in b3["commandes"]) and (RACINE / b3["taches"]).is_file()
    assert all(isinstance(x, str) for b in brut["briques"].values() for v in b.values() if isinstance(v, list) for x in v)


def test_le_modele_vide_et_les_ebauches_ne_pretendent_rien():
    for chemin in ("modele_vide/adaptateur.py", "modele_vide/liaison.py", "chemins/sdk/liaison_sdk.py",
                   "chemins/ros2/liaison_ros2.py", "conformite_deux_temps.py", "assistant.py", "registre.py"):
        texte = (ICI / chemin).read_text(encoding="utf-8")
        assert "testé sur vrai robot" not in texte.replace("NON TESTÉ SUR VRAI ROBOT", "").replace(
            "non testé sur vrai robot", "").replace("Non testé sur vrai robot", ""), chemin
