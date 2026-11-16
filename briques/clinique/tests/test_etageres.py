"""La clinique en boîte — M02, l'épreuve des étagères : dix minutes, tout est compté (avenant 3).

« Fini » veut dire (avec un fichier d'essai, jamais le vrai fichier de l'équipe) :
- deux objets du haut, un du milieu, un du bas et un objet tombé donnent 25 points ;
- un appui sur « J'ai aidé » fait compter l'objet suivant « avec aide », et la ligne de résultat dit « aides : 1 » ;
- avec « une personne » aux commandes, tous les objets comptent « avec aide », étiquette « RÉEL · TÉLÉCOMMANDÉ » ;
- avec une heure d'essai, un appui fait après dix minutes est refusé ;
- un appui annulé ne compte plus, mais reste écrit ;
- en mode « porteur », aucun point ne s'affiche ;
- le fichier d'essai effacé, la page redit « RÉEL : aucun essai compté » ;
- `docs/projet/EPREUVE_ETAGERES.md` tient sur une page.
Les vérifications de J01 et de K02 ne sont pas changées.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import etageres
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.essais_reels import CompteurReel
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

RACINE = Path(__file__).resolve().parents[3]
CODE = {"X-Code-Equipe": "code-d-essai"}


class Montre:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def banc(tmp_path):
    montre = Montre()
    compteur = CompteurReel(tmp_path / "essais_reels_d_essai.jsonl")
    return etageres.Epreuve(compteur, montre=montre), compteur, montre


def _lignes(compteur):
    return [json.loads(l) for l in compteur.fichier.read_text(encoding="utf-8").splitlines()]


def _depart(epreuve, pilote="robot", saisit=True):
    return epreuve.depart(carte="robot d'essai", pilote=pilote, saisit=saisit, note="salle d'essai")


# ---------------------------------------------------------------------------------------------- le score
def test_deux_du_haut_un_du_milieu_un_du_bas_et_un_tombe_donnent_25_points(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve)
    for appui in ("haut", "haut", "milieu", "bas", "tombé"):
        epreuve.appui(appui)
    etat = epreuve.etat()
    assert etat["score"] == 25 and etat["par_niveau"] == {"haut": 2, "milieu": 1, "bas": 1} and etat["tombes"] == 1
    essais = compteur.lignes()
    assert [(l["geste"], l["resultat"]) for l in essais] == [("étagères, haut", "réussi"), ("étagères, haut", "réussi"),
                                                            ("étagères, milieu", "réussi"), ("étagères, bas", "réussi"),
                                                            ("étagères, tombé en route", "raté")]
    assert all(l["etiquette"] == "RÉEL" and l["quand"] for l in essais)
    assert compteur.resume()["texte"] == "RÉEL : 4 sur 5" and compteur.resume()["illisibles"] == 0


def test_la_ligne_de_resultat_est_complete_jamais_le_score_seul(banc):
    epreuve, _, _ = banc
    _depart(epreuve)
    for appui in ("haut", "bas", "tombé"):
        epreuve.appui(appui)
    ligne = epreuve.resultat()
    for mot in ("score : 12", "haut : 1", "milieu : 0", "bas : 1", "tombés : 1", "aides : 0", "le robot tout seul",
                "robot d'essai", "[RÉEL]"):
        assert mot in ligne, mot
    assert epreuve.etat()["avertissement"] == "Ce score ne se compare qu'à nos propres essais."


# ---------------------------------------------------------------------------------------------- l'aide
def test_j_ai_aide_fait_compter_l_objet_suivant_avec_aide(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve)
    epreuve.appui("haut")
    epreuve.appui("aide")
    epreuve.appui("milieu")
    epreuve.appui("bas")
    assert [l["resultat"] for l in compteur.lignes()] == ["réussi", "réussi avec aide", "réussi"]
    assert "aides : 1" in epreuve.resultat() and epreuve.etat()["score"] == 23
    assert compteur.resume()["texte"] == "RÉEL : 2 sur 3 ; réussis avec aide : 1 sur 3"


def test_avec_une_personne_aux_commandes_tout_compte_avec_aide_et_c_est_telecommande(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve, pilote="personne")
    epreuve.appui("haut")
    epreuve.appui("bas")
    assert [l["resultat"] for l in compteur.lignes()] == ["réussi avec aide", "réussi avec aide"]
    assert all(l["etiquette"] == "RÉEL · TÉLÉCOMMANDÉ" for l in compteur.lignes())
    assert "[RÉEL · TÉLÉCOMMANDÉ]" in epreuve.resultat() and "une personne" in epreuve.resultat()


# ---------------------------------------------------------------------------------------------- dix minutes
def test_un_appui_apres_dix_minutes_est_refuse(banc):
    epreuve, compteur, montre = banc
    _depart(epreuve)
    montre.t += 599
    epreuve.appui("haut")
    assert epreuve.etat()["reste_s"] == 1 and not epreuve.etat()["fini"]
    montre.t += 2
    with pytest.raises(etageres.Refus, match="dix minutes"):
        epreuve.appui("bas")
    assert epreuve.etat()["fini"] and epreuve.etat()["score"] == 5 and len(compteur.lignes()) == 1
    with pytest.raises(etageres.Refus):
        epreuve.annuler_le_dernier()  # l'essai est fini : plus rien ne change


def test_le_temps_est_la_vraie_heure_pas_l_horloge_de_demonstration():
    import time

    assert etageres.Epreuve(CompteurReel(Path("/nulle/part.jsonl"))).montre is time.time
    assert etageres.DUREE_S == 600


def test_un_arret_de_securite_finit_l_essai_et_s_ecrit_avec_son_heure_et_sa_note(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve)
    epreuve.appui("milieu")
    epreuve.appui("arrêt", note="le robot penche")
    with pytest.raises(etageres.Refus, match="fini"):
        epreuve.appui("haut")
    arret = [l for l in _lignes(compteur) if l.get("evenement") == "arrêt de sécurité"]
    assert len(arret) == 1 and arret[0]["note"] == "le robot penche" and arret[0]["quand"]
    assert epreuve.etat()["score"] == 8 and "arrêt de sécurité : le robot penche" in epreuve.resultat()


def test_sans_depart_un_appui_est_refuse_et_un_deuxieme_depart_aussi(banc):
    epreuve, _, _ = banc
    with pytest.raises(etageres.Refus, match="Départ"):
        epreuve.appui("haut")
    _depart(epreuve)
    with pytest.raises(etageres.Refus, match="en cours"):
        _depart(epreuve)
    with pytest.raises(etageres.Refus):
        epreuve.appui("plafond")


# ---------------------------------------------------------------------------------------------- annuler
def test_un_appui_annule_ne_compte_plus_mais_reste_ecrit(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve)
    epreuve.appui("haut")
    epreuve.appui("bas")
    epreuve.annuler_le_dernier()
    assert epreuve.etat()["score"] == 5 and epreuve.etat()["par_niveau"]["bas"] == 0
    assert compteur.resume()["texte"] == "RÉEL : 1 sur 1"  # l'essai annulé ne compte plus
    brutes = _lignes(compteur)
    assert sum(1 for l in brutes if l.get("geste") == "étagères, bas") == 1  # l'appui est toujours écrit
    annulations = [l for l in brutes if l.get("evenement") == "annulation"]
    assert len(annulations) == 1 and annulations[0]["annule"] == next(l["id"] for l in brutes if l.get("geste") == "étagères, bas")


def test_annuler_un_j_ai_aide_retire_l_aide(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve)
    epreuve.appui("aide")
    epreuve.annuler_le_dernier()
    epreuve.appui("haut")
    assert compteur.lignes()[0]["resultat"] == "réussi" and "aides : 0" in epreuve.resultat()


# ---------------------------------------------------------------------------------------------- le mode porteur
def test_en_mode_porteur_aucun_point_ne_s_affiche(banc):
    epreuve, compteur, _ = banc
    _depart(epreuve, saisit=False)
    for appui in ("arrivé", "arrivé", "tombé", "aide", "arrivé"):
        epreuve.appui(appui)
    etat = epreuve.etat()
    assert etat["mode"] == "porteur" and etat["score"] is None
    assert etat["trajets"] == 4 and etat["arrives"] == 3 and etat["tombes"] == 1 and etat["aides"] == 1
    ligne = epreuve.resultat()
    assert "score" not in ligne and "point" not in ligne
    for mot in ("trajets : 4", "arrivés : 3", "tombés : 1", "aides : 1"):
        assert mot in ligne, mot
    assert {l["geste"] for l in compteur.lignes()} == {"porter"}
    with pytest.raises(etageres.Refus):
        epreuve.appui("haut")  # pas de niveaux en mode porteur


# ---------------------------------------------------------------------------------------------- la page
def _client(tmp_path):
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.essais_reels.fichier = tmp_path / "essais_reels_d_essai.jsonl"
    return TestClient(app), clinique


def test_la_page_etageres_par_le_serveur(tmp_path):
    client, clinique = _client(tmp_path)
    page = client.get("/clinique/etageres").text.replace("&#x27;", "'")
    for mot in ("RÉEL : aucun essai compté", "Départ", "posé — haut", "posé — milieu", "posé — bas", "tombé", "J'ai aidé",
                "Arrêt de sécurité", "Annuler le dernier appui", "/clinique/epreuve-etageres", "le robot tout seul", "une personne"):
        assert mot in page, mot
    assert "/clinique/etageres" in client.get("/clinique/essais-reels").text  # à côté du compteur d'essais réels
    corps = {"carte": "robot d'essai", "pilote": "robot", "saisit": True, "note": ""}
    assert client.post("/api/clinique/etageres/depart", json=corps).status_code == 403  # sans le code d'équipe
    assert client.post("/api/clinique/etageres/depart", json=corps, headers=CODE).status_code == 200
    for appui in ("haut", "haut", "milieu", "bas", "tombé"):
        r = client.post("/api/clinique/etageres/appui", json={"quoi": appui}, headers=CODE)
        assert r.status_code == 200
    assert r.json()["etat"]["score"] == 25
    assert client.post("/api/clinique/etageres/appui", json={"quoi": "plafond"}, headers=CODE).status_code == 400
    assert client.post("/api/clinique/etageres/annuler", headers=CODE).json()["etat"]["score"] == 28
    etat = client.get("/api/clinique/etageres").json()
    assert etat["etat"]["score"] == 28 and etat["resume"]["texte"] == "RÉEL : 4 sur 4"
    # le fichier d'essai est effacé : la page redit qu'aucun essai n'est compté
    clinique.essais_reels.fichier.unlink()
    assert "RÉEL : aucun essai compté" in client.get("/clinique/etageres/contenu").text


def test_le_protocole_tient_sur_une_page_et_a_ses_treize_points(tmp_path):
    texte = (RACINE / "docs/projet/EPREUVE_ETAGERES.md").read_text(encoding="utf-8")
    for n in range(1, 14):
        assert f"\n{n}. " in texte, n
    for mot in ("le score le plus haut est 69", "5 en haut, 8 au milieu, 10 en bas", "Pour un robot sans bras",
                "Ce score ne se compare qu'à nos propres essais", "Nous reprenons sa façon de compter, pas ses résultats"):
        assert mot in texte, mot
    assert len(texte.splitlines()) <= 40 and len(texte) <= 3600  # une page imprimée
    client, _ = _client(tmp_path)
    assert "Dix minutes, pas une de plus" in client.get("/clinique/epreuve-etageres").text


def test_non_teste_dit_que_la_page_n_a_compte_aucun_essai_sur_un_vrai_robot():
    assert "la page Étagères n'a compté aucun essai sur un vrai robot" in (RACINE / "NON_TESTE.md").read_text(encoding="utf-8")
