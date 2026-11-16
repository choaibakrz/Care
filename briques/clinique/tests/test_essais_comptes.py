"""La clinique en boîte — J01a, les essais comptés (avenant jury, J01 ; cahier 8 et 5.11).

« Fini » veut dire, pour cette première moitié :
- la liste des vingt essais est fixe, écrite dans un fichier : on rejoue exactement les mêmes ;
- chaque essai change de petites choses : la langue d'arrivée, le point oublié, l'objet demandé, un objet absent ;
- la commande affiche, pour chaque étape, « réussie tant de fois sur vingt », avec l'étiquette de l'étape ;
- une pièce cassée exprès : le tableau montre l'échec, avec le numéro de l'essai, l'étape et l'heure de la boîte noire ;
- une étape sans pièce s'affiche « pas encore construite » ;
- aucun échec n'est effacé ni rejoué ; la fiche dit quel cerveau a servi, l'étiquette FAUX ROBOT et la date.
Le compteur d'essais réels est la seconde moitié (J01b). Internet coupé, aucun modèle.
"""
from __future__ import annotations

import re

import pytest

from briques.b12_boite_noire.journal import lire
from briques.clinique import essais, repetition


def _ok(etiquette="SIMULÉ"):
    return lambda: repetition.Resultat(True, etiquette, "essai")


def _faux_controles():
    controles = {n: _ok() for n in range(1, 15)}
    controles[8] = _ok("FAUX ROBOT")
    return controles


def _jouer(controles, tmp_path, liste=None):
    lignes: list[str] = []
    bilan = essais.jouer_les_essais(liste or essais.charger(), controles, ecrire=lignes.append, dossier=tmp_path)
    return bilan, lignes


# ---------------------------------------------------------------------------------------------- la liste fixe
def test_la_liste_a_vingt_essais_fixes_avec_les_changements_demandes():
    liste = essais.charger()
    assert [e["numero"] for e in liste] == list(range(1, 21))
    assert {e["langue"] for e in liste} == {"it", "de", "fr", "en"}
    assert {e["point_oublie"] for e in liste} == {1, 2, 3, 4, 5, 6}
    assert len({e["objet"] for e in liste}) >= 5
    absents = [e for e in liste if e["objet_absent"]]
    assert 2 <= len(absents) <= 6
    assert any(e["cerveau_lent"] for e in liste) and not all(e["cerveau_lent"] for e in liste)
    assert essais.charger() == liste  # la même liste à chaque lecture : pas de hasard


def test_un_fichier_d_essais_mal_ecrit_est_refuse(tmp_path):
    mauvais = tmp_path / "essais.yaml"
    mauvais.write_text("marque: inventé\nessais:\n  - {numero: 1, langue: xx, point_oublie: 3, objet: couverture, "
                       "objet_absent: false, cerveau_lent: false}\n", encoding="utf-8")
    with pytest.raises(essais.EssaisInvalides, match="xx"):
        essais.charger(mauvais)
    mauvais.write_text("marque: inventé\nessais:\n  - {numero: 1, langue: it, point_oublie: 9, objet: couverture, "
                       "objet_absent: false, cerveau_lent: false}\n", encoding="utf-8")
    with pytest.raises(essais.EssaisInvalides, match="9"):
        essais.charger(mauvais)


# ---------------------------------------------------------------------------------------------- les changements arrivent aux pièces
@pytest.mark.parametrize("langue, debut", [("it", "Buongiorno"), ("de", "Guten Tag"), ("fr", "Bonjour"), ("en", "Hello")])
def test_la_langue_d_arrivee_change_vraiment(langue, debut):
    with repetition.variation({"langue": langue}):
        resultat = repetition.CONTROLES[1]()
    assert resultat.reussie is True, resultat.detail
    assert debut in resultat.detail and f"({langue})" in resultat.detail


@pytest.mark.parametrize("numero, nom", [(1, "la présentation"), (3, "la sonnette"), (4, "le lit")])
def test_le_point_oublie_change_vraiment(numero, nom):
    with repetition.variation({"point_oublie": numero}):
        resultat = repetition.CONTROLES[7]()
    assert resultat.reussie is True, resultat.detail
    assert f"Il reste un point : {nom}." in resultat.detail


def test_un_objet_absent_passe_a_un_humain_et_aucun_robot_ne_bouge():
    with repetition.variation({"objet": "fauteuil roulant", "objet_absent": True}):
        resultat = repetition.CONTROLES[8]()
    assert resultat.reussie is True, resultat.detail
    assert "Je ne trouve pas cet objet" in resultat.detail and "humain" in resultat.detail
    assert "0 geste" in resultat.detail and resultat.etiquette == "SIMULÉ"  # aucun robot n'a servi : on ne dit pas FAUX ROBOT


def test_sans_changement_les_etapes_jouent_le_scenario_du_cahier():
    assert repetition.VARIATION is None
    un, sept = repetition.CONTROLES[1](), repetition.CONTROLES[7]()
    assert "(it)" in un.detail and "la sonnette" in sept.detail


def test_le_changement_ne_deborde_pas_apres_l_essai():
    with repetition.variation({"langue": "de"}):
        assert repetition.VARIATION["langue"] == "de"
    assert repetition.VARIATION is None


# ---------------------------------------------------------------------------------------------- le tableau
def test_le_tableau_dit_reussie_tant_de_fois_sur_vingt_avec_l_etiquette(tmp_path):
    bilan, lignes = _jouer(_faux_controles(), tmp_path)
    tableau = [l for l in lignes if re.match(r"\s*\d+\. ", l)]
    assert len(tableau) == 14 and all("réussie 20 fois sur 20" in l for l in tableau)
    assert "[FAUX ROBOT]" in tableau[7] and "[SIMULÉ]" in tableau[0]
    assert bilan["essais"] == 20 and bilan["echecs"] == [] and bilan["code"] == 0
    assert any(l.startswith("ESSAIS COMPTÉS : 20 essais") for l in lignes)
    assert any("Aucun échec" in l for l in lignes)


def test_une_piece_cassee_expres_le_tableau_montre_l_echec_avec_son_heure(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def cassee_parfois():
        appels["n"] += 1
        if appels["n"] in (3, 11):
            raise RuntimeError("pièce cassée exprès")
        return repetition.Resultat(True, "SIMULÉ", "essai")

    controles[4] = cassee_parfois
    bilan, lignes = _jouer(controles, tmp_path)
    ligne_4 = next(l for l in lignes if re.match(r"\s*4\. ", l))
    assert "réussie 18 fois sur 20" in ligne_4
    assert [(e["essai"], e["etape"]) for e in bilan["echecs"]] == [(3, 4), (11, 4)]
    echecs = [l for l in lignes if l.startswith("  - essai ")]
    assert len(echecs) == 2 and "essai 3, étape 4" in echecs[0] and "pièce cassée exprès" in echecs[0]
    assert re.search(r"heure dans la boîte noire : \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", echecs[0])
    assert bilan["code"] == 1
    # l'heure affichée est bien celle de l'événement écrit dans la boîte noire
    notes = [e for e in lire(bilan["boite_noire"]) if e.type == "note" and e.donnees.get("quoi") == "etape_d_un_essai"]
    assert len(notes) == 20 * 14
    rates = [e for e in notes if e.donnees["issue"] != "reussie"]
    assert [(e.donnees["essai"], e.donnees["etape"]) for e in rates] == [(3, 4), (11, 4)]
    assert str(rates[0].heure)[:19].replace(" ", "T") in echecs[0]


def test_un_echec_n_est_ni_efface_ni_rejoue(tmp_path):
    controles = _faux_controles()
    appels = {"n": 0}

    def rate_une_fois():
        appels["n"] += 1
        return repetition.Resultat(appels["n"] != 5, "SIMULÉ", "raté à l'essai 5")

    controles[2] = rate_une_fois
    bilan, _ = _jouer(controles, tmp_path)
    assert appels["n"] == 20  # jouée vingt fois, pas une de plus : pas de deuxième chance
    assert [(e["essai"], e["etape"]) for e in bilan["echecs"]] == [(5, 2)]


def test_une_etape_sans_piece_s_affiche_pas_encore_construite(tmp_path):
    controles = _faux_controles()
    del controles[12]
    bilan, lignes = _jouer(controles, tmp_path)
    ligne = next(l for l in lignes if re.match(r"\s*12\. ", l))
    assert "pas encore construite" in ligne and "sur 20" not in ligne
    assert bilan["code"] == 1


def test_la_fiche_dit_le_cerveau_l_etiquette_la_date_et_les_changements(tmp_path):
    bilan, lignes = _jouer(_faux_controles(), tmp_path)
    texte = "\n".join(lignes)
    assert "FAUX ROBOT" in lignes[0] and re.search(r"\d\d\.\d\d\.\d{4}", lignes[0])
    assert "Cerveau : aucun modèle" in texte
    assert "aucun vrai robot" in texte
    assert "cerveau plus lent" in texte and "sans effet" in texte  # dit vrai : aucune pièce n'appelle encore le cerveau
    assert bilan["fiche"]["etiquette"] == "FAUX ROBOT" and bilan["fiche"]["cerveau"].startswith("aucun modèle")
    assert bilan["fiche"]["par_etape"][8] == {"reussies": 20, "essais": 20, "etiquettes": ["FAUX ROBOT"], "construite": True}


def test_on_peut_jouer_moins_d_essais_et_le_tableau_le_dit(tmp_path):
    bilan, lignes = _jouer(_faux_controles(), tmp_path, liste=essais.charger()[:3])
    assert all("sur 3" in l for l in lignes if re.match(r"\s*\d+\. ", l))
    assert any("3 essais" in l and "sur les 20 de la liste" in l for l in lignes)


def test_la_commande_est_dans_lancer_et_l_option_apertus_dit_vrai(capsys):
    from pathlib import Path

    assert '"essais"' in (Path(__file__).resolve().parents[3] / "lancer.py").read_text(encoding="utf-8")
    code = essais.main(["--apertus"])
    assert code == 2 and "pas encore" in capsys.readouterr().out


def test_deux_essais_de_la_liste_avec_les_vraies_pieces_qui_changent(tmp_path):
    """Les essais 2 et 4 de la liste, par les VRAIES pièces des étapes qui changent (1, 7, 8) : un objet précis à
    livrer sur le faux robot, puis un objet absent. Les autres étapes sont de faux contrôles ici, pour rester court :
    les vingt essais entiers se jouent par la commande « python3 lancer.py essais » (longue, hors vérification rapide)."""
    liste = [e for e in essais.charger() if e["numero"] in (2, 4)]
    assert [(e["langue"], e["objet_absent"]) for e in liste] == [("de", False), ("en", True)]
    controles = _faux_controles()
    for numero in (1, 7, 8):
        controles[numero] = repetition.CONTROLES[numero]
    bilan, lignes = _jouer(controles, tmp_path, liste=liste)
    assert bilan["echecs"] == [], "\n".join(lignes)
    assert all("réussie 2 fois sur 2" in l for l in lignes if re.match(r"\s*\d+\. ", l))
    huit = next(l for l in lignes if re.match(r"\s*8\. ", l))
    assert "[FAUX ROBOT, SIMULÉ]" in huit  # un essai sur faux robot, un essai sans robot : les deux étiquettes sont dites
    notes = {(e.donnees["essai"], e.donnees["etape"]): e.donnees for e in lire(bilan["boite_noire"])
             if e.type == "note" and e.donnees.get("quoi") == "etape_d_un_essai"}
    assert "Guten Tag" in notes[(2, 1)]["ligne"] and "Hello" in notes[(4, 1)]["ligne"]
    assert "la présentation" in notes[(2, 7)]["ligne"] and "le bracelet" in notes[(4, 7)]["ligne"]
    assert "couverture" in notes[(2, 8)]["ligne"] and "pas de question" in notes[(2, 8)]["ligne"]
    assert notes[(2, 8)]["etiquette"] == "FAUX ROBOT" and "livrée" in notes[(2, 8)]["ligne"]
    assert notes[(4, 8)]["etiquette"] == "SIMULÉ" and "Je ne trouve pas cet objet" in notes[(4, 8)]["ligne"]
