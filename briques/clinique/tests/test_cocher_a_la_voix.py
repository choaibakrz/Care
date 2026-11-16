"""La clinique en boîte — T16, cocher à la voix, AU NIVEAU DU TEXTE RECONNU (cahier 5.5).

« Fini » veut dire :
- « sonnette, fait » coche le bon point en français, en allemand, en italien et en anglais ;
- une phrase qui peut désigner deux points fait poser une question, et ne coche rien ;
- sans le mot « fait », rien n'est coché ; une phrase mal entendue ne coche rien (on passe au doigt) ;
- les boutons marchent toujours ;
- le carnet dit que le point a été coché « à la voix », avec la phrase entendue.
DIRE VRAI : il n'y a ni micro ni modèle d'écoute sur l'iMac (R4). Ici, la « phrase entendue » est un texte tapé :
c'est la moitié « comprendre la phrase », pas la moitié « entendre ». Aucun vrai son du dépôt ne dit ces phrases.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.listes import ChoixRefuse, ListesDeSoin
from briques.clinique.porte import JournalDesAcces, PorteDeLecture, charger_badges
from conftest import lancer

BADGES = charger_badges()
SOIGNANT = BADGES["soignant-etage-2"]


def _listes():
    return ListesDeSoin(PorteDeLecture(journal=JournalDesAcces()), Carnet())


def _etats(listes, liste="installation"):
    return {p["numero"]: p for p in listes.liste(SOIGNANT, "p01", liste)["points"]}


@pytest.mark.parametrize("phrase, langue", [("sonnette, fait", "français"), ("la sonnette, c'est fait", "français"),
                                            ("Klingel, erledigt", "allemand"), ("Klingel gemacht", "allemand"),
                                            ("campanello, fatto", "italien"), ("bell, done", "anglais"),
                                            ("call button done", "anglais"), ("SONNETTE FAIT.", "français")])
def test_sonnette_fait_coche_le_bon_point_dans_les_quatre_langues(phrase, langue):
    listes = _listes()
    r = listes.entendre(SOIGNANT, "p01", "installation", phrase)
    assert r["compris"] == "coche" and r["point"]["numero"] == 3 and r["point"]["nom"] == "la sonnette", (langue, r)
    etats = _etats(listes)
    assert etats[3]["etat"] == "fait" and etats[3]["comment"] == "à la voix"
    assert [n for n, p in etats.items() if p["etat"] == "fait"] == [3]  # ce point, et lui seul
    ligne = listes.carnet.lignes("point de liste")[-1]
    assert ligne["donnees"]["entendu"] == phrase and ligne["valide_par_un_humain"] is True
    assert "la sonnette" in r["dit"]


@pytest.mark.parametrize("phrase, numero", [("le bracelet, fait", 2), ("lit fait", 4), ("Bett, fertig", 4), ("letto, fatto", 4),
                                            ("walker, done", 6), ("la veilleuse, fait", 5), ("présentation faite", 1)])
def test_les_autres_points_se_cochent_par_leurs_mots_proches(phrase, numero):
    listes = _listes()
    assert listes.entendre(SOIGNANT, "p01", "installation", phrase)["point"]["numero"] == numero


def test_une_phrase_qui_peut_designer_deux_points_fait_poser_une_question_et_ne_coche_rien():
    listes = _listes()
    r = listes.entendre(SOIGNANT, "p01", "installation", "le bracelet et la sonnette, fait")
    assert r["compris"] == "question" and r["dit"] == "Lequel : le bracelet, ou la sonnette ?"
    assert [c["numero"] for c in r["choix"]] == [2, 3]
    assert listes.carnet.lignes("point de liste") == []  # il ne devine pas
    r = listes.entendre(SOIGNANT, "p01", "avant_physio", "bouteille et feuille, fait")
    assert r["compris"] == "question" and not listes.carnet.lignes("point de liste")


@pytest.mark.parametrize("phrase", ["sonnette", "la sonnette ?", "la sonnette n'est pas faite… non", "bonjour", "", "fait",
                                    "le fauteuil, fait", "literie, fait", "pas fait la sonnette"])
def test_sans_point_reconnu_ou_sans_le_mot_fait_rien_n_est_coche(phrase):
    listes = _listes()
    r = listes.entendre(SOIGNANT, "p01", "installation", phrase)
    assert r["compris"] == "rien" and r["dit"], phrase
    assert listes.carnet.lignes("point de liste") == [], phrase


def test_une_phrase_mal_entendue_ne_coche_rien_et_renvoie_au_doigt():
    listes = _listes()
    r = listes.entendre(SOIGNANT, "p01", "installation", "sonnette, fait", confiance=0.3)
    assert r["compris"] == "rien" and "doigt" in r["dit"] and listes.carnet.lignes("point de liste") == []
    r = listes.entendre(SOIGNANT, "p01", "installation", "…", confiance=0.1)
    assert r["compris"] == "rien"


def test_un_point_deja_coche_le_dit_et_ne_compte_pas_deux_fois():
    listes = _listes()
    listes.cocher(SOIGNANT, "p01", "installation", 3)
    r = listes.entendre(SOIGNANT, "p01", "installation", "sonnette, fait")
    assert r["compris"] == "coche" and "déjà" in r["dit"]
    assert len(listes.carnet.lignes("point de liste")) == 1 and _etats(listes)[3]["comment"] == "au doigt"


def test_la_voix_ne_donne_aucun_droit_de_plus_que_le_doigt():
    listes = _listes()
    with pytest.raises(Exception):
        listes.entendre(BADGES["patient-p01"], "p01", "installation", "sonnette, fait")
    with pytest.raises(Exception):
        listes.entendre(BADGES["robot-r1"], "p01", "installation", "sonnette, fait")
    with pytest.raises(ChoixRefuse):  # la liste « sortie » : pas prévue pour cette personne, ou point réservé au médecin
        listes.entendre(SOIGNANT, "p01", "sortie", "la lettre de sortie, fait")
    assert listes.carnet.lignes("point de liste") == []


def test_les_boutons_marchent_toujours():
    listes = _listes()
    listes.cocher(SOIGNANT, "p01", "installation", 1)
    listes.entendre(SOIGNANT, "p01", "installation", "sonnette, fait")
    etats = _etats(listes)
    assert (etats[1]["comment"], etats[3]["comment"]) == ("au doigt", "à la voix")
    assert listes.je_sors(SOIGNANT, "p01")["phrase"].startswith("Il reste 4 points")


# ---------------------------------------------------------------------------------------------- à l'écran
def _client():
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="x")
    return TestClient(app), clinique


def test_la_page_de_liste_a_un_champ_pour_la_phrase_entendue_et_le_dit_simule():
    client, clinique = _client()
    page = client.get("/clinique/soignant/liste", params={"badge": SOIGNANT.id, "patient": "p01", "liste": "installation"}).text
    assert "id='voix'" in page and "SIMULÉ" in page and "pas de micro" in page
    r = client.post("/api/clinique/liste/voix", json={"badge": SOIGNANT.id, "patient": "p01", "liste": "installation",
                                                      "phrase": "campanello, fatto"})
    assert r.status_code == 200 and r.json()["compris"] == "coche" and r.json()["point"]["numero"] == 3
    points = {p["numero"]: p for p in clinique.listes.liste(SOIGNANT, "p01", "installation")["points"]}
    assert points[3]["etat"] == "fait"
    assert client.post("/api/clinique/liste/voix", json={"badge": "patient-p01", "patient": "p01", "liste": "installation",
                                                         "phrase": "bell, done"}).status_code == 403


def test_micro_en_panne_la_phrase_arrive_comme_du_bruit_et_rien_n_est_coche():
    client, clinique = _client()
    lancer(clinique.pannes.provoquer("micro_bruit"))
    r = client.post("/api/clinique/liste/voix", json={"badge": SOIGNANT.id, "patient": "p01", "liste": "installation",
                                                      "phrase": "sonnette, fait"}).json()
    assert r["compris"] == "rien" and "doigt" in r["dit"] and clinique.carnet.lignes("point de liste") == []
    # au doigt, ça marche toujours
    assert client.post("/api/clinique/liste/cocher", json={"badge": SOIGNANT.id, "patient": "p01", "liste": "installation",
                                                           "numero": 3}).status_code == 200
