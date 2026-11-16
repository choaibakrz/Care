"""La clinique en boîte — K05, le tableau des capacités, et ce qui n'est pas résolu (avenant 2, K05 ; avenant 3, M02).

« La page « Ce que le système sait faire, et comment on le sait ». Une ligne par capacité. Quatre colonnes : PROUVÉ SUR UN
VRAI ROBOT (nombre d'essais, date) ; PROUVÉ SUR LE FAUX ROBOT (nombre d'essais) ; VÉRIFIÉ PAR DES TESTS SEULEMENT ; PAS FAIT.
La page se fabrique à partir des résultats. Une capacité sans essai réel ne peut pas être dans la première colonne. »
« Fini quand : la page s'ouvre depuis la page « Concours » ; avec un fichier d'essai, un essai « réel » enregistré fait
passer une ligne dans la première colonne, et la ligne revient quand le fichier est effacé ; une capacité dont la pièce est
BLOQUÉ s'affiche PAS FAIT ; le contenu de docs/projet/PAS_RESOLU.md s'affiche en bas. »
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import capacites
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.essais_reels import CompteurReel

RACINE = Path(__file__).resolve().parents[3]
DEMANDEES = ("accueillir dans une langue", "ranger un papier", "suivre une liste de soin", "rappeler le point oublié",
             "apporter un objet", "refuser un geste interdit", "passer le relais", "reprendre après une panne",
             "brancher un robot inconnu", "se rejouer seul", "déplacer des objets d'une étagère à une table")
COLONNES = (capacites.REEL, capacites.FAUX, capacites.TESTS, capacites.PAS_FAIT)


@pytest.fixture
def sources(tmp_path):
    essais = {"date": "2026-11-12T09:29:28", "etiquette": "FAUX ROBOT", "essais": 20,
              "par_etape": {str(n): {"reussies": 20 if n != 7 else 18, "essais": 20, "etiquettes": ["SIMULÉ"] if n != 8 else ["FAUX ROBOT"]}
                            for n in range(1, 15)}}
    (tmp_path / "essais_dernier.json").write_text(json.dumps(essais), encoding="utf-8")
    return {"essais": tmp_path / "essais_dernier.json", "reels": tmp_path / "essais_reels.jsonl",
            "branchements": tmp_path / "branchements.json", "mesures": tmp_path / "mesures", "rejeux": tmp_path / "rejeux"}


def _lignes(sources, suivi=None):
    return {l["titre"]: l for l in capacites.tableau(**sources, suivi=suivi)}


def test_chaque_capacite_demandee_a_sa_ligne_et_une_seule_colonne(sources):
    lignes = _lignes(sources)
    for titre in DEMANDEES:
        assert titre in lignes, titre
    assert len(lignes) >= len(DEMANDEES) + 2  # « ajoute celles qui manquent »
    for l in lignes.values():
        assert l["niveau"] in COLONNES, l


def test_les_essais_comptes_mettent_une_ligne_dans_la_colonne_du_faux_robot(sources):
    lignes = _lignes(sources)
    point = lignes["rappeler le point oublié"]
    assert point["niveau"] == capacites.FAUX and "18 réussis sur 20" in point["faux"] and "12.11.2026" in point["faux"]
    assert point["reel"] == "—"


def test_un_essai_reel_fait_passer_la_ligne_dans_la_premiere_colonne_et_elle_revient_quand_le_fichier_est_efface(sources):
    assert _lignes(sources)["apporter un objet"]["niveau"] == capacites.FAUX
    CompteurReel(sources["reels"]).compter("robot d'essai", "apporter un objet", True, note="essai de la vérification")
    ligne = _lignes(sources)["apporter un objet"]
    assert ligne["niveau"] == capacites.REEL and "1 réussi sur 1" in ligne["reel"] and "RÉEL" in ligne["reel"]
    assert _lignes(sources)["ranger un papier"]["niveau"] != capacites.REEL  # les autres lignes ne bougent pas
    sources["reels"].unlink()
    assert _lignes(sources)["apporter un objet"]["niveau"] == capacites.FAUX


def test_un_essai_reel_rate_ne_met_pas_la_ligne_dans_la_premiere_colonne(sources):
    CompteurReel(sources["reels"]).compter("robot d'essai", "apporter un objet", False)
    ligne = _lignes(sources)["apporter un objet"]
    assert ligne["niveau"] == capacites.FAUX and "0 réussi sur 1" in ligne["reel"]


def test_une_capacite_dont_la_piece_est_bloquee_s_affiche_pas_fait(sources):
    suivi = "| T24 | La panne et la reprise | T23 | BLOQUÉ (essai) | ... |\n"
    ligne = _lignes(sources, suivi=suivi)["reprendre après une panne"]
    assert ligne["niveau"] == capacites.PAS_FAIT and "BLOQUÉ" in ligne["pas_fait"] and "T24" in ligne["pas_fait"]


def test_sans_aucun_resultat_la_page_ne_met_rien_dans_les_colonnes_prouvees(tmp_path):
    vide = {k: tmp_path / k for k in ("essais", "reels", "branchements", "mesures", "rejeux")}
    for l in capacites.tableau(**vide):
        assert l["niveau"] in (capacites.TESTS, capacites.PAS_FAIT), l
        assert l["reel"] == "—" and l["faux"] == "—"


def test_la_page_s_ouvre_depuis_la_page_concours_et_montre_pas_resolu_en_bas(tmp_path):
    app = FastAPI()
    clinique = brancher_ecrans(app)
    clinique.faux_logiciel.dossier = tmp_path / "faux_logiciel"
    client = TestClient(app)
    concours = html.unescape(client.get("/clinique/concours").text)
    assert "Concours" in concours and "/clinique/capacites" in concours and "/clinique/invite" in concours
    assert "/clinique/etageres" in concours and "/clinique/tirage" in concours
    assert "/clinique/concours" in client.get("/clinique").text
    brut = client.get("/clinique/capacites").text
    page = html.unescape(brut)
    assert "Ce que le système sait faire, et comment on le sait" in page
    for colonne in COLONNES:
        assert colonne in page, colonne
    pas_resolu = (RACINE / "docs/projet/PAS_RESOLU.md").read_text(encoding="utf-8")
    assert page.index("Ce que nous n'avons pas résolu") > page.index("PAS FAIT")
    for ligne in [l for l in pas_resolu.splitlines() if l.startswith("- ")]:
        assert html.unescape(ligne[2:].split(" — ")[0]) in page, ligne


def test_pas_resolu_a_la_liste_de_depart_et_jamais_bientot():
    texte = (RACINE / "docs/projet/PAS_RESOLU.md").read_text(encoding="utf-8")
    for sujet in ("un vrai service avec de vrais patients", "l'hygiène", "le réseau d'une vraie clinique", "la nuit",
                  "l'accord du personnel", "les règles sur les appareils médicaux", "la saisie d'objets par un vrai bras",
                  "le lien avec le logiciel d'une clinique"):
        assert sujet in texte.lower(), sujet
    lignes = [l for l in texte.splitlines() if l.startswith("- ")]
    assert len(lignes) >= 8 and all(("pas essayé" in l or "essayé, raté" in l) for l in lignes)
    assert "bientôt" not in texte.lower()


def test_samedi_matin_a_les_six_lignes_de_la_vraie_salle():
    texte = (RACINE / "docs/projet/SAMEDI_MATIN.md").read_text(encoding="utf-8")
    partie = texte.split("La vraie salle")[1]
    for question in ("La lumière de la salle est-elle celle de nos essais ?", "Y a-t-il des reflets ou des objets brillants ?",
                     "Quel est le bruit ?", "Le Wi-Fi tient-il quand la salle est pleine ?",
                     "A-t-on répété une fois dans la vraie salle, à l'heure de la démonstration ?",
                     "L'heure exacte de la démonstration finale est-elle confirmée par les organisateurs ?"):
        assert f"- [ ] {question}" in partie, question
    assert "Le robot à roues (cahier 5.12)" in texte and "En plus, pour le matériel" in texte  # rien d'effacé


def test_aucun_chiffre_n_est_tape_a_la_main_dans_la_liste_des_capacites():
    texte = (RACINE / "briques" / "clinique" / "capacites.yaml").read_text(encoding="utf-8")
    assert "réussi" not in texte and "sur 20" not in texte  # la liste dit QUOI regarder, jamais un résultat
