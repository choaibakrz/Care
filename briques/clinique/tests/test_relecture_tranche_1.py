"""La clinique en boîte — T12, la relecture de la tranche 1. Un essai par manque trouvé par le relecteur neuf.

Chaque essai porte le numéro du point du rapport. Internet coupé, aucun modèle.
"""
from __future__ import annotations

import asyncio
import re
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import chef_clinique, repetition
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import AccesRefuse, Badge, JournalDesAcces, PorteDeLecture

MEDECIN, THERAPEUTE, SOIGNANT, ACCUEIL = "medecin-exemple", "therapeute-exemple", "soignant-etage-2", "accueil"
DICTEE = "Physio, évaluer la marche demain."


@pytest.fixture(autouse=True)
def _sans_mesure_de_lecture_sur_cet_ordinateur(monkeypatch, tmp_path):
    """La fiche lit la dernière mesure de lecture des papiers, si cet ordinateur en a une (journal/clinique/). Ces essais
    ne doivent pas dépendre de ce qui a été mesuré ici : ils partent d'un ordinateur sans mesure."""
    from briques.clinique import papiers_images

    monkeypatch.setattr(papiers_images, "FICHIER_MESURE", tmp_path / "pas_de_mesure.json")
    from briques.clinique import ecoute

    monkeypatch.setattr(ecoute, "FICHIER_MESURE", tmp_path / "pas_de_mesure_d_ecoute.json")


def _clinique(*sauts: str):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration(temps=lambda: 0.0)
    for saut in sauts:
        asyncio.run(horloge.sauter(saut))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


def _ok(etiquette="SIMULÉ", **mesures):
    return lambda: repetition.Resultat(True, etiquette, "essai", mesures)


def _controles():
    controles = {n: _ok() for n in range(1, 13)}
    controles[10] = _ok(phrases_retirees=0)  # comme la vraie étape 10 : le résumé donne son compte
    controles[13], controles[14] = repetition.CONTROLES[13], repetition.CONTROLES[14]
    return controles


def _jouer(controles):
    lignes: list[str] = []
    return chef_clinique.jouer(controles, ecrire=lignes.append), lignes


# ------------------------------------------------------------------ point 1 : l'accueil ne lit pas la dictée du médecin
def test_p1_la_dictee_n_est_lue_que_par_le_metier_vise_et_par_le_medecin():
    client, clinique = _clinique()  # jour 1 : l'accueil voit Madame Giulia B. (arrivée du jour)
    client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE})
    for badge in (ACCUEIL, SOIGNANT):
        reponse = client.get("/api/clinique/taches", params={"badge": badge})
        assert "évaluer la marche" not in reponse.text, badge
        assert "évaluer la marche" not in client.get(f"/clinique/{'accueil' if badge == ACCUEIL else 'soignant'}",
                                          params={"badge": badge}).text, badge
    assert "évaluer la marche demain" in client.get("/api/clinique/taches", params={"badge": THERAPEUTE}).text
    assert "évaluer la marche demain" in client.get("/clinique/therapeute", params={"badge": THERAPEUTE}).text
    assert any(t["quoi"] == "évaluer la marche demain" for t in clinique.taches.tableau(clinique.badges[MEDECIN]))


def test_p1_une_demande_d_objet_reste_visible_comme_avant():
    client, clinique = _clinique()
    clinique.taches.demander(clinique.badges[SOIGNANT], "p01", "il manque un grand coussin")
    assert "grand coussin" in client.get("/api/clinique/taches", params={"badge": SOIGNANT}).text


# ------------------------------------------------------------------ point 2 : pas de phrase libre du médecin vers l'accueil
def test_p2_une_dictee_ne_part_jamais_a_l_accueil():
    client, clinique = _clinique()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01",
                                                  "texte": "Accueil, la patiente a mal dormi."}).json()
    assert r["tache"]["pour"] == "soignant" and "pas reconnu" in r["dit"]
    assert "mal dormi" not in client.get("/api/clinique/taches", params={"badge": ACCUEIL}).text
    assert "mal dormi" not in client.get("/api/clinique/taches", params={"badge": THERAPEUTE}).text


# ------------------------------------------------------------------ point 3 : la surveillance du réseau
def test_p3_toutes_les_portes_de_recherche_et_d_envoi_sont_surveillees():
    from briques.clinique.rien_dehors import Surveillance, _en_place

    avant = _en_place()
    assert len(avant) == 9
    with Surveillance() as veille:
        pendant = _en_place()
        assert all(pendant[nom] is not avant[nom] for nom in avant)  # les neuf portes sont remplacées
        for appel in (lambda: socket.gethostbyname("exemple.invalid"), lambda: socket.gethostbyname_ex("exemple.invalid"),
                      lambda: socket.gethostbyaddr("192.0.2.1"), lambda: socket.getnameinfo(("192.0.2.1", 80), 0)):
            with pytest.raises(OSError):
                appel()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s, pytest.raises(OSError):
            s.sendmsg([b"x"], [], 0, ("192.0.2.1", 9))
        assert len(veille.essais) == 5 and veille.intacte()
    apres = _en_place()
    assert all(apres[nom] is avant[nom] for nom in avant)  # tout est remis comme avant


def test_p3_une_piece_qui_retire_la_surveillance_fait_rater_l_etape_14():
    controles = _controles()

    def tricheuse():
        socket.socket.connect = repetition.SEANCE.reseau._avant["connect"]  # elle remet l'ancienne porte
        return repetition.Resultat(True, "SIMULÉ", "une pièce a retiré la surveillance")

    controles[3] = tricheuse
    code, lignes = _jouer(controles)
    ligne = next(l for l in lignes if re.match(r"\s*14\. ", l))
    assert "RATÉE" in ligne and "surveillance" in ligne and code == 1


# ------------------------------------------------------------------ points 4, 5, 11 : la fiche dit ce qu'elle mesure
def test_p4_p5_p11_la_fiche_dit_combien_de_lignes_sont_mesurees_et_de_quelle_horloge_elle_parle():
    code, lignes = _jouer(_controles())
    etape = next(l for l in lignes if re.match(r"\s*13\. ", l))
    assert "5 lignes mesurées sur 7" in etape and "2 « non mesuré »" in etape
    fiche = {l.split(" : ", 1)[0].strip(" ·"): l.split(" : ", 1)[1] for l in lignes if l.startswith("    · ")}
    assert "horloge d'affichage" in fiche["Temps accéléré"] and "chaque pièce a sa propre horloge" in fiche["Temps accéléré"]
    assert "0 étape sur 12" in fiche["Part de l'humain"] and "sur 14" not in fiche["Part de l'humain"]


def test_p4_une_fiche_ou_il_manque_une_ligne_du_cahier_fait_rater_l_etape_13(monkeypatch):
    from briques.clinique import fiche

    vraie = fiche.fiche_de_la_repetition

    def amputee(seance):
        rendu = vraie(seance)
        rendu["lignes"] = [l for l in rendu["lignes"] if l["titre"] != "Robots simulés"]
        return rendu

    monkeypatch.setattr(fiche, "fiche_de_la_repetition", amputee)
    code, lignes = _jouer(_controles())
    assert any(re.match(r"\s*13\. .*RATÉE", l) and "Robots simulés" in l for l in lignes) and code == 1


def test_p11_le_compte_des_robots_vient_du_fichier(tmp_path, monkeypatch):
    from briques.clinique import fiche, flotte

    autre = tmp_path / "flotte.yaml"
    autre.write_text("marque: inventé\nrobots:\n  - {id: robot-r1, nom: R1, carte: Étage, simule: false}\n"
                     "  - {id: robot-r2, nom: R2, carte: Étage, simule: true}\n", encoding="utf-8")
    monkeypatch.setattr(flotte, "FICHIER", autre)
    seance = repetition.Seance()
    lignes = {l["titre"]: l["valeur"] for l in fiche.fiche_de_la_repetition(seance)["lignes"]}
    assert lignes["Robots simulés"].startswith("1 sur 2")


# ------------------------------------------------------------------ point 6 : une tâche que personne ne verrait
def test_p6_une_dictee_pour_un_patient_sans_therapeute_le_dit():
    client, _ = _clinique()
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p05", "texte": DICTEE}).json()
    assert "aucun badge" in r["dit"] and "thérapeute" in r["dit"]
    r = client.post("/api/clinique/dictee", json={"badge": MEDECIN, "patient": "p01", "texte": DICTEE}).json()
    assert "aucun badge" not in r["dit"]


# ------------------------------------------------------------------ point 8 : un robot simulé ne livre jamais
def test_p8_le_tableau_refuse_livree_pour_un_robot_simule():
    _, clinique = _clinique()
    tache = clinique.taches.demander(clinique.badges[SOIGNANT], "p01", "la feuille d'exercices")["tache"]
    clinique.flotte.partir("robot-r3", tache["id"])
    r3 = Badge(id="robot-r3", role="robot", libelle="Robot R3")
    with pytest.raises(AccesRefuse):
        clinique.taches.changer_etat(r3, tache["id"], "livrée")
    assert clinique.taches.tache(tache["id"])["etat"] == "en route"


# ------------------------------------------------------------------ point 10 : le compteur de phrases retirées compte
def test_p10_une_phrase_sans_source_est_retiree_et_comptee(monkeypatch):
    from briques.clinique import resume

    _, clinique = _clinique("le soir", "le lendemain matin")
    vraies = resume.ResumeDuMedecin._phrases

    def avec_une_phrase_sans_source(self, vue, jour):
        phrases = vraies(self, vue, jour)
        phrases["change"].append({"texte": "Phrase glissée exprès, sans source.", "sources": ["source-qui-n-existe-pas"]})
        return phrases

    avant = clinique.resume.resume(clinique.badges[MEDECIN], "p01")["retirees"]
    monkeypatch.setattr(resume.ResumeDuMedecin, "_phrases", avec_une_phrase_sans_source)
    clinique.resume._prets.clear()
    apres = clinique.resume.resume(clinique.badges[MEDECIN], "p01")
    assert avant == 0 and apres["retirees"] == 1
    assert "glissée exprès" not in str(apres["lignes"])


# ------------------------------------------------------------------ points 9 et 12 : les étapes 11 et 12 contrôlent ce qu'elles disent
def test_p9_p12_les_etapes_11_et_12_controlent_ce_qu_elles_annoncent():
    onze, douze = repetition.CONTROLES[11](), repetition.CONTROLES[12]()
    assert onze.reussie and "empreinte du faux dossier inchangée" in onze.detail
    assert douze.reussie and "4 « oui » du gardien, 4 gestes partis" in douze.detail
