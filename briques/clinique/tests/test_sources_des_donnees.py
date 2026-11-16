"""La clinique en boîte — L01, d'où vient chaque donnée (avenant 4).

« Fini » veut dire :
- chaque sorte de donnée du faux dossier a une source : ADMIN, SOINS, INCONNU ou NOUS ;
- une sorte de donnée ajoutée sans source est signalée par la table ;
- le badge « robot » ne reçoit aucune donnée SOINS (c'est la règle du cahier : on le vérifie par la vraie porte) ;
- la page « D'où vient cette donnée ? » s'affiche, avec pour chaque ligne les badges qui ont le droit de la lire.
Le faux dossier et la porte de lecture ne sont pas modifiés. Aucun nom de vrai logiciel, nulle part.
"""
from __future__ import annotations

import copy
import html
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import dossier, sources
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture


def _ligne(table, sorte):
    return next(l for l in table if l["sorte"] == sorte)


# ---------------------------------------------------------------------------------------------- la table
def test_la_table_est_un_fichier_lisible_a_cote_du_faux_dossier():
    assert sources.FICHIER.parent == dossier.DOSSIER.parent and sources.FICHIER.suffix == ".yaml"
    assert sources.FICHIER not in dossier.fichiers()  # elle n'est pas DANS le faux dossier : ses fiches ne changent pas
    brut = yaml.safe_load(sources.FICHIER.read_text(encoding="utf-8"))
    assert set(brut["sources"]) == {"ADMIN", "SOINS", "INCONNU", "NOUS"}
    texte = sources.FICHIER.read_text(encoding="utf-8").lower()
    assert "compatible" not in texte


def test_chaque_sorte_de_donnee_du_faux_dossier_a_une_source():
    table = sources.charger()
    assert sources.sans_source(dossier.charger(), table) == []
    assert all(l["source"] in sources.SOURCES for l in table)


def test_les_sources_sont_celles_de_l_avenant():
    table = sources.charger()
    attendu = {"l'identité": "ADMIN", "la langue": "ADMIN", "le séjour et ses dates": "ADMIN", "la chambre": "ADMIN",
               "l'assurance": "ADMIN", "les papiers administratifs": "ADMIN",
               "la raison du séjour": "SOINS", "les habitudes": "SOINS", "les listes de soin": "SOINS",
               "les documents médicaux": "SOINS", "le résumé": "SOINS", "les questions pour le médecin": "SOINS",
               "le programme des thérapies": "INCONNU", "le carnet": "NOUS"}
    for sorte, source in attendu.items():
        assert _ligne(table, sorte)["source"] == source, sorte
    assert "Nous ne savons pas quel outil le planifie" in _ligne(table, "le programme des thérapies")["explication"]


def test_une_sorte_de_donnee_ajoutee_sans_source_est_signalee():
    d = dossier.charger()
    patients = [copy.deepcopy(sources.en_clair(p)) for p in d.patients]
    patients[0]["Patient"]["groupe_d_essai"] = "inventé pour cet essai"
    patients[1]["allergies_d_essai"] = ["inventé"]
    patients[2]["DocumentReference"].append({"id": "x", "genre": "papier d'essai inconnu", "titre": "x", "texte": "x",
                                             "langue": "fr", "ecriture": "tapée", "marque": "INVENTÉ"})
    manquent = sources.sans_source(d, sources.charger(), patients=patients)
    assert manquent == ["DocumentReference : genre « papier d'essai inconnu »", "Patient.groupe_d_essai", "allergies_d_essai"]


@pytest.mark.parametrize("faute, mot", [("source: LUNE", "LUNE"), ("source: ", "source")])
def test_une_table_mal_ecrite_est_refusee(tmp_path, faute, mot):
    fichier = tmp_path / "sources.yaml"
    fichier.write_text("marque: inventé\nsources: {ADMIN: a, SOINS: b, INCONNU: c, NOUS: d}\nlignes:\n"
                       f"  - sorte: essai\n    {faute}\n    explication: x\n    champs: [Patient.id]\n", encoding="utf-8")
    with pytest.raises(sources.TableInvalide, match=mot):
        sources.charger(fichier)


# ---------------------------------------------------------------------------------------------- qui lit quoi, par la vraie porte
def test_le_robot_ne_recoit_aucune_donnee_soins():
    qui = sources.qui_lit(sources.charger())
    soins = [l for l in qui if l["source"] == "SOINS"]
    assert len(soins) >= 6 and all("robot" not in l["badges"] for l in soins), [l["sorte"] for l in soins if "robot" in l["badges"]]
    # tout ce que la porte donne au robot a une ligne dans la table, et aucune n'est SOINS
    recu = sources.ce_que_recoit("robot", sources.charger())
    assert recu["sans_ligne"] == [] and recu["cles"] and "SOINS" not in recu["sources"]
    assert set(recu["cles"]) >= {"prenom", "langue", "chambre", "etage"}


def test_les_badges_de_chaque_ligne_viennent_de_la_porte():
    qui = {l["sorte"]: l["badges"] for l in sources.qui_lit(sources.charger())}
    assert qui["la raison du séjour"] == ["médecin"]
    assert "soignant" in qui["les habitudes"] and "accueil" not in qui["les habitudes"] and "thérapeute" not in qui["les habitudes"]
    assert set(qui["la chambre"]) >= {"patient", "soignant", "thérapeute", "médecin", "accueil", "robot"}
    assert "direction" not in qui["l'identité"]  # la direction ne voit aucun nom
    assert qui["le programme des thérapies"] and "robot" in qui["le programme des thérapies"]  # le robot du hall : la première heure seulement


def test_la_porte_et_le_faux_dossier_n_ont_pas_change():
    avant = dossier.empreinte()
    sources.qui_lit(sources.charger())
    assert dossier.empreinte() == avant


# ---------------------------------------------------------------------------------------------- la page
def test_la_page_d_ou_vient_cette_donnee_s_affiche():
    app, horloge = FastAPI(), HorlogeDeDemonstration()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="")
    client = TestClient(app)
    page = html.unescape(client.get("/clinique/sources").text)
    for mot in ("D'où vient cette donnée ?", "ADMIN", "SOINS", "INCONNU", "NOUS", "le logiciel administratif",
                "le dossier de soins", "la raison du séjour", "médecin", "Données inventées",
                "Aucun lien avec un vrai logiciel de clinique", "Toutes les données du faux dossier ont une source"):
        assert mot in page, mot
    assert "Giulia" not in page  # la page parle des sortes de données, pas des personnes
    api = client.get("/api/clinique/sources").json()
    assert api["sans_source"] == [] and len(api["lignes"]) >= 14
    assert "/clinique/sources" in client.get("/clinique/flotte").text or "/clinique/sources" in client.get("/clinique").text
