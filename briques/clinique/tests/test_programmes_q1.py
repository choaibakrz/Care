"""Les programmes pour le PrimeBot Q1, à coller à la main (15.11.2026).

NON TESTÉ SUR VRAI ROBOT par notre système. « Fini » veut dire :
- pour une phrase, le programme écrit est EXACTEMENT celui que l'équipe a vu marcher (« boulangerie ») ;
- plusieurs phrases s'enchaînent, dans l'ordre, et il n'y a JAMAIS d'autre bloc que « dire » ;
- un texte vide, trop long, trop de phrases, un nom bizarre : refusé, rien n'est écrit ;
- la pièce n'envoie rien : elle n'importe aucun outil de réseau.
- le geste « fist bump » : le programme écrit est EXACTEMENT celui que l'équipe a exporté ; un geste dont l'équipe n'a
  pas exporté le code est refusé (on n'invente pas un code).
"""
import json
from pathlib import Path

import pytest

from briques.clinique import programmes_q1
from briques.clinique.programmes_q1 import ProgrammeRefuse, en_texte, programme, programme_parole

VU_SUR_LE_ROBOT = ('{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"boulangerie","robotTarget":"q1",'
                   '"updatedAt":1794768936292,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_tts",'
                   '"id":"tts1","x":90,"y":130,"inputs":{"TEXT":{"shadow":{"type":"text","id":"txt1","fields":'
                   '{"TEXT":"boulangerie"}}}}}]}}}}')


def test_pour_une_phrase_c_est_exactement_le_programme_vu_sur_le_robot():
    assert en_texte(programme_parole(["boulangerie"], "boulangerie")) == VU_SUR_LE_ROBOT  # au caractère près


def test_plusieurs_phrases_s_enchainent_et_il_n_y_a_que_des_blocs_dire():
    programme = programme_parole(["Buongiorno.", "Sono qui.", "A presto."], "bonjour")
    bloc, textes, types = programme["canvas"]["workspace"]["blocks"]["blocks"][0], [], set()
    while bloc:
        types.add(bloc["type"])
        textes.append(bloc["inputs"]["TEXT"]["shadow"]["fields"]["TEXT"])
        bloc = (bloc.get("next") or {}).get("block")
    assert textes == ["Buongiorno.", "Sono qui.", "A presto."] and types == {"q1_tts"}
    assert len(programme["canvas"]["workspace"]["blocks"]["blocks"]) == 1 and programme["canvas"]["robotTarget"] == "q1"


@pytest.mark.parametrize("phrases, nom", [([], "a"), ([""], "a"), (["   "], "a"), (["x" * 201], "a"), (["a"] * 61, "a"),
                                          ([3], "a"), ("bonjour", "a"), (["bon\njour"], "a"), (["a"], "Nom Bizarre"),
                                          (["a"], ""), (["a"], "x" * 31)])
def test_ce_qui_sort_du_cadre_est_refuse(phrases, nom):
    with pytest.raises(ProgrammeRefuse):
        programme_parole(phrases, nom)


def test_la_commande_ecrit_un_fichier_et_dit_qu_il_faut_coller_a_la_main(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(programmes_q1, "DOSSIER", tmp_path)
    assert programmes_q1.main(["--nom", "bonjour", "Buongiorno."]) == 0
    assert json.loads((tmp_path / "bonjour.json").read_text(encoding="utf-8"))["canvas"]["name"] == "bonjour"
    assert "À COLLER À LA MAIN" in capsys.readouterr().out
    assert programmes_q1.main(["--nom", "vide", ""]) == 2 and not (tmp_path / "vide.json").exists()


def test_la_piece_n_envoie_rien_au_robot():
    code = Path(programmes_q1.__file__).read_text(encoding="utf-8")
    for interdit in ("import socket", "urllib", "requests", "http.client", "subprocess", "bluetooth"):
        assert interdit not in code, interdit
    assert "NON TESTÉ SUR VRAI ROBOT" in code


VU_FIST_BUMP = ('{"schemaVersion":1,"type":"qy_blockly_canvas","canvas":{"name":"fist bump","robotTarget":"q1",'
                '"updatedAt":1794769897822,"workspace":{"blocks":{"languageVersion":0,"blocks":[{"type":"q1_action",'
                '"id":"act1","x":150,"y":150,"fields":{"ACTION_CODE":"3003"}}]}}}}')


def test_le_geste_fist_bump_est_exactement_le_programme_exporte_par_l_equipe():
    assert en_texte(programme(["geste:fist_bump"], "fist bump", 1794769897822)) == VU_FIST_BUMP  # au caractère près


def test_une_phrase_puis_un_geste_s_enchainent():
    premier = programme(["Hello.", "geste:fist_bump"], "salut")["canvas"]["workspace"]["blocks"]["blocks"][0]
    assert premier["type"] == "q1_tts" and (premier["x"], premier["y"]) == (90, 130)
    suivant = premier["next"]["block"]
    assert suivant == {"type": "q1_action", "id": "act1", "fields": {"ACTION_CODE": "3003"}}


@pytest.mark.parametrize("etape", ["geste:danse", "geste:3003", "geste:", "geste:9999", "geste:Fist_Bump", "geste:salto",
                                   "geste:marcher", "geste:danse_d"])
def test_un_geste_qui_n_est_pas_dans_la_liste_est_refuse(etape):
    with pytest.raises(ProgrammeRefuse):
        programme([etape], "a")


def test_le_programme_de_parole_refuse_un_geste_et_aucun_code_n_est_invente():
    with pytest.raises(ProgrammeRefuse):
        programme_parole(["geste:fist_bump"], "a")
    # Les seize numéros lus dans le kit du fabricant (McPresetMotion.msg, partie « Q »), et aucun autre.
    assert sorted(programmes_q1.GESTES_CONNUS.values()) == ["3001", "3002", "3003", "3004", "3005", "3007", "3008", "3010",
                                                           "3012", "3013", "3014", "3018", "3021", "3046", "3047", "3048"]
    assert programmes_q1.GESTES_CONNUS["fist_bump"] == "3003" and programmes_q1.GESTES_VUS_MARCHER == {"fist_bump"}


def test_une_danse_s_ecrit_avec_le_numero_du_fabricant():
    bloc = programme(["geste:danse_a"], "danse")["canvas"]["workspace"]["blocks"]["blocks"][0]
    assert bloc == {"type": "q1_action", "id": "act1", "x": 150, "y": 150, "fields": {"ACTION_CODE": "3046"}}


def test_la_commande_ecrit_le_geste_dans_un_fichier_sans_espace(tmp_path, monkeypatch):
    monkeypatch.setattr(programmes_q1, "DOSSIER", tmp_path)
    assert programmes_q1.main(["--nom", "fist bump", "geste:fist_bump"]) == 0
    assert json.loads((tmp_path / "fist_bump.json").read_text(encoding="utf-8"))["canvas"]["name"] == "fist bump"
    assert programmes_q1.main(["--nom", "x", "geste:salto"]) == 2 and not (tmp_path / "x.json").exists()


def test_dire_geste_attendre_s_enchainent_comme_dans_le_programme_que_l_equipe_a_vu_marcher():
    """L'équipe a réglé l'essai dans l'application le 15.11.2026 : dire, geste, attendre 5 s, dire, geste, attendre…"""
    bloc = programme(["Hello.", "geste:faire_signe", "attendre:5", "Thank you!"], "essai")["canvas"]["workspace"]["blocks"]["blocks"][0]
    types, attente = [], None
    while bloc:
        types.append(bloc["type"])
        if bloc["type"] == "wait_last_motion_completion":
            attente = bloc
        bloc = (bloc.get("next") or {}).get("block")
    assert types == ["q1_tts", "q1_action", "wait_last_motion_completion", "q1_tts"]
    assert {k: v for k, v in attente.items() if k != "next"} == {"type": "wait_last_motion_completion", "id": "wait1",
                                                                 "fields": {"TIMEOUT_SECONDS": "5"}}


@pytest.mark.parametrize("etape", ["attendre:0", "attendre:61", "attendre:", "attendre:cinq", "attendre:-3", "attendre:2.5"])
def test_une_attente_hors_du_cadre_est_refusee(etape):
    with pytest.raises(ProgrammeRefuse):
        programme(["Hello.", etape], "a")
