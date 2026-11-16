"""La clinique en boîte — K06, l'avis des personnes (avenant 2, K06 ; réponse de Hiba à Q9 : oui, aux conditions écrites).

Conditions de Hiba : cinq notes de 1 à 5 et un rôle, sans nom, sans texte libre, dans un fichier qui reste sur l'ordinateur.
« Fini quand, avec le oui : avec six avis d'essai, la page affiche six avis et cinq moyennes ; avec quatre, elle affiche
« trop peu d'avis » ; une vérification prouve que le fichier des avis ne fait pas partie de ce qui part vers GitHub ; les
avis d'essai sont effacés. » Et la version simple : le formulaire enregistre un avis d'essai, puis l'efface ; la page affiche
« Aucun avis réel… » ; elle s'ouvre depuis la page « Concours ».
JAMAIS un avis réel écrit par ce programme : ici, seulement des avis marqués ESSAI, dans un fichier à part, effacés ensuite.
"""
from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import avis
from briques.clinique.ecrans import brancher_ecrans

RACINE = Path(__file__).resolve().parents[3]
CODE = {"X-Code-Equipe": "code-d-essai"}
QUESTIONS = ("Le robot a-t-il dit ce qu'il allait faire avant de bouger ?", "Est-il resté à une distance qui vous convenait ?",
             "Vous a-t-il surpris ? (1 : souvent ; 5 : jamais)", "Avez-vous compris ses refus, et ses « je ne suis pas sûr » ?",
             "Seriez-vous d'accord pour qu'il aide dans un service de soins ?")
ROLES = ("soignant", "patient ou proche", "visiteur", "ingénieur", "autre")


@pytest.fixture
def banc(tmp_path):
    app = FastAPI()
    clinique = brancher_ecrans(app, code_equipe="code-d-essai")
    clinique.faux_logiciel.dossier = tmp_path / "faux_logiciel"
    clinique.avis.fichier = tmp_path / "avis.jsonl"  # jamais le vrai fichier des avis
    return TestClient(app, base_url="http://127.0.0.1"), clinique


def _essai(client, role="visiteur", notes=(4, 5, 3, 4, 5)):
    return client.post("/api/clinique/avis", json={"role": role, "notes": list(notes), "essai": True}, headers=CODE)


def test_le_formulaire_a_les_cinq_questions_les_cinq_roles_la_phrase_et_aucun_champ_libre(banc):
    client, _ = banc
    brut = client.get("/clinique/avis/donner").text
    page = html.unescape(brut)
    assert "Vos réponses sont anonymes. Elles servent à un prototype de concours. Vous pouvez arrêter quand vous voulez." in page
    assert page.index("Vos réponses sont anonymes") < page.index(QUESTIONS[0])
    for question in QUESTIONS:
        assert question in page, question
    for role in ROLES:
        assert role in page, role
    milieu = brut.split("<main id='contenu'>")[1].split("</main>")[0]
    assert "type='text'" not in milieu and "<textarea" not in milieu and "nom" not in html.unescape(milieu).lower().replace("anonymes", "")
    assert milieu.count("type='radio'") == 25


def test_un_avis_d_essai_est_enregistre_marque_essai_puis_efface(banc):
    client, clinique = banc
    r = _essai(client)
    assert r.status_code == 200, r.text
    lignes = [json.loads(l) for l in clinique.avis.fichier.read_text(encoding="utf-8").splitlines()]
    assert len(lignes) == 1 and lignes[0]["marque"] == "ESSAI" and set(lignes[0]) == {"quand", "role", "notes", "marque"}
    assert client.post("/api/clinique/avis/effacer-les-essais", headers=CODE).json()["effaces"] == 1
    assert clinique.avis.fichier.read_text(encoding="utf-8").strip() == ""


def test_sans_avis_reel_la_page_le_dit(banc):
    client, _ = banc
    _essai(client)
    page = html.unescape(client.get("/clinique/avis").text)
    assert "Aucun avis réel recueilli pour l'instant." in page and "ESSAI" in page


def test_avec_six_avis_d_essai_six_avis_et_cinq_moyennes(banc):
    client, clinique = banc
    notes = [(1, 2, 3, 4, 5), (5, 5, 5, 5, 5), (1, 1, 1, 1, 1), (3, 3, 3, 3, 3), (2, 4, 2, 4, 2), (4, 4, 4, 4, 4)]
    for i, n in enumerate(notes):
        assert _essai(client, ROLES[i % 5], n).status_code == 200
    page = html.unescape(client.get("/clinique/avis").text)
    essais = page.split("Avis d'essai")[1]
    assert "6 avis" in essais and essais.count("moyenne") == 5 and "trop peu d'avis" not in essais
    assert "moyenne 2,7 sur 5" in essais  # question 1 : (1+5+1+3+2+4)/6 = 2,666… → 2,7 ; une mauvaise note se montre aussi
    assert "soignant : 2" in essais and "visiteur : 1" in essais
    assert "Aucun avis réel recueilli pour l'instant." in page  # les essais ne se mélangent jamais aux avis réels
    client.post("/api/clinique/avis/effacer-les-essais", headers=CODE)
    assert not clinique.avis.lignes()


def test_avec_quatre_avis_trop_peu_d_avis(banc):
    client, _ = banc
    for _ in range(4):
        _essai(client)
    essais = html.unescape(client.get("/clinique/avis").text).split("Avis d'essai")[1]
    assert "4 avis" in essais and "trop peu d'avis" in essais and "moyenne" not in essais


@pytest.mark.parametrize("corps", [{"role": "visiteur", "notes": [4, 5, 3, 4]}, {"role": "visiteur", "notes": [4, 5, 3, 4, 6]},
                                   {"role": "médecin chef", "notes": [4, 5, 3, 4, 5]},
                                   {"role": "visiteur", "notes": [4, 5, 3, 4, 5], "nom": "Jean"},
                                   {"role": "visiteur", "notes": [4, 5, 3, 4, 5], "commentaire": "bien"}])
def test_un_avis_hors_des_conditions_est_refuse_et_rien_n_est_ecrit(banc, corps):
    client, clinique = banc
    assert client.post("/api/clinique/avis", json={**corps, "essai": True}, headers=CODE).status_code == 422
    assert not clinique.avis.fichier.exists() or clinique.avis.fichier.read_text(encoding="utf-8") == ""


def test_effacer_les_essais_demande_le_code_et_ne_touche_pas_aux_avis_reels(banc, tmp_path):
    client, clinique = banc
    reel = {"quand": "2026-11-14T10:00:00+01:00", "role": "visiteur", "notes": [3, 3, 3, 3, 3], "marque": "RÉEL"}
    clinique.avis.fichier.write_text(json.dumps(reel, ensure_ascii=False) + "\n", encoding="utf-8")  # une ligne fabriquée pour l'essai
    _essai(client)
    assert TestClient(client.app).post("/api/clinique/avis/effacer-les-essais").status_code == 403
    client.post("/api/clinique/avis/effacer-les-essais", headers=CODE)
    restantes = clinique.avis.lignes()
    assert restantes == [reel]
    clinique.avis.fichier.unlink()


def test_le_fichier_des_avis_ne_part_jamais_vers_github():
    assert avis.FICHIER.parent.is_relative_to(RACINE / "journal")
    sortie = subprocess.run(["git", "check-ignore", "-v", str(avis.FICHIER)], cwd=RACINE, capture_output=True, text=True)
    assert sortie.returncode == 0 and "avis" in sortie.stdout, sortie.stdout
    suivis = subprocess.run(["git", "ls-files", "--", str(avis.FICHIER.relative_to(RACINE))], cwd=RACINE, capture_output=True, text=True)
    assert suivis.stdout.strip() == ""


def test_la_page_s_ouvre_depuis_concours_et_la_collecte_a_son_adresse(banc):
    client, _ = banc
    concours = client.get("/clinique/concours").text
    assert "/clinique/avis\"" in concours
    page = html.unescape(client.get("/clinique/avis").text)
    assert "/clinique/avis/donner" in page and "Codes QR : pas encore" in page


def test_le_formulaire_est_dans_la_page_des_telephones(banc):
    from briques.clinique import reseau_local

    assert "clinique/avis/donner" in dict(reseau_local.ecrans())
