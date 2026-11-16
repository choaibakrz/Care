"""La clinique en boîte — H05 : une nouvelle sorte d'étape, « contrôle », dans le chef de démonstration (brique 15).

Réponse de Hiba à Q20 : « oui, à ces conditions. Tu ajoutes seulement une nouvelle sorte d'étape à la brique 15 ; tu ne
changes aucune étape qui existe. Toutes les vérifications de l'ossature passent sans être changées. Tu notes le changement
dans DECISIONS.md. Un tour, pas plus. »
« Fini » veut dire :
- une étape peut écrire « controle: NOM » ; c'est une chose à faire comme les autres (une seule par étape) ;
- le chef reçoit ses contrôles par leur nom (la brique 15 ne connaît aucune pièce de la clinique) ; un nom inconnu se voit
  AVANT de jouer ;
- l'étape appelle la pièce et reçoit « réussie » ou « ratée », avec une ligne de détail ; une pièce qui casse : « ratée » ;
- les scénarios, les essais et les autres sortes d'étapes de la brique 15 ne changent pas.
Faux robot. Aucun vrai robot.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from briques.b15_chef_demo.chef import ChefDemo
from briques.b15_chef_demo.scenario import DOSSIER_SCENARIOS, CHOSES, ScenarioInvalide, charger, lire
from briques.b15_chef_demo.verifier import resume
from conftest import lancer

RACINE = Path(__file__).resolve().parents[3]


def _scenario(*etapes):
    return lire({"titre": "essai des contrôles", "etapes": list(etapes)})


def test_une_etape_peut_ecrire_controle_et_c_est_une_chose_comme_les_autres():
    sc = _scenario({"nom": "liste", "controle": "point_oublie"})
    assert sc.etapes[0].genre == "controle" and sc.etapes[0].controle == "point_oublie"
    assert "controle" in CHOSES
    assert "contrôle « point_oublie »" in "\n".join(resume(sc))
    with pytest.raises(ScenarioInvalide, match="une seule chose"):
        _scenario({"nom": "deux", "controle": "point_oublie", "attendre_s": 1})
    with pytest.raises(ScenarioInvalide):
        _scenario({"nom": "vide", "controle": ""})
    with pytest.raises(ScenarioInvalide, match="attendu"):
        _scenario({"nom": "avec_attendu", "controle": "x", "attendu": "rien"})


def test_un_nom_inconnu_se_voit_avant_de_jouer(fabrique_systeme):
    s = fabrique_systeme()
    sc = _scenario({"nom": "a", "controle": "existe"}, {"nom": "b", "controle": "faute_de_frappe"})
    with pytest.raises(ScenarioInvalide, match="faute_de_frappe"):
        ChefDemo(s, sc, controles={"existe": lambda: (True, "ok")})
    with pytest.raises(ScenarioInvalide, match="existe"):
        ChefDemo(s, sc)  # sans contrôles donnés : aucun nom n'est connu


def _jouer(s, sc, controles):
    async def go():
        await s.demarrer()
        try:
            return await ChefDemo(s, sc, acceleration=60.0, controles=controles).jouer()
        finally:
            await s.arreter()

    return lancer(go())


def test_l_etape_recoit_reussie_ou_ratee_avec_une_ligne_de_detail(fabrique_systeme):
    class Resultat:  # la forme des résultats de la clinique : .reussie et .detail
        def __init__(self, reussie, detail):
            self.reussie, self.detail = reussie, detail

    def casse():
        raise RuntimeError("pièce cassée exprès")

    controles = {"bon": lambda: (True, "tout va bien"), "mauvais": lambda: Resultat(False, "il manque la sonnette"),
                 "objet": lambda: Resultat(True, "livrée"), "casse": casse}
    sc = _scenario({"nom": "un", "controle": "bon"}, {"nom": "deux", "controle": "mauvais"},
                   {"nom": "trois", "controle": "objet"}, {"nom": "quatre", "controle": "casse"},
                   {"nom": "cinq", "annonce": "Fin."})
    res = _jouer(fabrique_systeme(), sc, controles)
    par_nom = {e.nom: e for e in res.etapes}
    assert par_nom["un"].resultat == "reussie" and par_nom["un"].genre == "controle" and par_nom["un"].detail == "tout va bien"
    assert par_nom["deux"].resultat == "ratee" and par_nom["deux"].detail == "il manque la sonnette"
    assert par_nom["deux"].cause == "controle"
    assert par_nom["trois"].resultat == "reussie" and par_nom["trois"].detail == "livrée"
    assert par_nom["quatre"].resultat == "ratee" and "pièce cassée exprès" in par_nom["quatre"].detail
    assert par_nom["cinq"].resultat == "reussie"  # la partition continue après un contrôle raté


def test_un_vrai_controle_de_la_clinique_se_joue_dans_le_chef(fabrique_systeme):
    from briques.clinique import repetition

    sc = _scenario({"nom": "point_oublie", "controle": "etape_7"})
    res = _jouer(fabrique_systeme(), sc, {"etape_7": repetition.CONTROLES[7]})
    assert res.etapes[0].resultat == "reussie" and "Il reste un point : la sonnette." in res.etapes[0].detail


def test_les_scenarios_et_les_essais_de_la_brique_15_ne_changent_pas():
    for chemin in ("briques/b15_chef_demo/scenarios", "briques/b15_chef_demo/tests"):
        diff = subprocess.run(["git", "diff", "--stat", "HEAD", "--", chemin], cwd=RACINE, capture_output=True, text=True)
        assert diff.stdout.strip() == "", (chemin, diff.stdout)
    for fichier in sorted(DOSSIER_SCENARIOS.glob("*.yaml")):
        assert charger(fichier).etapes, fichier  # chaque scénario existant se lit toujours
