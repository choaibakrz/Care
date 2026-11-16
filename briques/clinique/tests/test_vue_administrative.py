"""La clinique en boîte — L03b, le traducteur branché : la porte donne la vue administrative (avenant 4, L03 ; seconde moitié).

« J'admets un patient. Votre robot le sait-il ? » « Fini » veut dire :
- une personne en attente, admise dans le faux logiciel, est connue de l'accueil du hall en moins de dix secondes, avec sa chambre ;
- avant l'admission (et avec une pré-admission seule), le robot appelle un humain ;
- son changement de chambre se voit ; la correction de sa langue change la langue de la réponse ;
- sa sortie la retire des présents ; l'annulation de la sortie la remet ;
- les règles des badges ne changent pas : la direction ne voit aucun nom ; le robot ne voit que le prénom, la langue et le lieu ;
- une personne arrivée par message n'a que de l'administratif : « dossier de soins : rien pour ce patient » ;
- l'écran de l'accueil affiche l'heure de la dernière nouvelle reçue ; la page du faux logiciel affiche le délai de lecture ;
- sans aucun message, les écrans montrent les mêmes patients et les mêmes données qu'avant.
"""
from __future__ import annotations

import html

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans, lire_ecran
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import AccesRefuse, JournalDesAcces, PorteDeLecture
from commun.bus import Bus

CODE = {"X-Code-Equipe": "code-d-essai"}


@pytest.fixture
def banc(tmp_path):
    bus = Bus()
    horloge, app = HorlogeDeDemonstration(bus=bus), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.faux_logiciel.dossier = tmp_path / "faux_logiciel"  # jamais le vrai dossier du journal
    clinique.faux_logiciel.remettre_a_zero()
    return TestClient(app), clinique, bus


def _evenement(client, sorte, numero="p13", **plus):
    r = client.post("/api/faux-logiciel/evenement", json={"sorte": sorte, "numero_patient": numero, **plus}, headers=CODE)
    assert r.status_code == 200, r.text
    return r.json()["message"]


def _ecran(clinique, ecran, badge):
    return lire_ecran(clinique, ecran, clinique.badges[badge])


def _ids(vue):
    return [p["id"] for p in vue["donnees"]["patients"]]


# ---------------------------------------------------------------------------------------------- sans message, rien ne change
def test_sans_aucun_message_les_ecrans_montrent_les_memes_patients_qu_avant(banc):
    _, clinique, _ = banc
    nue = PorteDeLecture(journal=JournalDesAcces(), jour=clinique.horloge.jour)  # une porte sans la vue administrative
    for nom, badge in clinique.badges.items():
        try:
            attendu = nue.patients(badge)
        except AccesRefuse:
            with pytest.raises(AccesRefuse):
                clinique.porte.patients(badge)
            continue
        assert clinique.porte.patients(badge) == attendu, nom
    assert clinique.porte.arrivees_pour_le_hall(clinique.badges["robot-r1"]) == nue.arrivees_pour_le_hall(clinique.badges["robot-r1"])
    assert clinique.porte.comptes(clinique.badges["direction"]) == nue.comptes(clinique.badges["direction"])


# ---------------------------------------------------------------------------------------------- l'accueil du hall
def test_avant_l_admission_le_robot_appelle_un_humain_puis_il_connait_la_personne(banc):
    client, clinique, _ = banc
    avant = clinique.accueil.entendre("Buongiorno, sono Paolo V.")
    assert avant["cas"] == "inconnu" and avant["appel"]  # notre système ne la connaît pas : un humain vient
    _evenement(client, "A05")
    attendue = clinique.accueil.entendre("Buongiorno, sono Paolo V.")
    assert attendue["cas"] == "inconnu" and attendue["appel"]  # une pré-admission seule ne suffit pas
    _evenement(client, "A01", chambre="11")
    apres = clinique.accueil.entendre("Buongiorno, sono Paolo V.")
    assert apres["cas"] == "arrivée" and apres["chambre"] == 11 and apres["etage"] == 2 and apres["langue"] == "it"
    assert "numero 11" in apres["dit"] and apres["premiere_heure"] is None
    assert "programma" not in apres["dit"].lower()  # pas de programme : le robot n'en dit rien
    assert 0 <= clinique.lecteur_admin().dernier_delai_s() < 10  # connue en moins de dix secondes
    assert [pas["lieu"] for pas in apres["chemin"]][-1] == "Chambre 11"


def test_le_changement_de_chambre_se_voit(banc):
    client, clinique, _ = banc
    _evenement(client, "A01", chambre="11")
    _evenement(client, "A02", chambre="13")
    assert clinique.accueil.entendre("Buongiorno, sono Paolo V.")["chambre"] == 13
    assert next(p for p in _ecran(clinique, "soignant", "soignant-etage-2")["donnees"]["patients"] if p["id"] == "p13")["chambre"] == 13


def test_la_correction_de_sa_langue_change_la_langue_de_la_reponse(banc):
    client, clinique, _ = banc
    _evenement(client, "A01", chambre="11")
    assert clinique.accueil.entendre("Paolo V.")["langue"] == "it"  # un nom seul : la langue de sa fiche administrative
    _evenement(client, "A08", champ="langue", valeur="de")
    reponse = clinique.accueil.entendre("Paolo V.")
    assert reponse["langue"] == "de" and "Zimmer" in reponse["dit"]


def test_sa_sortie_la_retire_des_presents_et_l_annulation_la_remet(banc):
    client, clinique, _ = banc
    _evenement(client, "A01", chambre="12")
    assert "p13" in _ids(_ecran(clinique, "soignant", "soignant-etage-2"))
    _evenement(client, "A03")
    assert "p13" not in _ids(_ecran(clinique, "soignant", "soignant-etage-2"))
    assert clinique.accueil.entendre("Buongiorno, sono Paolo V.")["cas"] == "inconnu"
    _evenement(client, "A13")
    assert "p13" in _ids(_ecran(clinique, "soignant", "soignant-etage-2"))
    assert clinique.accueil.entendre("Buongiorno, sono Paolo V.")["cas"] == "arrivée"


# ---------------------------------------------------------------------------------------------- les badges ne changent pas
def test_chaque_badge_voit_la_meme_sorte_de_choses_que_pour_les_autres(banc):
    client, clinique, _ = banc
    _evenement(client, "A01", chambre="11")
    porte, badges = clinique.porte, clinique.badges
    robot = next(p for p in porte.patients(badges["robot-r1"]) if p["id"] == "p13")
    assert robot == {"id": "p13", "prenom": "Paolo", "langue": "it", "chambre": 11, "etage": 2}  # prénom, langue, lieu
    with pytest.raises(AccesRefuse):
        porte.patients(badges["direction"])  # la direction ne voit aucun nom
    comptes = porte.comptes(badges["direction"])
    assert "Paolo" not in str(comptes) and sum(e["patients"] for e in comptes["etages"]) == 13
    assert "p13" not in [p["id"] for p in porte.patients(badges["medecin-exemple"])]  # pas dans la liste de ce médecin
    assert "p13" not in [p["id"] for p in porte.patients(badges["patient-p01"])]
    accueil = next(p for p in porte.patients(badges["accueil"]) if p["id"] == "p13")
    assert accueil["nom"] == "Monsieur Paolo V." and "habitudes" not in accueil and "raison" not in accueil
    soignant = next(p for p in porte.patients(badges["soignant-etage-2"]) if p["id"] == "p13")
    assert set(soignant) - {"dossier_de_soins"} == set(porte.patients(badges["soignant-etage-2"])[0]) - {"dossier_de_soins"}


def test_une_personne_arrivee_par_message_n_a_que_de_l_administratif(banc):
    client, clinique, _ = banc
    _evenement(client, "A01", chambre="11")
    soignant = next(p for p in clinique.porte.patients(clinique.badges["soignant-etage-2"]) if p["id"] == "p13")
    assert soignant["dossier_de_soins"] == "rien pour ce patient"
    assert soignant["habitudes"] == [] and soignant["listes"] == [] and soignant["documents"] == [] and soignant["programme"] == []
    page = html.unescape(client.get("/clinique/soignant?badge=soignant-etage-2").text)
    assert "Monsieur Paolo V." in page and "dossier de soins : rien pour ce patient" in page
    giulia = next(p for p in clinique.porte.patients(clinique.badges["soignant-etage-2"]) if p["id"] == "p01")
    assert "dossier_de_soins" not in giulia and giulia["habitudes"]  # les autres n'ont pas changé


def test_un_message_sur_une_personne_du_faux_dossier_ne_change_pas_sa_fiche(banc, tmp_path):
    client, clinique, _ = banc
    message = _evenement(client, "A01", chambre="14")
    from pathlib import Path
    faux = Path(message["fichier"])  # un message fabriqué qui parle de p01 : le faux dossier garde la main
    faux.with_name("0002_A01_p01.hl7").write_text(faux.read_text(encoding="utf-8").replace("p13^^^", "p01^^^").replace("|s13|", "|s01|")
                                                  .replace("-000001|", "-000777|"), encoding="utf-8")
    giulia = [p for p in clinique.porte.patients(clinique.badges["soignant-etage-2"]) if p["id"] == "p01"]
    assert len(giulia) == 1 and giulia[0]["chambre"] == 12 and giulia[0]["nom"] == "Madame Giulia B."


# ---------------------------------------------------------------------------------------------- ce qui se voit
def test_l_ecran_de_l_accueil_affiche_l_heure_de_la_derniere_nouvelle(banc):
    client, clinique, _ = banc
    avant = html.unescape(client.get("/clinique/accueil").text)
    assert "Logiciel administratif (SIMULÉ) : aucune nouvelle reçue" in avant
    _evenement(client, "A01", chambre="11")
    apres = html.unescape(client.get("/clinique/accueil").text)
    etat = clinique.horloge.etat()
    assert f"Logiciel administratif (SIMULÉ) : dernière nouvelle reçue à {etat['heure']}" in apres and "jour 1" in apres
    assert "Monsieur Paolo V." in apres  # l'arrivée du jour, venue par message


def test_la_page_du_faux_logiciel_affiche_le_delai_de_lecture(banc):
    client, _, _ = banc
    assert "aucun message lu [SIMULÉ]" in html.unescape(client.get("/faux-logiciel", headers=CODE).text)
    _evenement(client, "A01", chambre="11")
    page = html.unescape(client.get("/faux-logiciel", headers=CODE).text)
    assert "dernier message lu en 0," in page and "secondes [SIMULÉ]" in page
    assert "messages lus : 1 ; messages à trier : 0" in page


def test_chaque_message_lu_est_dans_la_boite_noire(banc):
    client, _, bus = banc
    _evenement(client, "A01", chambre="11")
    _evenement(client, "A02", chambre="12")
    lus = [e.donnees for e in bus.historique if e.type == "note" and e.donnees.get("quoi") == "message_lu"]
    assert [(n["sorte"], n["issue"], n["etiquette"]) for n in lus] == [("A01", "lu", "SIMULÉ"), ("A02", "lu", "SIMULÉ")]


def test_ouvrir_l_assistant_montre_la_personne_admise_et_controle_le_sejour(banc):
    client, _, _ = banc
    _evenement(client, "A01", chambre="11")
    bon = html.unescape(client.get("/clinique/ouvrir?patient=p13&sejour=s13&badge=soignant-etage-2").text)
    assert "Monsieur Paolo V." in bon and "dossier de soins : rien pour ce patient" in bon
    faux = html.unescape(client.get("/clinique/ouvrir?patient=p13&sejour=s99&badge=soignant-etage-2").text)
    assert "Paolo" not in faux and "refus" in faux.lower()


def test_remettre_le_faux_logiciel_a_zero_vide_aussi_la_vue(banc):
    client, clinique, _ = banc
    _evenement(client, "A01", chambre="11")
    assert "p13" in _ids(_ecran(clinique, "soignant", "soignant-etage-2"))
    client.post("/api/faux-logiciel/zero", headers=CODE)
    assert "p13" not in _ids(_ecran(clinique, "soignant", "soignant-etage-2"))
    assert clinique.accueil.entendre("Buongiorno, sono Paolo V.")["cas"] == "inconnu"
