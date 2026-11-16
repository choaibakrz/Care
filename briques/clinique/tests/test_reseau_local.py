"""La clinique en boîte — T30, le réseau local (cahier, T30).

« Une page d'entrée qui liste les écrans, avec un code QR pour chacun, pour les téléphones branchés sur le même Wi-Fi.
S'il faut un outil pour dessiner les codes, c'est un feu orange : en attendant, affiche les adresses en gros. »
« Fini quand : la page d'entrée répond et chaque adresse mène au bon écran. »
Aucun outil pour dessiner les codes QR n'est sur cet ordinateur : question Q29 à Hiba. La page affiche les adresses en gros.
Essayé depuis cet ordinateur, par son adresse du Wi-Fi ; pas depuis un vrai téléphone.
"""
from __future__ import annotations

import html
import re
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import reseau_local
from briques.clinique.ecrans import ECRANS, brancher_ecrans

PAGE = "/clinique/telephones"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(reseau_local, "adresse_du_wifi", lambda: "192.168.1.23")
    app = FastAPI()
    brancher_ecrans(app)
    return TestClient(app)


def _adresses(page: str) -> list[str]:
    return re.findall(r"http://[0-9.]+:\d+/clinique/[^\s<\"']*", html.unescape(page))


def test_la_page_d_entree_repond_et_liste_chaque_ecran_avec_son_adresse_du_wifi(client):
    brut = client.get(PAGE)
    page = html.unescape(brut.text)
    assert brut.status_code == 200 and "DONNÉES INVENTÉES" in page and "même Wi-Fi" in page
    adresses = _adresses(brut.text)
    for ecran in ECRANS:
        assert any(f"/clinique/{ecran}" in a for a in adresses), ecran
    assert all(a.startswith("http://192.168.1.23:") for a in adresses) and "localhost" not in page.split("<main")[1]
    assert PAGE in client.get("/clinique").text


def test_chaque_adresse_mene_au_bon_ecran(client):
    for adresse in _adresses(client.get(PAGE).text):
        chemin = adresse.split(":", 2)[2].split("/", 1)[1]
        reponse = client.get("/" + chemin)
        assert reponse.status_code == 200, adresse
        titre = re.search(r"<title>(.*?)</title>", reponse.text).group(1)
        attendu = reseau_local.titre_attendu(chemin)
        assert attendu in html.unescape(titre), (adresse, titre, attendu)


def test_les_adresses_sont_ecrites_en_gros(client):
    page = client.get(PAGE).text
    assert "class='lisible'" in page and "font-size:1.6rem" in page


def test_les_codes_qr_attendent_hiba_et_la_page_le_dit(client):
    page = html.unescape(client.get(PAGE).text)
    assert "Codes QR : pas encore" in page and "Q29" in page and "<img" not in page and "<svg" not in page


def test_sans_adresse_du_wifi_la_page_le_dit_et_ne_donne_pas_une_fausse_adresse(monkeypatch):
    monkeypatch.setattr(reseau_local, "adresse_du_wifi", lambda: None)
    app = FastAPI()
    brancher_ecrans(app)
    page = html.unescape(TestClient(app).get(PAGE).text)
    assert "Aucune adresse du Wi-Fi trouvée" in page and not _adresses(page)


def test_si_le_serveur_n_ecoute_que_cet_ordinateur_la_page_le_dit():
    texte = html.unescape(reseau_local.dessiner("192.168.1.23", 8000, ecoute="127.0.0.1"))
    assert "les téléphones ne pourront pas ouvrir" in texte and "0.0.0.0" in texte
    assert "les téléphones ne pourront pas ouvrir" not in html.unescape(reseau_local.dessiner("192.168.1.23", 8000, ecoute="0.0.0.0"))


def test_l_adresse_trouvee_est_une_adresse_du_reseau_local():
    adresse = reseau_local.adresse_du_wifi()
    if adresse is None:
        pytest.skip("cet ordinateur n'est sur aucun réseau en ce moment")
    assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", adresse) and not adresse.startswith("127.")
    assert reseau_local.est_locale(adresse), adresse


@pytest.mark.parametrize("adresse, locale", [("192.168.1.2", True), ("10.0.0.5", True), ("172.20.1.1", True),
                                             ("100.64.3.4", True), ("8.8.8.8", False), ("172.32.0.1", False)])
def test_une_adresse_hors_du_reseau_local_n_est_pas_donnee(adresse, locale):
    assert reseau_local.est_locale(adresse) is locale


def test_par_le_vrai_wifi_la_commande_existe_et_les_essais_ne_s_en_servent_pas():
    """Les essais coupent tout réseau sauf cet ordinateur lui-même (conftest.py, un garde-fou établi, pas touché).
    L'essai par l'adresse du Wi-Fi est donc la commande « python3 lancer.py telephones », lancée hors des essais.
    Ici : sous le garde-fou, la commande ne peut pas joindre le Wi-Fi, et elle le dit au lieu de prétendre."""
    import lancer

    assert "telephones" in lancer.__doc__
    lignes: list[str] = []
    try:
        code = reseau_local.essayer_par_le_wifi(ecrire=lignes.append)
    except Exception as erreur:  # noqa: BLE001 — le garde-fou refuse la connexion : c'est attendu sous pytest
        assert "Internet coupé pendant les tests" in str(erreur) or isinstance(erreur, (ConnectionError, httpx.HTTPError))
        return
    assert code != 0 and "RÉUSSI" not in "\n".join(lignes)
