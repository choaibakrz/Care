"""La clinique en boîte — J01b, le compteur d'essais réels (avenant jury, J01).

« Fini » veut dire :
- tant que l'équipe n'a rien compté, la fiche affiche « RÉEL : aucun essai compté » ;
- avec un fichier d'essai, le compteur enregistre un « réussi » et un « raté », chacun avec son heure, et la fiche
  affiche « 1 sur 2 » ; puis le fichier d'essai est effacé et la fiche redit « aucun essai compté » ;
- les boutons sont pour l'équipe : sans le code d'équipe, depuis un autre ordinateur, rien ne s'écrit ;
- un essai compté ne s'efface pas et ne se corrige pas : on ajoute, c'est tout ;
- la fiche de vérité de la répétition montre aussi le dernier tableau des essais comptés (FAUX ROBOT, avec sa date).
Ces essais n'écrivent JAMAIS dans le vrai fichier de l'équipe : seulement dans un dossier d'essai.
"""
from __future__ import annotations

import json
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import chef_clinique, essais_reels, fiche, repetition
from briques.clinique.carnet import Carnet
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

CODE = {"X-Code-Equipe": "code-d-essai"}


def _clinique(tmp_path):
    from briques.clinique.ecrans import brancher_ecrans

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.essais_reels.fichier = tmp_path / "essais_reels_d_essai.jsonl"  # jamais le vrai fichier de l'équipe
    return TestClient(app), clinique


def test_le_vrai_fichier_de_l_equipe_n_est_pas_dans_le_depot_et_les_essais_n_y_touchent_pas(tmp_path):
    vrai = essais_reels.FICHIER
    assert vrai.parent.name == "clinique" and vrai.parent.parent.name == "journal"  # journal/ : hors du dépôt envoyé
    avant = vrai.read_bytes() if vrai.exists() else None
    client, clinique = _clinique(tmp_path)
    client.post("/api/clinique/essais_reels", headers=CODE,
                json={"robot": "robot d'essai", "geste": "geste d'essai", "reussi": True, "note": ""})
    assert (vrai.read_bytes() if vrai.exists() else None) == avant


def test_rien_de_compte_la_fiche_dit_aucun_essai_compte(tmp_path):
    compteur = essais_reels.CompteurReel(tmp_path / "vide.jsonl")
    assert compteur.resume()["texte"] == "RÉEL : aucun essai compté"
    client, _ = _clinique(tmp_path)
    page = client.get("/clinique/essais-reels").text
    assert "RÉEL : aucun essai compté" in page and "DONNÉES INVENTÉES" in page


def test_un_reussi_un_rate_la_fiche_dit_1_sur_2_puis_le_fichier_efface_elle_redit_aucun(tmp_path):
    client, clinique = _clinique(tmp_path)
    fichier = clinique.essais_reels.fichier
    r1 = client.post("/api/clinique/essais_reels", headers=CODE,
                     json={"robot": "robot d'essai", "geste": "saisir une bouteille", "reussi": True, "note": "essai"})
    r2 = client.post("/api/clinique/essais_reels", headers=CODE,
                     json={"robot": "robot d'essai", "geste": "saisir une bouteille", "reussi": False, "note": "a glissé"})
    assert r1.status_code == 200 and r2.status_code == 200
    lignes = [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]
    assert [l["resultat"] for l in lignes] == ["réussi", "raté"]
    assert all(re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", l["quand"]) and l["etiquette"] == "RÉEL" for l in lignes)
    assert lignes[1]["note"] == "a glissé" and lignes[0]["robot"] == "robot d'essai"
    resume = clinique.essais_reels.resume()
    assert resume["texte"] == "RÉEL : 1 sur 2" and resume["essais"] == 2 and resume["reussis"] == 1
    assert resume["par_geste"] == [{"robot": "robot d'essai", "geste": "saisir une bouteille", "reussis": 1, "essais": 2}]
    lignes_fiche = {l["titre"]: l["valeur"] for l in fiche.lignes_des_essais(clinique.essais_reels, tmp_path / "rien.json")}
    assert lignes_fiche["Essais réels, comptés par l'équipe"].startswith("RÉEL : 1 sur 2")
    page = client.get("/clinique/essais-reels").text
    assert "RÉEL : 1 sur 2" in page and "a glissé" in page and "saisir une bouteille" in page
    fichier.unlink()  # le fichier d'essai est effacé
    assert clinique.essais_reels.resume()["texte"] == "RÉEL : aucun essai compté"
    lignes_fiche = {l["titre"]: l["valeur"] for l in fiche.lignes_des_essais(clinique.essais_reels, tmp_path / "rien.json")}
    assert lignes_fiche["Essais réels, comptés par l'équipe"] == "RÉEL : aucun essai compté"
    assert "RÉEL : aucun essai compté" in client.get("/clinique/essais-reels").text


def test_sans_le_code_d_equipe_rien_ne_s_ecrit(tmp_path):
    client, clinique = _clinique(tmp_path)
    corps = {"robot": "robot d'essai", "geste": "geste d'essai", "reussi": True, "note": ""}
    assert client.post("/api/clinique/essais_reels", json=corps).status_code == 403
    assert client.post("/api/clinique/essais_reels", json=corps, headers={"X-Code-Equipe": "faux"}).status_code == 403
    assert not clinique.essais_reels.fichier.exists()


def test_il_faut_un_robot_et_un_geste_et_la_note_reste_courte(tmp_path):
    client, clinique = _clinique(tmp_path)
    for corps in ({"robot": " ", "geste": "geste", "reussi": True, "note": ""},
                  {"robot": "robot", "geste": "", "reussi": True, "note": ""}):
        assert client.post("/api/clinique/essais_reels", headers=CODE, json=corps).status_code in (400, 422)
    assert not clinique.essais_reels.fichier.exists()
    client.post("/api/clinique/essais_reels", headers=CODE,
                json={"robot": "robot d'essai", "geste": "geste d'essai", "reussi": True, "note": "x" * 200})
    assert len(clinique.essais_reels.lignes()[0]["note"]) <= 120


def test_un_essai_compte_ne_s_efface_pas_et_ne_se_corrige_pas(tmp_path):
    client, clinique = _clinique(tmp_path)
    assert not hasattr(clinique.essais_reels, "effacer") and not hasattr(clinique.essais_reels, "corriger")
    for methode in (client.delete, client.put, client.patch):
        assert methode("/api/clinique/essais_reels", headers=CODE).status_code == 405


def test_une_balise_dans_une_note_ne_passe_pas_a_l_ecran(tmp_path):
    client, _ = _clinique(tmp_path)
    client.post("/api/clinique/essais_reels", headers=CODE,
                json={"robot": "robot d'essai", "geste": "geste", "reussi": False, "note": "<script>alert(1)</script>"})
    assert "<script>alert(1)" not in client.get("/clinique/essais-reels").text


def test_une_ligne_abimee_dans_le_fichier_se_voit_et_ne_bloque_pas(tmp_path):
    fichier = tmp_path / "abime.jsonl"
    compteur = essais_reels.CompteurReel(fichier)
    compteur.compter("robot d'essai", "geste", True, "")
    with open(fichier, "a", encoding="utf-8") as f:
        f.write("ceci n'est pas une ligne lisible\n")
    resume = compteur.resume()
    assert resume["essais"] == 1 and resume["illisibles"] == 1 and "1 ligne illisible" in resume["texte"]


# ---------------------------------------------------------------------------------------------- dans la fiche de vérité
def test_la_fiche_montre_le_dernier_tableau_des_essais_comptes_avec_son_etiquette_et_sa_date(tmp_path):
    dernier = tmp_path / "essais_dernier.json"
    compteur = essais_reels.CompteurReel(tmp_path / "vide.jsonl")
    lignes = {l["titre"]: l["valeur"] for l in fiche.lignes_des_essais(compteur, dernier)}
    assert lignes["Essais comptés sur le faux robot"].startswith("non mesuré") and "lancer.py essais" in lignes["Essais comptés sur le faux robot"]
    dernier.write_text(json.dumps({"etiquette": "FAUX ROBOT", "date": "2026-11-12T01:44:42", "essais": 20,
                                   "essais_de_la_liste": 20, "echecs": [{"essai": 3, "etape": 4}],
                                   "par_etape": {"1": {"reussies": 20, "essais": 20, "construite": True},
                                                 "4": {"reussies": 19, "essais": 20, "construite": True}}}), encoding="utf-8")
    valeur = {l["titre"]: l["valeur"] for l in fiche.lignes_des_essais(compteur, dernier)}["Essais comptés sur le faux robot"]
    assert valeur.startswith("FAUX ROBOT, le 12.11.2026 : 20 essais") and "1 étape sur 2 toujours réussie" in valeur
    assert "1 échec" in valeur and "étape 4 : 19 sur 20" in valeur


def test_la_repetition_affiche_les_deux_lignes_d_essais(monkeypatch, tmp_path):
    monkeypatch.setattr(essais_reels, "FICHIER", tmp_path / "pas_de_fichier.jsonl")
    controles = {n: (lambda: repetition.Resultat(True, "SIMULÉ", "essai", {"phrases_retirees": 0})) for n in range(1, 13)}
    controles[13], controles[14] = repetition.CONTROLES[13], repetition.CONTROLES[14]
    lignes: list[str] = []
    assert chef_clinique.jouer(controles, ecrire=lignes.append) == 0
    texte = "\n".join(lignes)
    assert "· Essais réels, comptés par l'équipe : RÉEL : aucun essai compté" in texte
    assert "· Essais comptés sur le faux robot : " in texte
