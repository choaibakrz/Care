"""Brique 11 — la main humaine. Testé sur faux robot, cerveau à règles, Internet coupé (conftest.py).

Prendre et rendre la main ; pendant la main humaine, la voix, la tablette et les agents sont ignorés (réponse polie),
sauf « stop » ; les ordres de l'humain passent par le gardien (un ordre trop rapide est refusé et expliqué) ;
boutons refusés sans le code d'équipe (sauf ARRÊT) ; la fiche de vérité compte la part de l'humain ; le panneau des
demandes à un humain ; le chef de démonstration passe la main à l'écran ; l'écran du jury dit qui pilote.
"""
from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from briques.b11_main_humaine.main_humaine import MainHumaine, Refus, nettoyer
from commun.phrases import dire
from conftest import lancer

ICI = Path(__file__).resolve().parents[1]
CODE = {"X-Code-Equipe": "code-de-test"}


@pytest.fixture
def systeme(tmp_path, reglages):
    """Un Système complet (faux robot, cerveau à règles), code d'équipe, mots appris dans tmp_path."""
    from commun.systeme import Systeme

    def fabrique(carte: str = "humanoide", acceleration: float = 20.0, vote: bool = False):
        inter = dict(reglages.get("interrupteurs") or {})
        inter["vote_public"] = {"actif": vote}
        r = {**reglages, "robot": {**reglages["robot"], "carte": carte},
             "ecran": {**reglages["ecran"], "code_equipe": "code-de-test"},
             "cerveau": {**reglages["cerveau"], "choix": "regles"}, "interrupteurs": inter,
             "doute": {"aides_apprises": str(tmp_path / "aides_apprises.yaml")}}
        return Systeme(r, dossier_journal=tmp_path / "journal", acceleration=acceleration)

    return fabrique


def _app(s):
    from briques.b13_ecran.serveur import creer_app

    return creer_app(s)


def _evs(s, type_, conversation=None):
    return [e for e in list(s.bus.historique) if e.type == type_ and (conversation is None or e.conversation == conversation)]


def _attendre(s, condition, delai_s: float = 10.0):
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        trouves = [e for e in list(s.bus.historique) if condition(e)]
        if trouves:
            return trouves
        time.sleep(0.02)
    raise AssertionError("événement attendu jamais arrivé")


async def _attendre_fin(s, conversation, delai_s: float = 10.0):
    fin = time.monotonic() + delai_s
    while time.monotonic() < fin:
        e = _evs(s, "action_terminee", conversation)
        if e:
            return e[-1]
        await asyncio.sleep(0.02)
    raise AssertionError("action jamais finie")


def _rien_ne_contourne_le_gardien(s):
    """Chaque action partie vers le robot a d'abord reçu le « oui » du gardien, dans la même conversation."""
    oui = {e.conversation for e in _evs(s, "gardien_decision") if e.donnees["verdict"] == "oui"}
    assert _evs(s, "action_demarree") and all(e.conversation in oui for e in _evs(s, "action_demarree"))


# ---------------------------------------------------------------- prendre et rendre la main
def test_prendre_puis_rendre_la_main(systeme):
    s = systeme()
    with TestClient(_app(s)) as c:
        assert c.get("/api/main_humaine").json()["qui"] is None
        r = c.post("/api/main_humaine/prendre", json={"qui": "Hiba"}, headers=CODE)
        assert r.status_code == 200 and r.json()["qui"] == "Hiba" and s.chaine.pilote_humain == "Hiba"
        jeton = r.json()["jeton"]
        assert r.json()["a_moi"] is True and len(jeton) >= 20
        # Un seul humain à la fois : une autre personne (ou la même, d'une autre tablette) doit attendre.
        for qui in ("Luca", "Hiba"):
            autre = c.post("/api/main_humaine/prendre", json={"qui": qui}, headers=CODE)
            assert autre.status_code == 409 and "Hiba a déjà la main" in autre.json()["detail"]
        assert c.get("/api/main_humaine?court=1").json()["qui"] == "Hiba"
        r = c.post("/api/main_humaine/rendre", json={"qui": "Hiba", "jeton": jeton}, headers=CODE).json()
        assert r["qui"] is None and s.chaine.pilote_humain is None
        assert c.post("/api/main_humaine/rendre", json={}, headers=CODE).json()["qui"] is None  # rien à rendre : rien
        # Tout est comme avant : une phrase fait de nouveau agir le robot (toujours par le gardien).
        assert c.post("/api/dire", json={"texte": "Va à la table", "langue": "fr"}, headers=CODE).json()["verdict"] == "oui"
    pilotage = _evs(s, "pilotage_humain")
    assert [(e.donnees["quoi"], e.donnees["qui"], e.source) for e in pilotage] == [
        ("reprise", "Hiba", "main_humaine"), ("rendu", "Hiba", "main_humaine")]
    assert pilotage[0].donnees["mention"] == "testé sur faux robot"
    assert pilotage[1].donnees["ordres"] == 0 and pilotage[1].donnees["duree_s"] >= 0 and pilotage[1].donnees["force"] is False
    # En prenant la main, un arrêt normal est TOUJOURS parti, par le gardien (au nom de l'humain).
    arret = pilotage[0].conversation
    assert pilotage[0].donnees["arret_envoye"] is True and arret
    assert [(e.donnees["verdict"], e.donnees["action"]["nom"], e.donnees["demandeur"])
            for e in _evs(s, "gardien_decision", arret)] == [("oui", "arreter", "humain:Hiba")]
    assert [e.donnees["action"]["nom"] for e in _evs(s, "action_demarree", arret)] == ["arreter"]
    # Le jeton ne va jamais dans la boîte noire.
    assert jeton not in " ".join(e.model_dump_json() for e in s.bus.historique)


def test_la_voix_la_tablette_et_les_agents_sont_ignores_sauf_stop(systeme):
    from briques.b14_porte_agents.porte import PorteDesAgents

    s = systeme(acceleration=5)

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            avant = await s.chaine.traiter("Prends la bouteille", "fr", source="micro")
            assert avant.reponses[-1].endswith("Vous confirmez ?")  # une action à risque attend un « oui »
            jeton = (await main.prendre("Hiba"))["jeton"]
            await asyncio.sleep(0.2)  # l'arrêt envoyé en prenant la main finit
            arret = _evs(s, "pilotage_humain")[-1].conversation
            n = len(s.bus.historique)
            for texte, langue, source in [("oui", "fr", "micro"), ("Va à la cuisine", "fr", "micro"),
                                          ("Geh zum Tisch", "de", "micro"), ("Gang zum Tisch", "gsw", "micro"),
                                          ("Go to the stage", "en", "agent:assistant"), ("Va à l'entrée", "fr", "clavier")]:
                r = await s.chaine.traiter(texte, langue, source=source)
                assert r.reponses == [dire("humain_pilote", langue)], (texte, r.reponses)
                assert r.verdict is None and r.action is None
            agent = await PorteDesAgents(s, "assistant").dire("Va à la table", "fr")
            assert agent["statut"] == "humain_pilote" and "humain pilote" in agent["explication"]
            # Ni le cerveau, ni le gardien, ni le robot n'ont rien reçu de ces phrases.
            apres = [e for e in s.bus.historique[n:] if e.conversation != arret]
            assert not [e for e in apres if e.type in ("demande_comprise", "gardien_decision", "action_demarree")]
            assert [e.donnees["cle"] for e in apres if e.type == "reponse_dite"] == ["humain_pilote"] * 7
            # L'humain lance un déplacement ; « stop » à la voix passe quand même, et arrête le robot.
            o = await main.ordre("se_deplacer", {"lieu": "scene"}, jeton)
            assert o["sorte"] == "parti"
            stop = await s.chaine.traiter("stop", "fr", source="micro")
            assert stop.verdict == "oui" and stop.action.nom == "arreter"
            assert (await _attendre_fin(s, o["conversation"])).donnees["statut"] == "annulee"
            await main.rendre(jeton)
            # Le « oui » d'avant a été oublié quand l'humain a pris la main : rien n'est pris.
            await s.chaine.traiter("oui", "fr", source="micro")
            await asyncio.sleep(0.2)
        finally:
            await s.arreter()
        assert not [e for e in _evs(s, "action_demarree") if e.donnees["action"]["nom"] == "saisir"]
        _rien_ne_contourne_le_gardien(s)

    lancer(go())


def test_les_ordres_de_l_humain_passent_par_le_gardien(systeme):
    s = systeme()
    with TestClient(_app(s)) as c:
        sans_main = c.post("/api/main_humaine/ordre", json={"nom": "se_deplacer", "parametres": {"lieu": "table"}},
                           headers=CODE)
        assert sans_main.status_code == 409 and "Prenez d'abord la main" in sans_main.json()["detail"]
        j = c.post("/api/main_humaine/prendre", json={"qui": "Hiba"}, headers=CODE).json()["jeton"]
        # Sans le jeton de la tablette qui a pris la main : refusé avant le gardien.
        for faux in ({}, {"jeton": "pas-le-bon"}):
            r = c.post("/api/main_humaine/ordre", json={"nom": "etat", **faux}, headers=CODE)
            assert r.status_code == 409 and "autre tablette" in r.json()["detail"]
        # Trop rapide : le gardien refuse, et l'écran reçoit l'explication (dans la langue choisie).
        trop = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "se_deplacer", "parametres": {"dx": "1", "vitesse": "2,0"}},
                      headers=CODE).json()
        assert trop["sorte"] == "refuse" and trop["verdict"] == "non" and trop["ok"] is False
        assert "la limite de sécurité est 0.3" in trop["reponses"][0]
        de = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "se_deplacer", "parametres": {"dx": 1, "vitesse": 5},
                                                     "langue": "de"}, headers=CODE).json()
        assert de["sorte"] == "refuse" and "Sicherheitsgrenze" in de["reponses"][0]
        bon = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "se_deplacer", "parametres": {"lieu": "table"}},
                     headers=CODE).json()
        assert bon["sorte"] == "parti" and bon["reponses"] == ["Je vais à : table."]
        _attendre(s, lambda e: e.type == "action_terminee" and e.conversation == bon["conversation"])
        fragile = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "saisir", "parametres": {"objet": "tasse"}},
                         headers=CODE).json()
        assert fragile["sorte"] == "humain" and fragile["numero_demande"]  # le gardien demande un humain, même ici
        inconnu = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "voler", "parametres": {}}, headers=CODE).json()
        assert inconnu["sorte"] == "refuse"
        assert c.get("/api/main_humaine").json()["ordres"] == 5
        c.post("/api/main_humaine/rendre", json={"qui": "Hiba", "jeton": j}, headers=CODE)
    for r in (trop, de, bon, fragile, inconnu):
        decisions = _evs(s, "gardien_decision", r["conversation"])
        assert decisions and all(e.donnees["demandeur"] == "humain:Hiba" for e in decisions), r
        assert [e.donnees["quoi"] for e in _evs(s, "pilotage_humain", r["conversation"])] == ["ordre"]
    for r in (trop, de, fragile, inconnu):
        assert not _evs(s, "action_demarree", r["conversation"])  # refusé : rien n'est parti vers le robot
    _rien_ne_contourne_le_gardien(s)


def test_les_boutons_ne_montrent_que_les_actions_de_la_carte(systeme):
    s = systeme("bras")
    with TestClient(_app(s)) as c:
        actions = {a["nom"]: a for a in c.get("/api/main_humaine").json()["actions"]}
        assert set(actions) == set(s.prise.carte().capacites) and "se_deplacer" not in actions
        gestes = next(p for p in actions["rejouer_geste"]["parametres"] if p["nom"] == "nom")["choix"]
        assert [g["valeur"] for g in gestes] == s.prise.carte().gestes
        j = c.post("/api/main_humaine/prendre", json={"qui": "Hiba"}, headers=CODE).json()["jeton"]
        r = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "se_deplacer", "parametres": {"dx": 0.2}},
                   headers=CODE).json()
        assert r["sorte"] == "refuse" and "ne sait pas faire" in r["reponses"][0]  # le gardien l'explique aussi


def test_les_precisions_des_boutons_sont_lues_simplement():
    assert nettoyer("se_deplacer", {"lieu": "", "dx": "0,5", "dy": None, "vitesse": " 0.2 "}) == {"dx": 0.5, "vitesse": 0.2}
    assert nettoyer("se_deplacer", {"dx": "beaucoup"}) == {"dx": "beaucoup"}  # le gardien dira « pas clair »
    assert nettoyer("se_deplacer", {"dx": "nan"}) == {"dx": "nan"}  # pas un vrai nombre : laissé au gardien
    assert nettoyer("parler", {"texte": "  Bonjour  "}) == {"texte": "Bonjour"}


# ---------------------------------------------------------------- le code d'équipe
def test_acces_refuse_sans_code_sauf_l_arret(systeme):
    s = systeme()
    with TestClient(_app(s)) as c:
        boutons = [("/api/main_humaine/prendre", {"qui": "Intrus"}), ("/api/main_humaine/rendre", {}),
                   ("/api/main_humaine/ordre", {"nom": "etat"}), ("/api/aide/repondre", {"numero": "x", "accepte": True}),
                   ("/api/aide/apprendre", {"mot": "frigo", "langue": "fr", "sens": "cuisine"}),
                   ("/api/gardien/vote", {"vote": "vitesse", "resultats": {"plus_lent": 1}})]
        for chemin, corps in boutons:
            assert c.post(chemin, json=corps).status_code == 403, chemin
            assert c.post(chemin, json=corps, headers={"X-Code-Equipe": "faux"}).status_code == 403, chemin
            # Une page venue d'un autre site est refusée, même avec le bon code.
            assert c.post(chemin, json=corps, headers={**CODE, "Origin": "http://ailleurs.example"}).status_code == 403
        assert s.chaine.pilote_humain is None and not _evs(s, "pilotage_humain")
        assert c.post("/api/arret_urgence").status_code == 200  # ARRÊT : ouvert à tous, toujours
        assert c.get("/api/main_humaine").status_code == 200  # lire : ouvert (comme /api/aides)
    assert _evs(s, "arret_urgence")


# ---------------------------------------------------------------- la fiche de vérité
def test_la_fiche_compte_la_part_de_l_humain(systeme):
    from briques.b12_boite_noire.fiche import calculer
    from briques.b12_boite_noire.journal import lire as lire_journal

    s = systeme()

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            await s.chaine.traiter("Regarde la table", "fr")  # le robot seul
            await asyncio.sleep(0.3)
            jeton = (await main.prendre("Hiba"))["jeton"]
            o = await main.ordre("regarder", {"cible": "scene"}, jeton)
            await _attendre_fin(s, o["conversation"])
            await asyncio.sleep(0.3)
            await main.rendre(jeton)
            await asyncio.sleep(0.3)
            await s.chaine.traiter("Regarde l'entrée", "fr")  # de nouveau le robot seul
        finally:
            await s.arreter()

    lancer(go())
    f = s.compteur.fiche()
    assert 20 < f.part_humain_pct < 80, f.part_humain_pct
    # 3 réussites : la table et l'entrée (le robot seul), la scène (l'humain). L'arrêt envoyé en prenant la main
    # n'est PAS une réussite du robot.
    assert f.ordres_humains == 1 and f.reussites_pilotees == 1 and f.reussites == 3
    arrets = [e.donnees["statut"] for e in _evs(s, "action_terminee") if e.donnees["action"]["nom"] == "arreter"]
    assert arrets == ["reussie"]
    assert f.mention == "testé sur faux robot"
    # La même fiche après coup, depuis les seuls événements, et depuis le fichier de la boîte noire (rejeu).
    for g in (calculer(s.bus.historique), calculer(lire_journal(s.boite_noire.fichier))):
        assert (g.part_humain_pct, g.ordres_humains, g.reussites_pilotees) == (f.part_humain_pct, 1, 1)


# ---------------------------------------------------------------- le panneau des demandes à un humain
def test_le_panneau_des_demandes_a_un_humain(systeme):
    s = systeme(vote=True)
    with TestClient(_app(s)) as c:
        c.post("/api/dire", json={"texte": "Prends la tasse", "langue": "fr"}, headers=CODE)
        _attendre(s, lambda e: e.type == "aide_demandee")
        e = c.get("/api/main_humaine").json()
        d = e["demandes"][0]
        assert d["action_texte"].startswith("prendre : tasse") and "fragile" in d["raisons_texte"]
        assert 0 < d["reste_s"] <= 120 and d["demandeur_texte"] == "une phrase (voix ou tablette)"
        assert c.post("/api/aide/repondre", json={"numero": d["numero"], "accepte": True}).status_code == 403
        r = c.post("/api/aide/repondre", json={"numero": d["numero"], "accepte": True, "qui": "Hiba"}, headers=CODE).json()
        assert r["ok"] and r["resultat"]["verdict"] == "oui"  # le gardien a tout revérifié avant le ticket
        _attendre(s, lambda x: x.type == "action_terminee" and x.donnees["action"]["nom"] == "saisir")
        assert c.get("/api/main_humaine").json()["demandes"] == []
        # Deuxième demande, refusée par l'humain : rien ne part.
        c.post("/api/dire", json={"texte": "Prends la tasse", "langue": "fr"}, headers=CODE)
        _attendre(s, lambda x: x.type == "aide_demandee" and x.donnees.get("numero") not in (None, d["numero"]))
        d2 = c.get("/api/main_humaine").json()["demandes"][0]
        r = c.post("/api/aide/repondre", json={"numero": d2["numero"], "accepte": False, "qui": "Hiba"}, headers=CODE).json()
        assert r["resultat"]["verdict"] == "non" and not _evs(s, "action_demarree", d2["conversation"])
        # Apprendre un mot : « frigo » = cuisine.
        r = c.post("/api/aide/apprendre", json={"mot": "frigo", "langue": "fr", "sens": "cuisine", "qui": "Hiba"},
                   headers=CODE).json()
        assert r["ok"] is True
        e = c.get("/api/main_humaine").json()
        assert any(m["mot"] == "frigo" and m["sens"] == "cuisine" for m in e["mots_appris"])
        assert {"valeur": "cuisine", "texte": "cuisine"} in e["sens_possibles"]
        # Le vote du public : montré seulement quand l'interrupteur est allumé.
        assert e["vote_public"] is True and [v["id"] for v in e["votes"]] == ["vitesse", "service"]
        v = c.post("/api/gardien/vote", json={"vote": "vitesse", "resultats": {"plus_lent": 5, "comme_avant": 2}},
                   headers=CODE).json()
        assert v["ok"] and v["change"] and "0,2" in v["phrase"]
        # La page de l'équipe charge le morceau de la brique 11 (servi par cet ordinateur, rien d'Internet).
        page = c.get("/").text
        assert "/main_humaine/main_humaine.js" in page and "/main_humaine/main_humaine.css" in page
        js = c.get("/main_humaine/main_humaine.js").text
        for mot in ("Je prends la main", "Je rends la main", "Demandes à un humain", "Accepter", "Refuser",
                    "Apprendre un mot", "Vote du public", "/api/aide/repondre", "/api/aide/apprendre", "/api/gardien/vote"):
            assert mot in js, mot
        assert c.get("/main_humaine/main_humaine.css").status_code == 200
    _rien_ne_contourne_le_gardien(s)


def test_sans_vote_du_public_le_panneau_n_en_montre_pas(systeme):
    s = systeme(vote=False)
    with TestClient(_app(s)) as c:
        e = c.get("/api/main_humaine").json()
        assert e["vote_public"] is False and e["votes"] == []


# ---------------------------------------------------------------- le chef de démonstration (brique 15)
def _petit(*etapes):
    from briques.b15_chef_demo.scenario import lire

    return lire({"titre": "petit essai", "plan_b": ["main_humaine", "sauter"], "etapes": list(etapes)})


def test_le_chef_passe_la_main_a_l_ecran_puis_la_reprend(systeme):
    from briques.b15_chef_demo.chef import ChefDemo, OperateurEcran

    s = systeme(acceleration=60)
    sc = _petit({"nom": "saluer", "dire": "Salue", "attendu": {"action": "rejouer_geste"}},
                {"nom": "suite", "dire": "Applaudis", "attendu": {"action": "rejouer_geste"}})

    async def humain(main: MainHumaine):
        """Une personne devant l'écran : elle lit la consigne, prend la main, donne un ordre, la rend (« fait »)."""
        while main.consigne is None:
            await asyncio.sleep(0.02)
        assert "Salue" in main.consigne["texte"]
        jeton = (await main.prendre("Hiba"))["jeton"]
        r = await main.ordre("rejouer_geste", {"nom": "saluer"}, jeton)
        assert r["verdict"] == "oui"  # le gardien dit oui… et le robot en panne refuse (la prise le dit)
        await main.rendre(jeton, fait=True)

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            chef = ChefDemo(s, sc, repetition=True, acceleration=60, pannes={1: "robot"}, operateur=OperateurEcran(main))
            res, _ = await asyncio.gather(chef.jouer(), humain(main))
            return res
        finally:
            await s.arreter()

    res = lancer(go())
    assert [e.resultat for e in res.etapes] == ["rattrapee", "reussie"] and res.operateur == "écran (main humaine)"
    assert [(p.moyen, p.resultat) for p in res.etapes[0].plans_b] == [("main_humaine", "reussi")]
    # Une seule reprise et un seul rendu, notés par l'écran (le chef ne les note pas une deuxième fois).
    assert [(e.donnees["quoi"], e.source) for e in _evs(s, "pilotage_humain")] == [
        ("demande", "main_humaine"), ("reprise", "main_humaine"), ("ordre", "main_humaine"), ("rendu", "main_humaine")]
    assert _evs(s, "pilotage_humain")[-1].donnees["fait"] is True
    assert res.fiche.part_humain_pct > 0 and res.fiche.ordres_humains == 1
    assert s.chaine.pilote_humain is None  # la main est rendue : tout comme avant


def test_personne_ne_prend_la_main_le_chef_passe_a_la_suite(systeme):
    from briques.b15_chef_demo.chef import ChefDemo, OperateurEcran

    s = systeme(acceleration=60)
    sc = _petit({"nom": "saluer", "dire": "Salue", "attendu": {"action": "rejouer_geste"}})

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            chef = ChefDemo(s, sc, repetition=True, acceleration=60, pannes={1: "robot"},
                            operateur=OperateurEcran(main, attente_s=0.3))
            return await chef.jouer(), main
        finally:
            await s.arreter()

    res, main = lancer(go())
    assert [(p.moyen, p.resultat) for p in res.etapes[0].plans_b] == [("main_humaine", "rate"), ("sauter", "saute")]
    assert [e.donnees["quoi"] for e in _evs(s, "pilotage_humain")] == ["demande", "demande_retiree"]
    assert _evs(s, "pilotage_humain")[-1].donnees["raison"] == "personne n'a pris la main à temps"
    assert main.consigne is None and main.qui is None and s.compteur.fiche().part_humain_pct == 0


def test_la_consigne_du_chef_arrive_a_l_ecran(systeme):
    s = systeme()

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s, attente_chef_s=5)
            tache = asyncio.create_task(main.attendre_un_humain("étape « x » : faites à la main « Salue »"))
            while main.consigne is None:
                await asyncio.sleep(0.01)
            assert main.etat()["consigne"]["texte"].endswith("« Salue »")
            jeton = (await main.prendre("Hiba"))["jeton"]
            with pytest.raises(Refus):
                await main.prendre("Luca")
            # Une deuxième demande du chef pendant que la première attend : refusée tout de suite (notée).
            assert await main.attendre_un_humain("une autre consigne") is False
            assert any("deuxième demande" in e.donnees.get("texte", "") for e in _evs(s, "note"))
            assert main.consigne["texte"].endswith("« Salue »")  # la première est toujours là
            await main.rendre(jeton, fait=False)  # « Pas pu — je rends la main »
            assert await tache is False and main.consigne is None
        finally:
            await s.arreter()

    lancer(go())


# ---------------------------------------------------------------- l'écran du jury
def test_le_jury_dit_qu_un_humain_pilote(systeme):
    s = systeme()
    with TestClient(_app(s)) as c:
        page = c.get("/jury").text
        assert 'id="bandeau-pilote"' in page and "UN HUMAIN PILOTE" in page and 'id="f-humain-d"' in page
        js = c.get("/static/jury.js").text
        assert "/api/main_humaine?court=1" in js and "MAIN HUMAINE SIMULÉE" in js and 'case "pilotage_humain"' in js
        # Tuile « Réussites » : « dont N par l'humain » ; la part simulée du chef est dite à part.
        assert 'id="f-reussites-d"' in page and "par l'humain" in js and "simulée (répétition)" in js
        c.post("/api/main_humaine/prendre", json={"qui": "Hiba"}, headers=CODE)
        court = c.get("/api/main_humaine?court=1").json()
        assert court["qui"] == "Hiba" and court["mention"] == "testé sur faux robot" and "actions" not in court
        lignes = [ligne for ligne in _lignes_flux(c) if ligne["type"] == "pilotage_humain"]
        assert lignes and lignes[-1]["texte"] == "un humain prend la main : Hiba"


def _lignes_flux(c):
    import json

    r = c.get("/api/flux_simple?historique=200&direct=0")
    return [json.loads(ligne) for ligne in r.text.splitlines() if ligne.strip()]


def test_le_jury_voit_aussi_la_main_humaine_simulee_du_chef(systeme):
    s = systeme()

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            await s.bus.emettre("pilotage_humain", "chef_demo", quoi="reprise", operateur="automatique (simulé)",
                                consigne="faites « Salue »", par="chef_demo")
            assert main.etat(court=True)["annoncee"]["qui"] == "automatique (simulé)"
            assert s.chaine.pilote_humain is None  # la voix n'est pas coupée par une main simulée
            await s.bus.emettre("pilotage_humain", "chef_demo", quoi="rendu", operateur="automatique (simulé)")
            assert main.etat(court=True)["annoncee"] is None
        finally:
            await s.arreter()

    lancer(go())


# ---------------------------------------------------------------- jamais d'appel direct au robot
def test_la_main_humaine_ne_parle_au_robot_que_par_la_chaine():
    """En lisant le code (sans l'exécuter) : aucun appel aux commandes du robot, ni au guichet du gardien ; les
    ordres partent par `chaine.ordre_humain` (formulaire → gardien → ticket → prise)."""
    interdits = {"executer", "demarrer", "annuler", "arreter_tout", "rearmer", "verifier", "verificateur",
                 "reponse_humaine", "provoquer_panne", "simulation", "etat_robot", "suivre"}
    fautes, ordres = [], 0
    for p in sorted(ICI.glob("*.py")):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Attribute):
                if n.attr in interdits:
                    fautes.append(f"{p.name}:{n.lineno} {ast.unparse(n)}")
                ordres += n.attr == "ordre_humain"
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                module = getattr(n, "module", "") or ""
                if module.startswith(("briques.b02_faux_robot", "briques.b03_adaptateurs")) or module.endswith(
                        ("prise", "ticket", "adaptateur")):
                    fautes.append(f"{p.name}:{n.lineno} import {module}")
    assert not fautes, fautes
    assert ordres >= 2  # les boutons, et l'arrêt quand l'humain prend la main


# ---------------------------------------------------------------- corrections après la relecture sécurité
def test_prendre_la_main_arrete_l_action_en_cours(systeme):
    """Cas normal : la voix a lancé un déplacement ; l'humain prend la main ; le robot s'arrête (par le gardien)."""
    s = systeme(acceleration=5)

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            voix = await s.chaine.traiter("avance de 2 mètres", "fr", attendre_fin=False)
            await asyncio.sleep(0.3)
            assert s.prise.action_longue_en_cours() is not None
            await main.prendre("Hiba")
            assert (await _attendre_fin(s, voix.conversation)).donnees["statut"] == "annulee"
            assert s.prise.action_longue_en_cours() is None
        finally:
            await s.arreter()

    lancer(go())
    f = s.compteur.fiche()
    assert f.reussites == 0 and f.annulees == 1  # l'arrêt envoyé en prenant la main n'est pas une réussite du robot


def test_la_course_du_clic_pendant_qu_une_action_de_la_voix_demarre(systeme):
    """Le robot met du temps à démarrer (panne « lenteur », comme un vrai robot) ; le clic « Je prends la main »
    arrive pendant que la prise attend le robot (rien n'est encore « en cours »). Le déplacement ne doit pas continuer :
    l'arrêt part toujours ; la prise refuse le ticket d'avant (ticket_avant_stop), ou le robot l'arrête."""
    s = systeme(acceleration=5)

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            s.simulation.provoquer_panne("lenteur")
            en_cours_au_clic, taches = [], []

            async def apres_annonce(ev):
                if ev.donnees.get("genre") == "annonce" and main.qui is None and not taches:
                    async def cliquer():
                        await asyncio.sleep(0.1)  # le clic arrive pendant que la prise attend le robot
                        en_cours_au_clic.append(s.prise.action_longue_en_cours())
                        await main.prendre("Hiba")
                    taches.append(asyncio.create_task(cliquer()))

            s.bus.abonner(apres_annonce, "reponse_dite")
            voix = await s.chaine.traiter("avance de 2 mètres", "fr", attendre_fin=False)
            await taches[0]
            await asyncio.sleep(1.5)
            s.simulation.reparer()
            assert en_cours_au_clic == [None]  # la course a bien eu lieu : rien n'était « en cours » au clic
            assert s.prise.action_longue_en_cours() is None
            fins = [e.donnees["statut"] for e in _evs(s, "action_terminee", voix.conversation)]
            refus = [r["code"] for e in _evs(s, "action_refusee", voix.conversation) for r in e.donnees.get("raisons", [])]
            assert fins == ["annulee"] or "ticket_avant_stop" in refus, (fins, refus)
            assert "reussie" not in fins and s.chaine.pilote_humain == "Hiba"
        finally:
            await s.arreter()

    lancer(go())


def test_une_demande_de_l_autre_camp_ne_part_jamais(systeme):
    """Une demande à un humain faite AVANT la main humaine (voix, agent) ne part pas PENDANT ; une demande du pilote ne
    part pas APRÈS qu'il a rendu la main. Oubliée chez le gardien ET dans la chaîne."""
    s = systeme()

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            res = await s.chaine.traiter("prends la tasse", "fr", attendre_fin=False, source="agent:essai")
            assert res.verdict == "humain"
            numero = s.gardien.demandes_en_attente()[0]["numero"]
            jeton = (await main.prendre("Hiba"))["jeton"]
            assert s.gardien.demandes_en_attente() == [] and main.etat()["demandes"] == []
            assert _evs(s, "pilotage_humain")[0].donnees["demandes_oubliees"] == 1
            assert await s.chaine.reponse_humaine(numero, True, qui="Luca") is None  # rien ne part
            o = await main.ordre("saisir", {"objet": "tasse"}, jeton)
            assert o["sorte"] == "humain" and o["numero_demande"]
            await main.rendre(jeton)
            assert s.gardien.demandes_en_attente() == []
            assert _evs(s, "pilotage_humain")[-1].donnees["demandes_oubliees"] == 1
            assert await s.chaine.reponse_humaine(o["numero_demande"], True, qui="Luca") is None
            await asyncio.sleep(0.3)
        finally:
            await s.arreter()
        assert not [e for e in _evs(s, "action_demarree") if e.donnees["action"]["nom"] == "saisir"]
        assert not [e for e in _evs(s, "gardien_decision")
                    if e.donnees["verdict"] == "oui" and (e.donnees.get("action") or {}).get("nom") == "saisir"]

    lancer(go())


def test_le_numero_de_main_attrape_un_aller_retour(systeme):
    """La main est prise PUIS rendue pendant que le gardien vérifie un ordre de la voix : un simple oui/non verrait
    « personne n'a la main » au départ comme à l'arrivée ; le numéro de main, lui, a changé : rien ne part."""
    s = systeme()

    async def go():
        await s.demarrer()
        try:
            verifier = s.gardien.verifier

            async def verifier_pendant_un_aller_retour(action, carte, **kw):
                if action.nom != "arreter":
                    s.chaine.changer_de_main("Hiba")
                    s.chaine.changer_de_main(None)
                return await verifier(action, carte, **kw)

            s.gardien.verifier = verifier_pendant_un_aller_retour
            res = await s.chaine.traiter("Va à la table", "fr")
            s.gardien.verifier = verifier
            assert res.verdict == "oui" and res.statut_action is None and not res.reponses
            assert any("la main a changé" in e.donnees.get("texte", "") for e in _evs(s, "note", res.conversation))
            assert not _evs(s, "action_demarree")
            assert (await s.chaine.traiter("Va à la table", "fr")).statut_action == "reussie"  # sans changement : part
        finally:
            await s.arreter()

    lancer(go())


def test_le_jeton_de_la_tablette_qui_a_pris_la_main(systeme):
    s = systeme()
    with TestClient(_app(s)) as c:
        j = c.post("/api/main_humaine/prendre", json={"qui": "Hiba"}, headers=CODE).json()["jeton"]
        assert c.get("/api/main_humaine", headers={"X-Jeton-Main": j}).json()["a_moi"] is True
        etat = c.get("/api/main_humaine").json()
        assert etat["a_moi"] is False and "jeton" not in etat and j not in str(etat)  # jamais dans l'état lu par tous
        # Une autre tablette (code d'équipe, mais pas le jeton) : ni ordre, ni rendu normal…
        r = c.post("/api/main_humaine/ordre", json={"nom": "etat"}, headers=CODE)
        assert r.status_code == 409 and "autre tablette" in r.json()["detail"]
        r = c.post("/api/main_humaine/rendre", json={"qui": "Luca"}, headers=CODE)
        assert r.status_code == 409 and "Libérer la main" in r.json()["detail"] and s.chaine.pilote_humain == "Hiba"
        # … seulement « Libérer la main » (forcer), noté dans la boîte noire.
        r = c.post("/api/main_humaine/rendre", json={"qui": "Luca", "forcer": True}, headers=CODE).json()
        assert r["qui"] is None and s.chaine.pilote_humain is None
        rendu = _evs(s, "pilotage_humain")[-1].donnees
        assert (rendu["quoi"], rendu["qui"], rendu["rendu_par"], rendu["force"]) == ("rendu", "Hiba", "Luca", True)
        # L'ancien jeton ne sert plus à rien, même quand quelqu'un d'autre reprend la main.
        r = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "etat"}, headers=CODE)
        assert r.status_code == 409 and "Prenez d'abord la main" in r.json()["detail"]
        j2 = c.post("/api/main_humaine/prendre", json={"qui": "Luca"}, headers=CODE).json()["jeton"]
        assert j2 != j
        r = c.post("/api/main_humaine/ordre", json={"jeton": j, "nom": "etat"}, headers=CODE)
        assert r.status_code == 409 and "autre tablette" in r.json()["detail"]
        assert c.post("/api/main_humaine/ordre", json={"jeton": j2, "nom": "etat"}, headers=CODE).json()["sorte"] == "parti"
    boite_noire = " ".join(e.model_dump_json() for e in s.bus.historique)
    assert j not in boite_noire and j2 not in boite_noire


def test_la_fiche_compte_a_part_la_main_simulee_du_chef():
    from briques.b12_boite_noire.fiche import calculer
    from commun.evenements import Evenement

    def journal(simulee_notee: bool):
        sim = {"operateur": "automatique (simulé)", "par": "chef_demo", **({"simulee": True} if simulee_notee else {})}
        return [Evenement(type="session_debut", source="systeme", t=0.0),
                Evenement(type="pilotage_humain", source="chef_demo", donnees={"quoi": "reprise", **sim}, t=10.0),
                Evenement(type="pilotage_humain", source="chef_demo", donnees={"quoi": "rendu", **sim}, t=20.0),
                Evenement(type="pilotage_humain", source="main_humaine", donnees={"quoi": "reprise", "qui": "Hiba"}, t=30.0),
                Evenement(type="pilotage_humain", source="main_humaine", donnees={"quoi": "rendu", "qui": "Hiba"}, t=45.0),
                Evenement(type="note", source="test", t=100.0)]

    for simulee_notee in (True, False):  # False : un journal d'avant ce drapeau (l'opérateur « simulé » suffit)
        f = calculer(journal(simulee_notee))
        assert (f.part_humain_pct, f.part_humain_simulee_pct) == (15.0, 10.0)


def test_le_chef_n_attend_pas_le_rendu_indefiniment(systeme):
    """Un humain prend la main pour le chef… et ne la rend pas : après l'attente maximale, le chef passe à la suite.
    La main n'est jamais retirée à l'humain."""
    from briques.b15_chef_demo.chef import ChefDemo, OperateurEcran

    s = systeme(acceleration=60)
    sc = _petit({"nom": "saluer", "dire": "Salue", "attendu": {"action": "rejouer_geste"}})

    async def humain(main: MainHumaine):
        while main.consigne is None:
            await asyncio.sleep(0.02)
        await main.prendre("Hiba")  # … et ne la rend jamais

    async def go():
        await s.demarrer()
        try:
            main = MainHumaine(s)
            chef = ChefDemo(s, sc, repetition=True, acceleration=60, pannes={1: "robot"},
                            operateur=OperateurEcran(main, attente_rendu_s=0.3))
            res, _ = await asyncio.gather(chef.jouer(), humain(main))
            return res, main
        finally:
            await s.arreter()

    res, main = lancer(go())
    assert [(p.moyen, p.resultat) for p in res.etapes[0].plans_b] == [("main_humaine", "rate"), ("sauter", "saute")]
    retirees = [e.donnees for e in _evs(s, "pilotage_humain") if e.donnees["quoi"] == "demande_retiree"]
    assert len(retirees) == 1 and "pas rendue à temps" in retirees[0]["raison"]
    assert main.qui == "Hiba" and s.chaine.pilote_humain == "Hiba" and main.consigne is None
