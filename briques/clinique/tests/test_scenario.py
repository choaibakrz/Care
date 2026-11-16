"""La clinique en boîte — T11a, le scénario : sept scènes, chacune avec son plan B. Internet coupé, aucun modèle.

On vérifie : le scénario a les sept scènes du cahier (4.2) ; chaque scène a un plan B, écrit avec les mots du chef de
démonstration (brique 15) ; chacune des quatorze étapes est dans une scène et une seule ; la répétition joue les
scènes dans l'ordre, à l'heure du scénario, avec la marque « temps accéléré » dès que l'horloge saute ; quand une
étape rate ou manque, le plan B de sa scène s'affiche, et la répétition dit quand même « RATÉE ».
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from briques.b15_chef_demo.scenario import MOYENS
from briques.clinique import chef_clinique, horloge, repetition
from briques.clinique.tests.la_vraie_repetition import la_vraie_repetition  # noqa: F401 (une aide d'essai)

RACINE = Path(__file__).resolve().parents[3]


def _ok(etiquette="SIMULÉ"):
    return lambda: repetition.Resultat(True, etiquette, "essai")


def _tout_ok():
    return {e.numero: _ok() for e in repetition.ETAPES}


def _jouer(controles):
    lignes: list[str] = []
    code = chef_clinique.jouer(controles, ecrire=lignes.append)
    return code, lignes


def _donnees():
    return chef_clinique.lire_fichier()


# ---------------------------------------------------------------------------------------------- le fichier du scénario
def test_les_sept_scenes_du_cahier_dans_l_ordre():
    scenario = chef_clinique.charger()
    assert [s.numero for s in scenario.scenes] == [1, 2, 3, 4, 5, 6, 7]
    titres = " | ".join(s.titre for s in scenario.scenes)
    for mot in ("arrivée", "papiers", "soin", "soir", "médecin", "flotte", "vérité"):
        assert mot in titres.lower(), mot
    assert scenario.marque == "inventé"


def test_chaque_scene_a_son_plan_b_avec_les_mots_du_chef():
    for scene in chef_clinique.charger().scenes:
        assert scene.plan_b, scene.titre
        for moyen in scene.plan_b:
            assert moyen.moyen in MOYENS, (scene.titre, moyen.moyen)  # tablette, main_humaine, mode_local, sauter
            assert len(moyen.consigne) > 10, (scene.titre, moyen.moyen)


def test_chaque_etape_est_dans_une_scene_et_une_seule():
    etapes = [n for s in chef_clinique.charger().scenes for n in s.etapes]
    assert sorted(etapes) == list(range(1, 15))
    assert etapes == sorted(etapes)  # les scènes suivent l'ordre des étapes du cahier


def test_les_reperes_sont_ceux_de_l_horloge_et_avancent():
    connus = horloge.reperes()
    minutes = []
    for scene in chef_clinique.charger().scenes:
        if scene.repere is None:
            continue
        assert scene.repere in connus, scene.repere
        h, m = connus[scene.repere]["heure"].split(":")
        minutes.append(connus[scene.repere]["jour"] * 1440 + int(h) * 60 + int(m))
    assert minutes == sorted(minutes) and len(set(minutes)) == len(minutes)


@pytest.mark.parametrize("casse, message", [
    (lambda d: d["scenes"][0].update(plan_b=[]), "plan B"),
    (lambda d: d["scenes"][0].pop("plan_b"), "plan_b"),
    (lambda d: d["scenes"][1]["plan_b"][0].update(moyen="magie"), "magie"),
    (lambda d: d["scenes"][2].update(couleur="bleu"), "couleur"),
    (lambda d: d["scenes"][3].update(repere="minuit"), "minuit"),
    (lambda d: d["scenes"][4]["etapes"].append(9), "9"),
    (lambda d: d["scenes"][5].update(etapes=[]), "étape"),
    (lambda d: d["scenes"].pop(), "13"),
    (lambda d: d.update(marque="vrai"), "inventé"),
])
def test_un_scenario_mal_ecrit_est_refuse_a_la_lecture(casse, message):
    donnees = _donnees()
    casse(donnees)
    with pytest.raises(chef_clinique.ScenarioCliniqueInvalide) as erreur:
        chef_clinique.lire(donnees)
    assert message in str(erreur.value)


# ---------------------------------------------------------------------------------------------- la répétition par scènes
def test_la_repetition_joue_les_scenes_dans_l_ordre_avec_l_heure():
    code, lignes = _jouer(_tout_ok())
    scenes = [l for l in lignes if l.startswith("Scène ")]
    assert [int(re.match(r"Scène (\d)", l).group(1)) for l in scenes] == [1, 2, 3, 4, 5, 6, 7]
    assert "Jour 1 — 9 h 00" in scenes[0] and "TEMPS ACCÉLÉRÉ" not in scenes[0]
    assert "Jour 1 — 19 h 00" in scenes[3] and "TEMPS ACCÉLÉRÉ" in scenes[3]
    assert "Jour 2" in scenes[4] and "TEMPS ACCÉLÉRÉ" in scenes[6]
    etapes = [l for l in lignes if re.match(r"\s*\d+\. ", l)]
    assert len(etapes) == 14 and all("[SIMULÉ]" in l for l in etapes)
    assert code == 0 and lignes[-1] == "RÉPÉTITION : RÉUSSIE"
    assert not any("plan B" in l.lower() for l in lignes)  # tout a réussi : aucun plan B à dire


def test_chaque_etape_sort_sous_sa_scene():
    _, lignes = _jouer(_tout_ok())
    scene, vues = None, {}
    for ligne in lignes:
        if ligne.startswith("Scène "):
            scene = int(ligne[6])
        trouve = re.match(r"\s*(\d+)\. ", ligne)
        if trouve:
            vues[int(trouve.group(1))] = scene
    attendu = {n: s.numero for s in chef_clinique.charger().scenes for n in s.etapes}
    assert vues == attendu


def test_une_etape_ratee_fait_dire_le_plan_b_de_sa_scene_et_la_repetition_reste_ratee():
    controles = _tout_ok()
    controles[8] = lambda: repetition.Resultat(False, "FAUX ROBOT", "le robot n'est pas arrivé")
    code, lignes = _jouer(controles)
    assert code == 1 and "étape ratée : 8" in lignes[-1]
    scene_3 = chef_clinique.charger().scenes[2]
    plans = [l for l in lignes if "plan B" in l]
    assert len(plans) == 1 and scene_3.plan_b[0].consigne in plans[0]
    debut = next(i for i, l in enumerate(lignes) if l.startswith("Scène 3"))
    suite = next(i for i, l in enumerate(lignes) if l.startswith("Scène 4"))
    assert debut < lignes.index(plans[0]) < suite
    # la démonstration continue : les scènes suivantes sont jouées
    assert any(re.match(r"\s*13\. \[SIMULÉ\] réussie", l) for l in lignes)


def test_une_piece_pas_construite_fait_dire_le_plan_b_sans_jamais_reussir():
    controles = _tout_ok()
    del controles[12]
    code, lignes = _jouer(controles)
    assert code == 1 and lignes[-1] == "RÉPÉTITION : RATÉE — 1 étape manquante"
    assert len([l for l in lignes if "plan B" in l]) == 1


def test_une_piece_cassee_expres_la_repetition_dit_ratee():
    controles = _tout_ok()

    def cassee():
        raise RuntimeError("pièce cassée exprès")

    controles[1] = cassee
    code, lignes = _jouer(controles)
    assert code == 1 and "RÉUSSIE" not in lignes[-1] and "1" in lignes[-1]


def test_le_plan_b_ne_compte_jamais_comme_une_reussite():
    for numero in range(1, 15):
        controles = _tout_ok()
        controles[numero] = lambda: repetition.Resultat(False, "SIMULÉ", "raté exprès")
        code, lignes = _jouer(controles)
        assert code == 1 and lignes[-1].startswith("RÉPÉTITION : RATÉE — "), numero


def test_le_bandeau_et_la_marque_sont_en_tete():
    _, lignes = _jouer(_tout_ok())
    assert "DONNÉES INVENTÉES" in lignes[0]


def test_la_commande_repetition_passe_par_les_scenes(la_vraie_repetition):
    sortie = la_vraie_repetition  # la commande, lancée une fois pour tous les essais (tests/la_vraie_repetition.py)
    lignes = sortie.stdout.strip().splitlines()
    assert len([l for l in lignes if l.startswith("Scène ")]) == 7
    assert len([l for l in lignes if re.match(r"\s*\d+\. ", l)]) == 14
    assert lignes[-1].startswith("RÉPÉTITION : ")
    assert (sortie.returncode == 0) == (lignes[-1] == "RÉPÉTITION : RÉUSSIE")


def test_l_ancienne_entree_de_la_repetition_marche_toujours():
    lignes: list[str] = []
    assert repetition.jouer(_tout_ok(), ecrire=lignes.append) == 0
    assert lignes[-1] == "RÉPÉTITION : RÉUSSIE"
