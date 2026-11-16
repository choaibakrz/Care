"""La clinique en boîte — T28, « À vous » : le jury change le scénario (cahier 4.3).

« Rien ne doit être écrit en dur. Ces trois changements doivent marcher sans toucher au code :
une autre langue à l'arrivée (allemand, français ou anglais) ; un autre point oublié dans la liste ;
un objet absent de la réserve : le robot dit qu'il ne le trouve pas et demande à un humain. »
« Fini quand : les trois changements réussissent, lancés par trois vérifications qui ne touchent pas au code. »
Les trois vérifications lancent la commande `python3 lancer.py a-vous` avec les choix du jury, ou changent le fichier
`a_vous.yaml` : aucune ligne de programme n'est changée. Arrivée tapée (pas de voix), faux robot. Aucun vrai robot.
"""
from __future__ import annotations

import pytest

from briques.clinique import a_vous, repetition


def _lancer(*options, fichier=None):
    lignes: list[str] = []
    code = a_vous.main(list(options), ecrire=lignes.append, fichier=fichier)
    return code, "\n".join(lignes)


# ------------------------------------------------------------------------------------------------ les trois vérifications
@pytest.mark.parametrize("langue, debut", [("de", "Guten Tag"), ("fr", "Bonjour"), ("en", "Hello")])
def test_verification_1_une_autre_langue_a_l_arrivee(langue, debut):
    code, texte = _lancer("--langue", langue)
    assert code == 0, texte
    assert debut in texte and f"({langue})" in texte and "À VOUS : RÉUSSI" in texte
    assert "arrivée tapée" in texte  # dire vrai : pas de voix dans cette commande


@pytest.mark.parametrize("numero", [1, 2, 4, 5, 6])
def test_verification_2_un_autre_point_oublie_dans_la_liste(numero):
    code, texte = _lancer("--point", str(numero))
    assert code == 0, texte
    nom = a_vous.points_de_la_liste()[numero]
    assert f"Il reste un point : {nom}." in texte and "la sonnette." not in texte.split("Il reste un point")[1][:30]


@pytest.mark.parametrize("objet", ["un fauteuil roulant", "une guitare", "le parapluie"])
def test_verification_3_un_objet_absent_de_la_reserve(objet):
    code, texte = _lancer("--objet", objet)
    assert code == 0, texte
    assert "Je ne trouve pas cet objet" in texte and "tâche pour un humain" in texte and "0 geste du robot" in texte
    assert "absent de la réserve" in texte


# ------------------------------------------------------------------------------------------------ autour
def test_les_trois_changements_ensemble_et_rien_ne_deborde():
    code, texte = _lancer("--langue", "en", "--point", "5", "--objet", "une guitare")
    assert code == 0 and texte.count("réussie") >= 3 and "Hello" in texte and "Je ne trouve pas" in texte
    assert repetition.VARIATION is None  # après la commande, le scénario redevient celui du cahier


def test_un_objet_qui_est_dans_la_reserve_est_livre_par_le_faux_robot():
    code, texte = _lancer("--objet", "la couverture")
    assert code == 0, texte
    assert "tâche livrée" in texte and "FAUX ROBOT" in texte and "Je ne trouve pas" not in texte


def test_un_objet_flou_recoit_une_question_puis_est_livre():
    code, texte = _lancer("--objet", "un coussin")
    assert code == 0 and "question : «" in texte and "tâche livrée" in texte, texte


def test_sans_option_la_commande_lit_le_fichier_que_le_jury_peut_changer(tmp_path):
    fichier = tmp_path / "a_vous.yaml"
    fichier.write_text("langue: fr\npoint_oublie: 2\nobjet: une guitare\n", encoding="utf-8")
    code, texte = _lancer(fichier=fichier)
    assert code == 0 and "Bonjour" in texte and f"Il reste un point : {a_vous.points_de_la_liste()[2]}." in texte
    assert "Je ne trouve pas" in texte and "a_vous.yaml" in texte
    assert a_vous.FICHIER.exists() and a_vous.lire_les_choix(a_vous.FICHIER)  # le fichier du dépôt se lit


@pytest.mark.parametrize("options, mot", [(("--langue", "es"), "allemand"), (("--point", "9"), "entre 1 et"),
                                           (("--point", "deux"), "numéro"), (("--objet", "   "), "objet")])
def test_un_choix_impossible_est_refuse_avec_une_phrase_claire_et_rien_n_est_joue(options, mot):
    code, texte = _lancer(*options)
    assert code == 2 and mot in texte and "réussie" not in texte


def test_la_commande_est_dans_lancer():
    import lancer

    assert "a-vous" in lancer.__doc__
