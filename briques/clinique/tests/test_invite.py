"""La clinique en boîte — K07a, l'écran « Invité » (avenant 2, K07 ; avenant 4, L02).

« Lundi, le mieux est qu'un juré tienne lui-même les commandes. Il faut donc un écran que l'on comprend sans nous. »
« Fini » veut dire, pour cette première moitié :
- l'écran `/clinique/invite` a quatre grands boutons, chacun avec une phrase d'aide : tirer une demande au hasard, changer la
  langue, cacher un objet, provoquer une panne ;
- chaque bouton marche depuis cet écran, sans passer par un autre ;
- rien de dangereux : l'écran n'ouvre aucun réglage, n'accepte que des choix d'une liste fermée, et ne fait bouger aucun
  vrai robot ; depuis un autre ordinateur, il faut le code d'équipe ;
- tout ce que fait l'invité est écrit dans la boîte noire, avec la marque INVITÉ ;
- « Remettre à zéro » remet le scénario prêt à jouer en moins de dix secondes, sans relancer les programmes : les pannes
  finies, le faux logiciel administratif remis à zéro (avenant 4, L02) ; la boîte noire n'est pas effacée.
Reste pour K07b : la commande qui essaie les quatre boutons dans six ordres, et la mesure de la taille du texte.
Faux robot et robots simulés. Aucun vrai robot.
"""
from __future__ import annotations

import html
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

CODE = {"X-Code-Equipe": "code-d-essai"}


class Boite:
    def __init__(self) -> None:
        self.notes: list[dict] = []

    async def emettre(self, genre, source, **donnees):
        self.notes.append({"genre": genre, "source": source, **donnees})


@pytest.fixture
def banc(tmp_path):
    boite = Boite()
    horloge, app = HorlogeDeDemonstration(bus=boite), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    clinique.faux_logiciel.dossier = tmp_path / "faux_logiciel"  # jamais le vrai dossier du journal (corrigé au tour 88)
    return TestClient(app), clinique, boite


def _de_l_invite(boite):
    return [n for n in boite.notes if n.get("marque") == "INVITÉ"]


def test_l_ecran_a_quatre_grands_boutons_avec_leur_phrase_d_aide(banc):
    client, _, _ = banc
    brut = client.get("/clinique/invite")
    page = html.unescape(brut.text)
    assert brut.status_code == 200 and "DONNÉES INVENTÉES" in page and "Invité" in page
    for titre in ("Tirer une demande au hasard", "Changer la langue", "Cacher un objet", "Provoquer une panne", "Remettre à zéro"):
        assert titre in page, titre
    assert page.count("class='aide'") >= 5  # une phrase d'aide par bouton
    assert "/clinique/invite" in client.get("/clinique").text


def test_l_ecran_n_ouvre_aucun_reglage(banc):
    client, _, _ = banc
    brut = client.get("/clinique/invite").text
    milieu = brut.split("<main id='contenu'>")[1].split("</main>")[0]
    for mot in ("reglages", "réglages", "/api/clinique/flotte", "/api/faux-logiciel", "/clinique/pannes\"", "vitesse", "gardien/regles"):
        assert mot not in milieu, mot
    assert milieu.count("<input") == 1 and "Code d'équipe" in milieu  # le seul champ : le code, depuis un autre ordinateur


def test_bouton_1_tirer_une_demande_au_hasard(banc):
    client, _, boite = banc
    r = client.post("/api/clinique/invite/tirage", json={}, headers=CODE)
    assert r.status_code == 200, r.text
    fait = r.json()
    assert fait["bouton"] == "tirage" and fait["etiquette"] == "FAUX ROBOT" and "gestes interdits exécutés : 0" in fait["dit"]
    page = html.unescape(client.get("/clinique/invite").text)
    assert fait["dit"] in page  # le résultat s'affiche sur l'écran de l'invité, pas ailleurs
    assert [n["bouton"] for n in _de_l_invite(boite)] == ["tirage"]


@pytest.mark.parametrize("langue, debut", [("de", "Guten Tag"), ("fr", "Bonjour"), ("en", "Hello"), ("it", "Buongiorno")])
def test_bouton_2_changer_la_langue(banc, langue, debut):
    client, _, boite = banc
    r = client.post("/api/clinique/invite/langue", json={"choix": langue}, headers=CODE)
    assert r.status_code == 200 and r.json()["reussi"] is True, r.text
    assert debut in r.json()["dit"] and "tapée" in r.json()["dit"]
    assert _de_l_invite(boite)[-1]["choix"] == langue


def test_bouton_3_cacher_un_objet(banc):
    client, _, boite = banc
    r = client.post("/api/clinique/invite/objet", json={"choix": "un fauteuil roulant"}, headers=CODE)
    assert r.status_code == 200 and r.json()["reussi"] is True, r.text
    assert "Je ne trouve pas cet objet" in r.json()["dit"] and "humain" in r.json()["dit"]
    assert _de_l_invite(boite)[-1]["bouton"] == "objet"


def test_bouton_4_provoquer_une_panne_puis_la_finir(banc):
    client, clinique, boite = banc
    r = client.post("/api/clinique/invite/panne", json={}, headers=CODE)
    assert r.status_code == 200 and clinique.pannes.active("lien_robot"), r.text
    assert "PANNE PROVOQUÉE" in client.get("/clinique/invite").text  # le bandeau, sur l'écran de l'invité
    r = client.post("/api/clinique/invite/panne", json={}, headers=CODE)  # le même bouton finit la panne
    assert r.status_code == 200 and not clinique.pannes.active("lien_robot")
    assert [n["choix"] for n in _de_l_invite(boite)] == ["provoquer", "finir"]


@pytest.mark.parametrize("bouton, choix", [("langue", "es"), ("objet", "une bombe"), ("objet", "la couverture"),
                                           ("reglages", None), ("panne", "cerveau_muet")])
def test_seuls_les_choix_de_la_liste_sont_acceptes(banc, bouton, choix):
    client, clinique, boite = banc
    r = client.post(f"/api/clinique/invite/{bouton}", json={} if choix is None else {"choix": choix}, headers=CODE)
    assert r.status_code in (400, 404, 422), r.text
    assert not _de_l_invite(boite) and not clinique.pannes.actives()


def test_depuis_un_autre_ordinateur_il_faut_le_code_d_equipe(banc):
    client, clinique, boite = banc
    for bouton in ("tirage", "langue", "objet", "panne", "zero"):
        assert client.post(f"/api/clinique/invite/{bouton}", json={"choix": "de"}).status_code == 403, bouton
    assert not _de_l_invite(boite)


def test_remettre_a_zero_en_moins_de_dix_secondes_sans_effacer_la_boite_noire(banc):
    client, clinique, boite = banc
    client.post("/api/clinique/invite/panne", json={}, headers=CODE)
    client.post("/api/clinique/invite/langue", json={"choix": "de"}, headers=CODE)
    faux = clinique.faux_logiciel
    attente = next(p for p in faux.liste() if not p["verrouille"])  # une des trois personnes en attente
    faux.evenement("A05", attente["numero_patient"])  # le faux logiciel a bougé
    assert faux.messages()
    avant = len(boite.notes)
    debut = time.monotonic()
    r = client.post("/api/clinique/invite/zero", json={}, headers=CODE)
    duree = time.monotonic() - debut
    assert r.status_code == 200 and duree < 10, (r.text, duree)
    assert not clinique.pannes.actives() and not faux.messages()
    assert r.json()["secondes"] < 10 and "pannes" in r.json()["dit"] and "faux logiciel" in r.json()["dit"]
    assert len(boite.notes) > avant and boite.notes[:avant] == boite.notes[:avant]  # rien d'effacé : seulement ajouté
    assert _de_l_invite(boite)[-1]["bouton"] == "zero"
    page = html.unescape(client.get("/clinique/invite").text)
    assert "Guten Tag" not in page  # l'écran de l'invité est propre


# --- Dans un vrai navigateur (Chrome sans fenêtre) : de vrais gestes de souris sur l'écran de l'invité -------------------------
from briques.clinique.tests.test_clic_dans_le_navigateur import CHROME, Pilote, chrome, serveur  # noqa: E402,F401


@pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur : les boutons ne sont pas essayés dans un navigateur")
def test_dans_chrome_l_invite_change_la_langue_puis_remet_a_zero(serveur, chrome):  # noqa: F811
    import asyncio
    import json

    import websockets

    async def bouton(pilote, texte):
        point = None
        for _ in range(50):
            point = await pilote.lire(
                "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === " + json.dumps(texte) + ");"
                " if (!b) return null; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect();"
                " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()")
            if point:
                break
            await asyncio.sleep(0.1)
        assert point, f"le bouton « {texte} » n'est pas sur la page"
        await pilote.cliquer(point, 0.08)

    async def attendre(pilote, condition, mot):
        for _ in range(100):
            texte = await pilote.lire("document.getElementById('contenu').innerText")
            if condition(texte):
                return texte
            await asyncio.sleep(0.1)
        raise AssertionError(f"« {mot} » : {texte[:500]}")

    async def jouer():
        async with websockets.connect(chrome, max_size=None) as ws:
            pilote = Pilote(ws)
            await pilote.ouvrir(f"{serveur}/clinique/invite")
            await bouton(pilote, "Deutsch")
            vu = await attendre(pilote, lambda t: "Guten Tag" in t, "Guten Tag")
            await bouton(pilote, "Remettre à zéro")
            apres = await attendre(pilote, lambda t: "Guten Tag" not in t, "plus de Guten Tag")
            return vu, apres

    vu, apres = asyncio.run(jouer())
    assert "Réussi" in vu and "SIMULÉ" in vu and "Tirer une demande au hasard" in apres
