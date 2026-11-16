"""La clinique en boîte — T27, la fiche de vérité complète (cahier 5.11 ; avenant 2, K02 et K03 ; avenant 4, L03).

« Fini quand : toutes les lignes de 5.11 se remplissent seules après une répétition. »
En plus des sept lignes du cahier, la fiche porte :
- les trois chiffres de K02, avec leur niveau de preuve, leur nombre d'essais et leur date ;
- « réussis et constatés : tant sur tant » (K03) ;
- « logiciel administratif : SIMULÉ ; messages lus : tant ; messages à trier : tant » (L03).
Tout est compté pendant la répétition : rien n'est tapé à la main. Après la répétition, la fiche est gardée dans un fichier
(avec sa date) et une page la montre. Faux robot et robots simulés : aucun vrai robot.
"""
from __future__ import annotations

import html
import json
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import aide_humaine, chef_clinique, ecrans_fiche, fiche, repetition, traducteur

EN_PLUS = ("Réussis du premier coup", "Aide humaine", "Plus longue durée sans arrêt", "Réussis et constatés",
           "Logiciel administratif")


@pytest.fixture(scope="module")
def jouee():
    """Une vraie répétition, jouée une fois pour tous les essais de ce fichier."""
    sortie: list[str] = []
    seances: list[repetition.Seance] = []
    code = chef_clinique.jouer(ecrire=sortie.append, garder=seances)
    return code, "\n".join(sortie), seances[0]


def _valeurs(seance):
    return {l["titre"]: l["valeur"] for l in fiche.fiche_de_la_repetition(seance)["lignes"]}


def test_apres_une_repetition_toutes_les_lignes_se_remplissent_seules(jouee):
    code, texte, seance = jouee
    assert code == 0
    valeurs = _valeurs(seance)
    for titre in fiche.LIGNES_DU_CAHIER + EN_PLUS:
        assert valeurs.get(titre, "").strip(), titre
        assert f"{titre} : " in texte, titre  # et la répétition l'affiche
    assert fiche.LIGNES_EN_PLUS == EN_PLUS


def test_les_trois_chiffres_ont_leur_preuve_leur_nombre_d_essais_et_leur_date(jouee):
    _, _, seance = jouee
    valeurs = _valeurs(seance)
    un = valeurs["Réussis du premier coup"]
    assert re.search(r"^\d+ sur 12 \[FAUX ROBOT ET SIMULÉ, 12 essais, \d{2}\.\d{2}\.\d{4}\]", un), un
    assert "une étape de la répétition = un essai" in un
    deux = valeurs["Aide humaine"]
    assert ("aucune aide sur" in deux or "aide" in deux) and "tâches de robot" in deux and "12 essais" in deux
    trois = valeurs["Plus longue durée sans arrêt"]
    assert "non mesuré" in trois or re.search(r"\[FAUX ROBOT, \d+ passages", trois), trois


def test_les_cases_viennent_de_ce_qui_s_est_passe_a_chaque_etape():
    """Une aide humaine pendant l'étape 3, une étape 5 ratée : chacune va dans sa case, et une seule."""
    def controle(numero):
        def jouer():
            if numero == 3:
                aide_humaine.signaler("bouton", qui="essai", detail="une aide d'essai")
            return repetition.Resultat(numero != 5, "SIMULÉ", "essai")
        return jouer

    with repetition.seance() as seance:
        for n in range(1, 13):
            try:
                r = controle(n)()
            except Exception:
                r = None
            repetition._noter(n, "reussie" if r.reussie else "ratee", r)
        cases = fiche.cases_de_la_seance(seance)
    assert cases == {"du premier coup": 10, "après une reprise automatique": 0, "avec une aide humaine": 1, "raté": 1}
    valeurs = _valeurs(seance)
    assert valeurs["Réussis du premier coup"].startswith("10 sur 12")
    assert "1 aide humaine" in valeurs["Aide humaine"] or "aucune tâche de robot" in valeurs["Aide humaine"]


def test_reussis_et_constates_compte_les_livraisons_que_le_monde_a_montrees(jouee):
    _, _, seance = jouee
    ligne = _valeurs(seance)["Réussis et constatés"]
    m = re.match(r"(\d+) sur (\d+) livraisons? d'un robot", ligne)
    assert m and int(m.group(1)) <= int(m.group(2)) and int(m.group(2)) >= 1, ligne
    assert (int(m.group(1)), int(m.group(2))) == (seance.aide.constatees, seance.aide.livraisons)
    assert "SIMULÉ" in ligne  # le constat vient du monde simulé, pas d'une personne


def test_la_ligne_du_logiciel_administratif_compte_les_messages_lus_pendant_la_repetition(jouee, tmp_path):
    _, _, seance = jouee
    ligne = _valeurs(seance)["Logiciel administratif"]
    assert re.match(r"SIMULÉ ; messages lus : \d+ ; messages à trier : \d+", ligne), ligne
    with traducteur.compter() as compte:  # le compteur suit vraiment les lectures
        (tmp_path / "abime.hl7").write_text("ceci n'est pas un message", encoding="utf-8")
        assert traducteur.Traducteur(tmp_path).lire()["a_trier"] == 1
    assert compte == {"lus": 0, "a_trier": 1}


def test_la_fiche_est_gardee_dans_un_fichier_avec_sa_date_et_une_page_la_montre(jouee, tmp_path):
    _, _, seance = jouee
    fichier = tmp_path / "fiche_derniere.json"
    ecrite = fiche.garder(fiche.fiche_de_la_repetition(seance), fichier, reussie=True)
    lue = json.loads(fichier.read_text(encoding="utf-8"))
    assert lue["marque"] == "données inventées" and lue["quand"] == ecrite["quand"] and len(lue["lignes"]) >= 12
    app = FastAPI()
    ecrans_fiche.brancher_fiche(app, fichier)
    page = html.unescape(TestClient(app).get("/clinique/fiche-de-verite").text)
    assert "DONNÉES INVENTÉES" in page and "Fiche de vérité" in page and "dernière répétition" in page
    for titre in fiche.LIGNES_DU_CAHIER + EN_PLUS:
        assert titre in page, titre
    assert "Giulia" not in page and "/Users/" not in page


def test_sans_repetition_la_page_le_dit_et_n_invente_rien(tmp_path):
    app = FastAPI()
    ecrans_fiche.brancher_fiche(app, tmp_path / "absente.json")
    page = html.unescape(TestClient(app).get("/clinique/fiche-de-verite").text)
    assert "Aucune répétition" in page and "python3 lancer.py repetition" in page and "sur 12" not in page


def test_la_page_est_branchee_avec_les_ecrans_de_la_clinique():
    from briques.clinique.ecrans import brancher_ecrans

    app = FastAPI()
    brancher_ecrans(app)
    client = TestClient(app)
    assert client.get("/clinique/fiche-de-verite").status_code == 200
    assert "/clinique/fiche-de-verite" in client.get("/clinique").text
