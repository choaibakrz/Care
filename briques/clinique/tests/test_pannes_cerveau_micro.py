"""La clinique en boîte — J02c, les pannes « le cerveau ne répond plus » et « le micro n'entend que du bruit ».

« Fini » veut dire, pour chacune des deux :
- 1. le robot s'arrête (arrêt normal, par la prise) et ne commence rien de nouveau : une demande attend ;
- 2. l'écran dit ce qui se passe, ce que le système fait, qui est prévenu ;
- 3. la boîte noire et le carnet notent le début et la fin ;
- 4. au retour, rien n'est perdu : les coches sont là, la demande en attente repart et est livrée.
Et ce que le système continue de faire sans la pièce absente, il le dit :
- cerveau muet : le médecin garde le résumé préparé AVANT la panne, marqué « peut être vieux » ; les nouveaux papiers
  attendent sans proposition ; les listes se cochent toujours ;
- micro : une phrase mal entendue ne fait rien partir et ne coche rien ; on passe au doigt.
Les quatre pannes de l'avenant sont maintenant construites. Testé sur faux robot. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import pannes as piece
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture
from conftest import lancer

SOIGNANT, MEDECIN, ACCUEIL = "soignant-etage-2", "medecin-exemple", "accueil"


def _clinique(*sauts):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration(temps=lambda: 0.0)
    for saut in sauts:
        asyncio.run(horloge.sauter(saut))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    return TestClient(app), clinique


def test_les_quatre_pannes_de_l_avenant_sont_construites():
    assert all(p["construite"] and p["etiquette"] == "SIMULÉ" for p in piece.PANNES.values())
    assert set(piece.ABRI) == {"lien_robot", "cerveau_muet", "micro_bruit"}


@pytest.mark.parametrize("panne", ["cerveau_muet", "micro_bruit"])
def test_les_quatre_choses_obligatoires_sur_le_faux_robot(panne, tmp_path):
    d = piece.demonstration(panne, tmp_path)
    clinique, demande = d["clinique"], d["demande"]
    assert d["ok"] is True and d["choses"] == {1: True, 2: True, 3: True, 4: True}, "\n".join(d["lignes"])
    # 1. arrêt normal demandé à la prise, puis rien de nouveau : la demande attend, aucun geste, aucune demande au gardien
    assert d["arrets_demandes"] == 1
    assert d["pendant"]["etat"] == "demandée" and d["pendant"]["en_attente"] == piece.ATTENTES[panne]
    assert d["gestes_pendant"] == [] and d["decisions_pendant"] == 0
    # 2. l'écran
    p = piece.PANNES[panne]
    for morceau in (p["ce_qui_se_passe"], p["ce_que_le_systeme_fait"], p["qui_est_prevenu"], "SIMULÉ", "PANNE"):
        assert morceau in d["bandeau"], morceau
    # 3. la boîte noire et le carnet
    assert [(e.donnees["quoi"], e.donnees["etat"]) for e in d["notes"]] == [(panne, "début"), (panne, "fin")]
    assert [l["donnees"]["etat"] for l in clinique.carnet.lignes("panne")] == ["début", "fin"]
    # 4. rien n'est perdu
    assert d["points"][1] == "fait" and d["points"][2] == "fait"
    assert d["retour"]["reparties"] == [demande["id"]]
    assert clinique.taches.tache(demande["id"])["etat"] == "livrée"
    assert d["gestes"] == ["se_deplacer", "saisir", "se_deplacer", "poser"]
    if panne == "micro_bruit":  # une phrase mal entendue pendant la panne : rien n'est parti, rien n'est coché
        assert d["mal_entendu"] == {"texte": "…", "confiance": 0.1, "gestes": 0, "coches_en_plus": 0}
        assert "phrase mal entendue" in "\n".join(d["lignes"])


# ---------------------------------------------------------------------------------------------- le cerveau muet, sans robot
def test_cerveau_muet_le_medecin_garde_le_resume_d_avant_marque_vieux():
    client, clinique = _clinique("le soir", "le lendemain matin")
    medecin, soignant = clinique.badges[MEDECIN], clinique.badges[SOIGNANT]
    avant = clinique.resume.resume(medecin, "p01")
    assert "fige" not in avant
    lancer(clinique.pannes.provoquer("cerveau_muet"))
    clinique.listes.cocher(soignant, "p01", "installation", 1)  # quelque chose change pendant la panne
    pendant = clinique.resume.resume(medecin, "p01")
    assert pendant["lignes"] == avant["lignes"]  # le résumé n'est pas refait
    assert "peut être vieux" in pendant["fige"] and "le cerveau ne répond plus" in pendant["fige"]
    page = client.get("/clinique/medecin", params={"badge": MEDECIN}).text
    assert "préparé avant la panne, il peut être vieux" in page
    lancer(clinique.pannes.finir("cerveau_muet"))
    apres = clinique.resume.resume(medecin, "p01")
    assert "fige" not in apres and apres["lignes"] != avant["lignes"]  # refait, avec la coche
    assert "préparé avant la panne" not in client.get("/clinique/medecin", params={"badge": MEDECIN}).text


def test_cerveau_muet_un_resume_jamais_prepare_le_dit_au_lieu_d_inventer():
    _, clinique = _clinique("le soir", "le lendemain matin")
    lancer(clinique.pannes.provoquer("cerveau_muet"))
    resume = clinique.resume.resume(clinique.badges[MEDECIN], "p03")
    assert resume["lignes"] == [] and "aucun résumé n'était prêt" in resume["fige"]


def test_cerveau_muet_les_nouveaux_papiers_attendent_sans_proposition():
    _, clinique = _clinique()
    accueil = clinique.badges[ACCUEIL]
    lancer(clinique.pannes.provoquer("cerveau_muet"))
    pile = clinique.papiers.pile(accueil)
    assert pile["a_valider"] == [] and len(pile["sans_proposition"]) >= 3
    assert "le cerveau ne répond plus" in pile["dit"]
    assert clinique.carnet.lignes("papier") == []  # rien n'a été proposé ni écrit
    lancer(clinique.pannes.finir("cerveau_muet"))
    pile = clinique.papiers.pile(accueil)
    assert len(pile["a_valider"]) >= 3 and pile["sans_proposition"] == [] and pile["dit"] == ""


# ---------------------------------------------------------------------------------------------- le micro
def test_micro_bruit_ce_que_les_oreilles_rendent():
    _, clinique = _clinique()
    assert clinique.pannes.entendre("sonnette, fait") == ("sonnette, fait", 1.0)
    lancer(clinique.pannes.provoquer("micro_bruit"))
    assert clinique.pannes.entendre("sonnette, fait") == ("…", 0.1)
    lancer(clinique.pannes.finir("micro_bruit"))
    assert clinique.pannes.entendre("sonnette, fait") == ("sonnette, fait", 1.0)


def test_deux_pannes_en_meme_temps_le_robot_attend_la_fin_des_deux():
    _, clinique = _clinique()
    lancer(clinique.pannes.provoquer("cerveau_muet"))
    lancer(clinique.pannes.provoquer("micro_bruit"))
    assert clinique.pannes.a_l_abri() == "cerveau_muet"
    lancer(clinique.pannes.finir("cerveau_muet"))
    assert clinique.pannes.a_l_abri() == "micro_bruit"  # encore à l'abri : rien ne repart
    lancer(clinique.pannes.finir("micro_bruit"))
    assert clinique.pannes.a_l_abri() is None


def test_la_commande_joue_les_trois_pannes_du_robot_et_renvoie_la_tablette_a_sa_page(capsys, monkeypatch):
    joue = {"ok": True, "lignes": ["PANNE : TENUE"]}
    appels = []
    monkeypatch.setattr(piece, "demonstration", lambda ident: appels.append(ident) or joue)
    for ident in piece.ABRI:
        assert piece.main([ident]) == 0
    assert appels == list(piece.ABRI)
    monkeypatch.undo()
    assert piece.main(["lien_tablette"]) == 2 and "/clinique/pannes" in capsys.readouterr().out
