"""Brique 13 — l'écran du jury (étape 4). Testé sur faux robot, Internet coupé pour les tests (conftest.py).

Pages et API, deuxième langue des réponses du robot, bouton « Internet coupé » (qui coupe VRAIMENT une connexion
vers l'extérieur et laisse passer cet ordinateur), flux simple pour le motion design, mode silence.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import shutil
import socket
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from conftest import lancer

ICI = Path(__file__).resolve().parents[1]
CODE = {"X-Code-Equipe": "code-de-test"}


def _app(s, **kw):
    from briques.b13_ecran.serveur import creer_app

    s.reglages["ecran"]["code_equipe"] = "code-de-test"
    return creer_app(s, **kw)


def _attendre(s, condition, delai_s: float = 10.0):
    import time

    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        trouves = [e for e in list(s.bus.historique) if condition(e)]
        if trouves:
            return trouves
        time.sleep(0.02)
    raise AssertionError("événement attendu jamais arrivé")


# ---------------------------------------------------------------- la page
def test_la_page_du_jury_s_ouvre_et_ne_demande_rien_a_internet(fabrique_systeme):
    from briques.b13_ecran.flux_simple import PICTOS

    with TestClient(_app(fabrique_systeme())) as client:
        page = client.get("/jury")
        assert page.status_code == 200
        for mot in ("J'ai entendu", "J'ai compris", "Je vais faire", "Je refuse parce que", "Je pose une question",
                    "J'ai besoin d'aide", "Fiche de vérité", "testé sur faux robot", "Internet coupé", "Mode silence"):
            assert mot in page.text, mot
        assert client.get("/static/jury.js").status_code == 200
        assert client.get("/static/jury.css").status_code == 200
        assert "/jury" in client.get("/").text  # lien depuis l'écran de l'équipe
        assert "Fiche de vérité" in client.get("/").text  # l'écran de l'équipe est toujours là
        etat = client.get("/api/jury/etat").json()
        assert etat["internet_coupe"] is False and etat["silence"] is False
        assert etat["traducteur"]["disponible"] is False
    # Aucun fichier venu d'un CDN, aucune police externe : pas une seule adresse Internet dans la page.
    for nom in ("jury.html", "jury.js", "jury.css"):
        texte = (ICI / "static" / nom).read_text(encoding="utf-8")
        assert not re.search(r"https?://", texte), nom
        assert "@import" not in texte and "@font-face" not in texte, nom
    html = (ICI / "static" / "jury.html").read_text(encoding="utf-8")
    assert re.findall(r'<(?:link|script)[^>]*(?:href|src)="([^"]+)"', html) == ["/static/jury.css", "/static/jury.js"]
    # Un pictogramme SVG intégré pour chaque nom du flux simple (aller, prendre, regarder, refus, question, arrêt, aide…).
    for nom in PICTOS:
        assert f'<symbol id="p-{nom}"' in html, nom


# ---------------------------------------------------------------- deuxième langue des réponses du robot
def _session(fabrique_systeme, carte, phrases):
    async def go():
        s = fabrique_systeme(carte)
        await s.demarrer()
        for texte, langue in phrases:
            await s.chaine.traiter(texte, langue)
        await s.arreter()
        return s

    return lancer(go())


PHRASES_HUMANOIDE = [("Va à la cuisine", "fr"), ("Geh in die Küche", "de"), ("Go to the kitchen", "en"), ("去厨房", "zh"),
                     ("Vai in cucina", "it"), ("Gang i d'Chuchi", "gsw"), ("Va à la scène à 5 mètres par seconde", "fr"),
                     ("Geh zur Bühne mit 4 Meter pro Sekunde", "de"), ("va", "fr"), ("geh", "de"), ("blabla", "en"),
                     ("Regarde la table", "fr"), ("Avance un peu", "fr"), ("Batterie ?", "fr"), ("Salue", "it")]
PHRASES_BRAS = [("Va à la cuisine", "fr"), ("Prends la bouteille", "fr"), ("oui", "fr"), ("Nimm die Flasche", "de"),
                ("Nein", "de"), ("拿瓶子", "zh"), ("好的", "zh"), ("take", "en")]


def test_chaque_reponse_du_robot_porte_sa_cle_et_se_redit_a_l_identique(fabrique_systeme):
    """La clé et les valeurs redonnent EXACTEMENT le texte dit, dans la langue de la personne."""
    attendues = {"humanoide": {"annonce.se_deplacer", "annonce.regarder", "fait", "refus",
                               "repli_langue", "incompris", "question_lieu", "etat"},
                 "bras": {"confirmer", "confirmation_annulee", "annonce.saisir", "fait", "refus"}}
    for carte, phrases in (("humanoide", PHRASES_HUMANOIDE), ("bras", PHRASES_BRAS)):
        s = _session(fabrique_systeme, carte, phrases)
        reponses = [e for e in s.bus.historique if e.type == "reponse_dite"]
        assert len(reponses) > len(phrases)
        sans_cle = [e.donnees["texte"] for e in reponses if not e.donnees.get("cle")]
        assert sans_cle == []  # cerveau à règles : toutes les phrases viennent de phrases.yaml
        for e in reponses:
            d = e.donnees
            json.dumps(d["valeurs"])  # passe dans la boîte noire et le WebSocket
            assert s.chaine.redire(d["cle"], d["valeurs"], d["langue_entendue"]) == d["texte"], d
        cles = {e.donnees["cle"] for e in reponses}
        assert attendues[carte] <= cles, attendues[carte] - cles


def test_les_phrases_je_leve_la_main_portent_leur_cle_et_se_redisent_dans_la_deuxieme_langue(fabrique_systeme):
    """Relecture du lot B : les trois « je lève la main » (deux « pas compris », deux échecs, le gardien demande un
    humain) portent `cle` et `valeurs` : /jury les redit dans la 2e langue au lieu de « traduction indisponible »."""
    async def go(carte, phrases):
        s = fabrique_systeme(carte)
        s.doute.actif = True  # la main levée « il bute » allumée, quel que soit reglages.yaml
        await s.demarrer()
        for texte, langue in phrases:
            await s.chaine.traiter(texte, langue)
        await s.arreter()
        return [e.donnees for e in s.bus.historique if e.type == "reponse_dite" and e.donnees["genre"] == "main_levee"], s

    incompris, s1 = lancer(go("humanoide", [("blabla", "fr"), ("blublu", "fr"),  # deux « pas compris »
                                             ("Prends la bouteille", "it"), ("sì", "it"),  # deux échecs (trop loin)
                                             ("Prendi la bottiglia", "it"), ("sì", "it")]))
    gardien, s2 = lancer(go("bras", [("Nimm die Tasse", "de")]))  # objet fragile : le gardien demande un humain
    assert len(incompris) == 2 and len(gardien) == 1
    for s, d in [(s1, x) for x in incompris] + [(s2, x) for x in gardien]:
        assert d["cle"] == "main_levee"
        json.dumps(d["valeurs"])
        assert s.chaine.redire(d["cle"], d["valeurs"], d["langue_entendue"]) == d["texte"], d
    assert s1.chaine.redire("main_levee", incompris[0]["valeurs"], "en") == "I am raising my hand: I need help."
    assert s1.chaine.redire("main_levee", incompris[1]["valeurs"], "zh") == s1.chaine.redire("main_levee", {}, "zh")
    en_francais = s2.chaine.redire(gardien[0]["cle"], gardien[0]["valeurs"], "fr")
    assert en_francais.startswith("Je lève la main : j'ai besoin d'aide.") and "fragile : tasse" in en_francais
    assert gardien[0]["texte"].startswith("Ich hebe die Hand")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node introuvable (on n'installe rien)")
def test_le_panneau_aide_montre_l_action_et_les_raisons_du_gardien():
    """Relecture du lot B : une demande du gardien (sans `texte`) montre l'action et les raisons, pas « gardien ».
    Sans navigateur : jury.js est chargé dans Node avec un faux « document » (tests/panneau_aide.js)."""
    import subprocess

    gardien = {"type": "aide_demandee", "source": "gardien", "donnees": {
        "raison": "gardien", "numero": "ab12cd34", "action": {"nom": "saisir", "parametres": {"objet": "tasse", "force": 15}},
        "raisons": [{"code": "objet_fragile", "details": {"objet": "tasse", "objet_noms": {"fr": "tasse"}}}]}}
    doute = {"type": "aide_demandee", "source": "doute", "donnees": {
        "raison": "incompris_de_suite", "texte": "Je lève la main : j'ai besoin d'aide."}}
    sortie = subprocess.run(["node", str(ICI / "tests" / "panneau_aide.js"), str(ICI / "static" / "jury.js"),
                             json.dumps([gardien, doute])], capture_output=True, text=True, timeout=30)
    assert sortie.returncode == 0, sortie.stderr
    p_gardien, p_doute = json.loads(sortie.stdout)
    assert p_gardien["texte"] == "En attente d'un humain : prendre : tasse · 15 N"
    assert "objet fragile (tasse)" in p_gardien["detail"] and "ab12cd34" in p_gardien["detail"]
    assert "gardien" not in p_gardien["texte"]
    assert p_doute["texte"] == "Je lève la main : j'ai besoin d'aide."  # venue de la brique 8 : sa phrase, inchangée


def test_une_reponse_du_robot_redite_dans_une_autre_langue(fabrique_systeme):
    s = _session(fabrique_systeme, "bras", [("Prends la bouteille", "de"), ("Va à la cuisine", "zh"), ("take", "en")])
    rep = [e.donnees for e in s.bus.historique if e.type == "reponse_dite"]
    confirmer = next(d for d in rep if d["cle"] == "confirmer")
    assert s.chaine.redire(confirmer["cle"], confirmer["valeurs"], "fr") == "Je prends : bouteille. Vous confirmez ?"
    assert s.chaine.redire(confirmer["cle"], confirmer["valeurs"], "en") == "I am taking: bottle. Do you confirm?"
    hors_carte = next(d for d in rep if d["cle"] == "refus")
    assert "ne sait pas faire" in s.chaine.redire(hors_carte["cle"], hors_carte["valeurs"], "fr")
    question = next(d for d in rep if d["cle"].startswith("question"))
    assert s.chaine.redire(question["cle"], question["valeurs"], "it").endswith("?")


def test_l_ecran_donne_la_deuxieme_langue_et_ne_fait_pas_semblant(fabrique_systeme):
    from briques.b13_ecran.traduction import Traducteur

    s = fabrique_systeme()
    with TestClient(_app(s)) as client:
        assert client.post("/api/dire", json={"texte": "Va à la cuisine", "langue": "fr"}, headers=CODE).status_code == 200
        annonce = _attendre(s, lambda e: e.type == "reponse_dite" and e.donnees.get("genre") == "annonce")[0]
        parole = _attendre(s, lambda e: e.type == "parole_entendue")[0]
        r = client.get(f"/api/traduire/{annonce.id}", params={"langue": "de"}).json()
        assert r == {"ok": True, "texte": "Ich gehe zu: Küche.", "langue": "de", "comment": "phrase_connue"}
        assert client.get(f"/api/traduire/{annonce.id}", params={"langue": "zh"}).json()["texte"] == "我去：厨房。"
        assert client.get(f"/api/traduire/{annonce.id}", params={"langue": "fr"}).json()["comment"] == "meme_langue"
        # Ce que la PERSONNE a dit : il faudrait un modèle. Aucun n'est branché : on le dit.
        r = client.get(f"/api/traduire/{parole.id}", params={"langue": "de"}).json()
        assert r["ok"] is False and r["texte"] is None and r["message"] == "traduction indisponible hors ligne"
        assert client.get(f"/api/traduire/{parole.id}", params={"langue": "fr"}).json()["texte"] == "Va à la cuisine"
        assert client.get("/api/traduire/inconnu", params={"langue": "de"}).status_code == 404
        assert client.get(f"/api/traduire/{annonce.id}", params={"langue": "xx"}).status_code == 400

        # L'endroit prévu pour brancher plus tard une traduction par le cerveau (Apertus).
        class FauxTraducteur(Traducteur):
            nom, disponible = "faux traducteur d'essai", True

            async def traduire(self, texte, de, vers):
                return f"[{de}→{vers}] {texte}"

        client.app.state.jury.traducteur = FauxTraducteur()
        r = client.get(f"/api/traduire/{parole.id}", params={"langue": "de"}).json()
        assert r["ok"] and r["texte"] == "[fr→de] Va à la cuisine" and "faux traducteur" in r["comment"]


# ---------------------------------------------------------------- Internet coupé
def test_adresses_locales_permises_internet_refuse():
    from briques.b13_ecran.internet import adresse_permise, nom_local

    for a in ("127.0.0.1", "::1", "localhost", "192.168.1.20", "10.0.0.5", "172.16.3.4", "fe80::1%en0", "fd12::4",
              "0.0.0.0", "::ffff:192.168.1.9", "imac.local", "imac"):
        assert adresse_permise(a), a
    for a in ("1.1.1.1", "8.8.8.8", "2a00:1450:4001::1", "api.inference.cscs.ch", "example.com", "::ffff:8.8.8.8", None):
        assert not adresse_permise(a), a
    assert nom_local("Mac-de-Hiba.local.") and not nom_local("huggingface.co")


def _connexion_exterieure():
    """Ouvre une vraie connexion TCP vers une adresse d'Internet (sans passer par la recherche de nom)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect(("1.1.1.1", 443))
    finally:
        s.close()


def test_le_bouton_internet_coupe_coupe_vraiment_et_laisse_passer_cet_ordinateur(fabrique_systeme, monkeypatch):
    import httpx

    from briques.b12_boite_noire.journal import lire
    from briques.b13_ecran.internet import InternetCoupe, NomRefuse

    s = fabrique_systeme()
    serveur_local = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveur_local.bind(("127.0.0.1", 0))
    serveur_local.listen()
    port = serveur_local.getsockname()[1]
    mandataire = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # un faux « proxy » sur cet ordinateur
    mandataire.bind(("127.0.0.1", 0))
    mandataire.listen()
    monkeypatch.setenv("ALL_PROXY", f"http://127.0.0.1:{mandataire.getsockname()[1]}")
    try:
        with TestClient(_app(s)) as client:
            assert client.post("/api/internet_coupe", json={"coupe": True}).status_code == 403  # sans code
            r = client.post("/api/internet_coupe", json={"coupe": True}, headers=CODE).json()
            assert r["internet_coupe"] is True and "refusée avant de partir" in r["preuve"]

            # Vers l'extérieur : refusé par NOTRE coupure (avant même la protection des tests).
            with pytest.raises(InternetCoupe, match="Internet coupé"):
                _connexion_exterieure()
            with pytest.raises(NomRefuse, match="Internet coupé"):
                socket.getaddrinfo("example.com", 443)
            with pytest.raises(httpx.ConnectError, match="Internet coupé"):
                httpx.get("https://example.com/", timeout=2, trust_env=False)
            # Un mandataire (proxy) mène à Internet même s'il est sur cet ordinateur : refusé aussi.
            with pytest.raises(InternetCoupe, match="mandataire"):
                socket.create_connection(mandataire.getsockname(), timeout=2)
            with pytest.raises(httpx.ConnectError, match="Internet coupé"):
                httpx.get("https://example.com/", timeout=2)  # avec ou sans mandataire déclaré
            etat = client.get("/api/jury/etat").json()
            assert etat["connexions_refusees"] >= 4 and f"127.0.0.1:{mandataire.getsockname()[1]}" in etat["mandataires_coupes"]

            # Cet ordinateur : passe toujours.
            c = socket.create_connection(("127.0.0.1", port), timeout=2)
            c.close()
            assert socket.getaddrinfo("localhost", port)

            # Et tout continue : le robot comprend, le gardien vérifie, le faux robot agit.
            assert client.post("/api/dire", json={"texte": "Va à la cuisine", "langue": "fr"}, headers=CODE).status_code == 200
            _attendre(s, lambda e: e.type == "action_terminee" and e.donnees.get("statut") == "reussie")

            # Un second clic rétablit.
            r = client.post("/api/internet_coupe", json={"coupe": False}, headers=CODE).json()
            assert r["internet_coupe"] is False
            with pytest.raises(OSError) as erreur:
                _connexion_exterieure()
            assert not isinstance(erreur.value, InternetCoupe)  # c'est de nouveau la protection des tests qui refuse
    finally:
        serveur_local.close()
        mandataire.close()
    notes = [e for e in lire(s.boite_noire.fichier) if e.type == "internet_coupe"]  # dans la boîte noire
    assert [e.donnees["coupe"] for e in notes] == [True, False]
    assert notes[1].donnees["connexions_refusees"] >= 3


def test_le_reseau_local_en_plus_et_la_liste_toujours_permis():
    """Relecture du lot B : 100.64.0.0/10 (Tailscale…), .home, .fritz.box… sont locaux ; la liste « toujours permis »
    de reglages.yaml (le robot, l'autre Mac) passe toujours. gethostbyname, gethostbyname_ex, gethostbyaddr : coupés."""
    from briques.b13_ecran.internet import Coupure, InternetCoupe, NomRefuse, adresse_permise

    for a in ("100.64.0.1", "100.101.102.103", "100.127.255.254", "box.fritz.box", "nas.home", "imac.lan",
              "mac.home.arpa", "robot", "imac.local"):
        assert adresse_permise(a), a
    for a in ("100.128.0.1", "100.63.255.255", "fritz.box.exemple.org", "home.exemple.org"):
        assert not adresse_permise(a), a
    c = Coupure(toujours_permis=["203.0.113.7", "robot.exemple.org", "198.51.100.0/24", "http://Autre-Mac.Exemple.ORG:8000/"])
    assert c.toujours("203.0.113.7") and c.toujours("198.51.100.42") and c.toujours("robot.exemple.org.")
    assert c.toujours("autre-mac.exemple.org") and not c.toujours("8.8.8.8") and not c.toujours("exemple.org")
    assert Coupure(toujours_permis="robot.exemple.org").toujours_permis == ["robot.exemple.org"]  # un texte seul
    originaux = (socket.gethostbyname, socket.gethostbyname_ex, socket.gethostbyaddr, socket.getaddrinfo)
    c.couper()
    try:
        # Toujours permis : NOTRE coupure laisse passer (derrière, c'est la protection des tests qui refuse).
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError) as erreur:
                s.connect(("203.0.113.7", 443))
            assert not isinstance(erreur.value, InternetCoupe)
        finally:
            s.close()
        with pytest.raises(socket.gaierror) as erreur:
            socket.getaddrinfo("robot.exemple.org", 80)
        assert not isinstance(erreur.value, NomRefuse)
        with pytest.raises(InternetCoupe):
            _connexion_exterieure()  # 1.1.1.1 : pas dans la liste, refusé
        # Les vieilles fonctions de recherche de nom sont coupées aussi.
        with pytest.raises(NomRefuse):
            socket.gethostbyname("example.com")
        with pytest.raises(NomRefuse):
            socket.gethostbyname_ex("example.com")
        with pytest.raises(NomRefuse):
            socket.gethostbyaddr("8.8.8.8")
        assert socket.gethostbyname("localhost") == "127.0.0.1"  # cet ordinateur : permis
        assert "127.0.0.1" in socket.gethostbyname_ex("localhost")[2]
    finally:
        c.retablir()
    assert (socket.gethostbyname, socket.gethostbyname_ex, socket.gethostbyaddr, socket.getaddrinfo) == originaux


def test_arret_d_urgence_et_rearmement_marchent_pendant_la_coupure(fabrique_systeme):
    """Relecture du lot B : « Internet coupé » n'empêche jamais l'ARRÊT d'urgence ni le réarmement. Faux robot."""
    s = fabrique_systeme("humanoide", 2.0)  # lent : le robot roule encore quand on appuie sur ARRÊT
    s.reglages["ecran"]["internet_coupe"] = {"toujours_permis": ["robot-g1", "192.168.8.20"]}
    with TestClient(_app(s)) as client:
        r = client.post("/api/internet_coupe", json={"coupe": True}, headers=CODE).json()
        assert r["internet_coupe"] is True and r["toujours_permis"] == ["robot-g1", "192.168.8.20"]
        client.post("/api/dire", json={"texte": "Va à la cuisine", "langue": "fr"}, headers=CODE)
        _attendre(s, lambda e: e.type == "action_demarree")
        assert client.post("/api/arret_urgence").json()["ok"] is True  # ouvert à tous, sans code
        _attendre(s, lambda e: e.type == "arret_urgence")
        _attendre(s, lambda e: e.type == "action_terminee")
        assert client.get("/api/etat").json()["en_mouvement"] is False
        assert client.post("/api/rearmer", headers=CODE).json()["ok"] is True
        _attendre(s, lambda e: e.type == "reparation" and e.donnees.get("quoi") == "rearmement")
        client.post("/api/dire", json={"texte": "Regarde la table", "langue": "fr"}, headers=CODE)
        _attendre(s, lambda e: e.type == "action_terminee" and e.donnees.get("statut") == "reussie")
        assert client.get("/api/jury/etat").json()["internet_coupe"] is True  # coupé du début à la fin
        client.post("/api/internet_coupe", json={"coupe": False}, headers=CODE)


def test_internet_coupe_eteint_l_etage_apertus_par_internet(reglages, tmp_path):
    from commun.systeme import Systeme

    r = {**reglages, "ecran": {**reglages["ecran"]}, "robot": {**reglages["robot"], "carte": "humanoide"},
         "cerveau": {"choix": "cascade", "seuil_confiance": 0.5, "serveurs": {}, "cascade": [{"nom": "regles"}],
                     "internet": {"actif": True, "url": "https://api.inference.cscs.ch/v1", "modele": "essai",
                                  "formulaire": "json_schema", "delai_s": 4}}}
    s = Systeme(r, dossier_journal=tmp_path / "journal", acceleration=20)
    etage = s.cerveau.etages[0]
    assert etage.cerveau.nom == "apertus_internet"
    with TestClient(_app(s)) as client:
        r = client.post("/api/internet_coupe", json={"coupe": True}, headers=CODE).json()
        assert r["etages_eteints"] == ["apertus_internet"] and etage.en_pause_jusqua == math.inf
        assert client.post("/api/dire", json={"texte": "Regarde la table", "langue": "fr"}, headers=CODE).status_code == 200
        compris = _attendre(s, lambda e: e.type == "demande_comprise")[0]
        assert compris.donnees["duree_ms"] < 1000  # le cerveau à règles répond tout de suite, sans attendre 4 s
        assert not [e for e in s.bus.historique if e.type == "cerveau_secours"]  # l'étage Internet n'a même pas été essayé
        client.post("/api/internet_coupe", json={"coupe": False}, headers=CODE)
        assert etage.en_pause_jusqua == 0.0
        fin = [e for e in s.bus.historique if e.type == "internet_coupe"][-1]
        assert fin.donnees["etages_rallumes"] == ["apertus_internet"]


# ---------------------------------------------------------------- flux simple (motion design)
def test_le_flux_simple_une_ligne_par_evenement(fabrique_systeme):
    from briques.b13_ecran.flux_simple import PICTOS

    s = fabrique_systeme()
    with TestClient(_app(s)) as client:
        for texte in ("Regarde la table", "Va à la scène à 5 mètres par seconde", "va"):
            client.post("/api/dire", json={"texte": texte, "langue": "fr"}, headers=CODE)
            _attendre(s, lambda e, t=texte: e.type == "parole_entendue" and e.donnees["texte"] == t)
        client.post("/api/arret_urgence")
        _attendre(s, lambda e: e.type == "arret_urgence")
        lignes = [json.loads(x) for x in client.get("/api/flux_simple", params={"historique": 500, "direct": 0}).text.splitlines()]
        assert len(lignes) >= 15
        for ligne in lignes:
            assert set(ligne) == {"numero", "heure", "heure_locale", "type", "langue", "texte", "picto", "conversation",
                                  "robot", "id"}
            assert ligne["picto"] in PICTOS or ligne["picto"] == ""
            assert isinstance(ligne["texte"], str) and len(ligne["texte"]) <= 160
        par_type = {}
        for ligne in lignes:
            par_type.setdefault(ligne["type"], []).append(ligne)
        premiere = par_type["parole_entendue"][0]
        assert (premiere["texte"], premiere["langue"], premiere["picto"]) == ("Regarde la table", "fr", "entendu")
        assert par_type["demande_comprise"][0]["picto"] == "regarder"
        assert any(x["picto"] == "refus" and "sécurité" in x["texte"] for x in par_type["reponse_dite"])
        assert any(x["picto"] == "question" for x in par_type["reponse_dite"])
        assert par_type["arret_urgence"][0]["picto"] == "arret"
        # Filtrer : seulement certains types, ou tous sauf certains ; s'arrêter après N lignes.
        seul = client.get("/api/flux_simple", params={"types": "reponse_dite", "historique": 500, "direct": 0}).text
        assert {json.loads(x)["type"] for x in seul.splitlines()} == {"reponse_dite"}
        sans = client.get("/api/flux_simple", params={"sans": "action_progression,reponse_dite", "historique": 500,
                                                       "direct": 0}).text
        assert not {"action_progression", "reponse_dite"} & {json.loads(x)["type"] for x in sans.splitlines()}
        assert len(client.get("/api/flux_simple", params={"historique": 500, "max": 3}).text.splitlines()) == 3

        # En direct par WebSocket (simple, puis complet pour la page du jury).
        client.post("/api/rearmer", headers=CODE)
        with client.websocket_connect("/ws_simple?historique=0&types=demande_comprise,reponse_dite") as ws:
            client.post("/api/dire", json={"texte": "Salue", "langue": "fr"}, headers=CODE)
            premier = ws.receive_json()
            assert premier["type"] == "demande_comprise" and premier["picto"] == "geste"
            assert ws.receive_json()["type"] == "reponse_dite"
        with client.websocket_connect("/ws_simple?historique=3&complet=1") as ws:
            m = ws.receive_json()
            assert {"donnees", "source", "simple"} <= set(m) and m["simple"]["type"] == m["type"]


def test_le_flux_simple_sait_lire_tous_les_types_d_evenements():
    from briques.b13_ecran.flux_simple import ligne_simple
    from commun.evenements import TYPES, Evenement

    for t in TYPES:
        vide = ligne_simple(Evenement(type=t, source="test").model_dump(mode="json"))
        assert vide["type"] == t and isinstance(vide["texte"], str)
    ligne = ligne_simple({"type": "internet_coupe", "donnees": {"coupe": True}, "heure": "2026-11-14T10:00:00+00:00"})
    assert ligne["texte"] == "Internet coupé — tout continue" and ligne["picto"] == "internet" and ligne["heure_locale"]


def test_la_doc_du_flux_montre_chaque_type_et_chaque_picto():
    from briques.b13_ecran.flux_simple import PICTOS
    from commun.evenements import TYPES

    doc = (ICI / "FLUX_POUR_MOTION_DESIGN.md").read_text(encoding="utf-8")
    for t in TYPES:
        assert f"### `{t}`" in doc, t
    for p in PICTOS:
        assert f"`{p}`" in doc, p
    for bloc in re.findall(r"```json\n(.*?)```", doc, flags=re.S):
        for ligne in bloc.strip().splitlines():
            json.loads(ligne)  # chaque exemple est du JSON valable


# ---------------------------------------------------------------- mode silence
def test_le_mode_silence_est_protege_et_note(fabrique_systeme):
    s = fabrique_systeme()
    with TestClient(_app(s)) as client:
        assert client.post("/api/mode_silence", json={"actif": True}).status_code == 403
        assert client.post("/api/mode_silence", json={"actif": True}, headers=CODE).json()["silence"] is True
        assert client.get("/api/jury/etat").json()["silence"] is True
        assert client.post("/api/mode_silence", json={"actif": False}, headers=CODE).json()["silence"] is False
    assert [e.donnees["actif"] for e in s.bus.historique if e.type == "mode_silence"] == [True, False]


def test_le_mode_silence_suit_l_interrupteur_des_reglages(fabrique_systeme):
    s = fabrique_systeme()
    s.reglages["interrupteurs"] = {**s.reglages.get("interrupteurs", {}), "mode_silence": {"actif": True}}
    with TestClient(_app(s)) as client:
        assert client.get("/api/jury/etat").json()["silence"] is True


def test_le_mode_silence_met_la_voix_en_sous_titres_seulement(fabrique_systeme):
    from briques.b04_oreilles_voix.conversation import Conversation
    from briques.b04_oreilles_voix.peripheriques import HautParleurFactice
    from briques.b04_oreilles_voix.voix import Son, VoixTexte
    from briques.b13_ecran.jury import Jury

    class VoixQuiParle:
        nom = "voix d'essai"

        def synthetiser(self, texte, langue, lent=False):
            return Son(echantillons=np.zeros(1600, dtype="float32"), taux=16000, moteur=self.nom)

    async def go():
        s = fabrique_systeme()
        voix = VoixQuiParle()
        conv = Conversation(s, None, voix, HautParleurFactice(vitesse=50), s.reglages.get("voix", {}))
        jury = Jury(s, conv)
        await s.chaine.repondre("Bonjour", "fr", "c1")
        await conv.attendre_calme(10)
        await jury.mode_silence(True)
        assert isinstance(conv.voix, VoixTexte)
        await s.chaine.repondre("Je vais à : cuisine.", "fr", "c2")
        await conv.attendre_calme(10)
        await jury.mode_silence(False)
        assert conv.voix is voix  # la voix normale revient
        await s.chaine.repondre("C'est fait.", "fr", "c3")
        await conv.attendre_calme(10)
        conv.fermer()
        await asyncio.sleep(0)
        return [e.donnees["sous_titres_seulement"] for e in s.bus.historique if e.type == "voix_debut"]

    assert lancer(go()) == [False, True, False]
