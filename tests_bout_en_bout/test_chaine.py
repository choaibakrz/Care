"""Bout en bout, Internet coupé (voir conftest.py). Testé sur faux robot.

Étape 1 : la parole est encore TAPÉE (la voix arrive à l'étape 2), le cerveau est « à règles ».
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import lancer

MEME_ORDRE = [("Va à la cuisine", "fr"), ("Geh in die Küche", "de"), ("Go to the kitchen", "en"),
              ("去厨房", "zh"), ("Vai in cucina", "it"), ("Gang i d'Chuchi", "gsw")]


def _traiter(s, phrases):
    async def go():
        await s.demarrer()
        res = [await s.chaine.traiter(t, l) for t, l in phrases]
        await s.arreter()
        return res

    return lancer(go())


def test_preuve_1_meme_action_dans_toutes_les_langues(fabrique_systeme):
    res = _traiter(fabrique_systeme(), MEME_ORDRE)
    actions = {(r.action.nom, r.action.parametres["lieu"]) for r in res}
    assert actions == {("se_deplacer", "cuisine")}
    assert all(r.statut_action == "reussie" for r in res)
    assert res[1].reponses[0].startswith("Ich gehe") and res[3].reponses[0].startswith("我去")


def test_suisse_allemand_compris_reponse_en_allemand_et_le_robot_le_dit(fabrique_systeme):
    res = _traiter(fabrique_systeme(), [("Gang i d'Chuchi", "gsw"), ("Gang zum Tisch", "gsw")])
    assert "Schweizerdeutsch" in res[0].reponses[0] and "Hochdeutsch" in res[0].reponses[0]
    assert "Schweizerdeutsch" not in " ".join(res[1].reponses)  # dit une seule fois


@pytest.mark.parametrize("texte,langue,mot", [
    ("Va à la scène à 5 mètres par seconde", "fr", "sécurité"),
    ("Geh zur Bühne mit 4 Meter pro Sekunde", "de", "Sicherheitsgrenze"),
    ("Go to the stage at 9 meters per second", "en", "safety limit"),
    ("以 5 米每秒 去舞台", "zh", "安全限制"),
])
def test_preuve_2_ordre_dangereux_refuse_et_explique_dans_la_langue(fabrique_systeme, texte, langue, mot):
    (r,) = _traiter(fabrique_systeme(), [(texte, langue)])
    assert r.verdict == "non" and r.statut_action is None
    assert mot in r.reponses[-1]


@pytest.mark.parametrize("texte,langue", [("va", "fr"), ("geh", "de"), ("take", "en"), ("prends et pose", "fr")])
def test_preuve_3_ordre_flou_le_robot_pose_une_question(fabrique_systeme, texte, langue):
    (r,) = _traiter(fabrique_systeme(), [(texte, langue)])
    assert r.decision.genre == "question" and r.statut_action is None


def test_preuve_5_remplacer_l_humanoide_par_le_bras_rien_d_autre_ne_change(fabrique_systeme):
    """Même code, même chaîne : seule la carte change."""
    h = _traiter(fabrique_systeme("humanoide"), [("Va à la cuisine", "fr"), ("Salue", "fr")])
    b = _traiter(fabrique_systeme("bras"), [("Va à la cuisine", "fr"), ("Salue", "fr"), ("Prends la bouteille", "fr"),
                                            ("Oui", "fr")])
    assert h[0].statut_action == "reussie"
    assert b[0].decision.genre == "hors_carte" and "ne sait pas faire" in b[0].reponses[-1]
    assert h[1].statut_action == b[1].statut_action == "reussie"
    assert b[2].statut_action is None and "confirmez" in b[2].reponses[-1]  # action à risque : il demande d'abord
    assert b[3].statut_action == "reussie"


def test_preuve_4_l_ecran_montre_tout_et_la_fiche_se_remplit(fabrique_systeme):
    s = fabrique_systeme()
    s.reglages["ecran"]["code_equipe"] = "code-de-test"
    from briques.b13_ecran.serveur import creer_app

    with TestClient(creer_app(s)) as client:
        assert "Fiche de vérité" in client.get("/").text
        assert client.get("/api/carte").json()["mention"] == "testé sur faux robot"
        assert client.post("/api/dire", json={"texte": "Regarde la table"}).status_code == 403  # sans code
        code = {"X-Code-Equipe": "code-de-test"}
        with client.websocket_connect("/ws") as ws:
            assert client.post("/api/dire", json={"texte": "Regarde la table", "langue": "fr"}, headers=code).status_code == 200
            vus = set()
            for _ in range(60):
                vus.add(ws.receive_json()["type"])
                if "reponse_dite" in vus and "gardien_decision" in vus:
                    break
        assert {"parole_entendue", "demande_comprise", "gardien_decision", "reponse_dite"} <= vus
        assert client.post("/api/arret_urgence").json()["ok"]  # sans code : l'arrêt d'urgence est ouvert à tous
        fiche = client.get("/api/fiche").json()
        assert fiche["demandes"] == 1 and fiche["arrets_urgence"] == 1
        assert client.get("/api/etat").json()["arret_urgence_actif"] is True


def test_internet_est_bien_coupe_pendant_les_tests():
    import socket

    with pytest.raises(OSError):
        socket.create_connection(("1.1.1.1", 443), timeout=1)


def test_l_ecran_protege_rearmer_et_refuse_les_autres_sites(fabrique_systeme):
    s = fabrique_systeme()
    s.reglages["ecran"]["code_equipe"] = "code-de-test"
    from briques.b13_ecran.serveur import creer_app

    with TestClient(creer_app(s)) as client:
        assert client.post("/api/arret_urgence").json()["ok"]
        assert client.post("/api/rearmer").status_code == 403
        assert client.post("/api/panne", json={"nom": "refus"}).status_code == 403
        mauvais_site = {"X-Code-Equipe": "code-de-test", "Origin": "http://site-pirate.example"}
        assert client.post("/api/rearmer", headers=mauvais_site).status_code == 403
        assert client.post("/api/rearmer", headers={"X-Code-Equipe": "faux"}).status_code == 403
        assert client.post("/api/rearmer", headers={"X-Code-Equipe": "code-de-test"}).json()["ok"] is True


def test_le_fichier_d_exemple_ne_contient_aucun_code():
    """Le dépôt ne doit jamais contenir de code d'équipe : seul reglages.yaml (hors dépôt) en a un."""
    import yaml

    from commun.systeme import REGLAGES_EXEMPLE

    assert yaml.safe_load(REGLAGES_EXEMPLE.read_text(encoding="utf-8"))["ecran"]["code_equipe"] == ""


@pytest.mark.parametrize("ordre,reponse,langue,fait", [
    ("Prends la bouteille", "oui", "fr", True), ("Nimm die Flasche", "Nein", "de", False),
    ("Take the bottle", "yes", "en", True), ("拿瓶子", "好的", "zh", True), ("Prendi la bottiglia", "no", "it", False),
])
def test_action_a_risque_le_robot_repete_et_attend_oui(fabrique_systeme, ordre, reponse, langue, fait):
    s = fabrique_systeme("bras")
    r1, r2 = _traiter(s, [(ordre, langue), (reponse, langue)])
    assert r1.statut_action is None and r1.decision.genre == "action"
    assert (r2.statut_action == "reussie") is fait


def test_la_raison_d_un_echec_est_dite_dans_la_langue_de_la_personne(fabrique_systeme):
    """Faux bras : l'objet de test est hors de portée ; la personne parle allemand → toute la réponse en allemand."""
    async def go():
        s = fabrique_systeme("bras")
        await s.demarrer()
        await s.chaine.traiter("Nimm das Testobjekt", "de")
        r = await s.chaine.traiter("ja", "de")
        await s.arreter()
        return r

    r = lancer(go())
    assert r.statut_action == "echouee"
    dernier = r.reponses[-1].texte if hasattr(r.reponses[-1], "texte") else str(r.reponses[-1])
    assert "außer Reichweite" in dernier and "portée" not in dernier, dernier


def test_un_stop_pendant_la_verification_du_gardien_l_emporte(fabrique_systeme):
    """Relecture du lot B : l'état du robot met 300 ms à venir (réseau d'un vrai robot, simulé) ; « stop » arrive
    pendant ce temps. Le robot ne doit PAS partir après. Testé sur faux robot."""
    import asyncio

    s = fabrique_systeme()
    lire = s.gardien.perception._lire_etat

    async def etat_lent():
        await asyncio.sleep(0.3)
        return await lire()

    s.gardien.perception._lire_etat = etat_lent

    async def go():
        await s.demarrer()
        aller = asyncio.create_task(s.chaine.traiter("Va à la table", "fr"))
        await asyncio.sleep(0.1)
        await s.chaine.traiter("Stop !", "fr")
        r = await aller
        await s.arreter()
        return r

    r = lancer(go())
    parties = [e.donnees["action"]["nom"] for e in s.bus.historique if e.type == "action_demarree"]
    assert "se_deplacer" not in parties and r.statut_action is None


def test_la_prise_refuse_un_ticket_fabrique_avant_le_dernier_stop(fabrique_systeme):
    from briques.b01_prise.actions import ActionDemandee
    from briques.b01_prise.prise import ActionRefusee

    s = fabrique_systeme()

    async def go():
        await s.demarrer()
        carte = s.prise.carte()
        _, vieux = await s.gardien.verifier(ActionDemandee(nom="regarder", parametres={"cible": "table"}), carte)
        _, stop = await s.gardien.verifier(ActionDemandee(nom="arreter"), carte)
        await s.prise.executer(stop)
        try:
            await s.prise.executer(vieux)
            return None
        except ActionRefusee as e:
            return [r.code for r in e.raisons]
        finally:
            await s.arreter()

    assert lancer(go()) == ["ticket_avant_stop"]


def test_une_carte_qui_ne_dit_pas_la_verite_empeche_le_demarrage(reglages, tmp_path):
    """Relecture du lot B : une carte copiée d'un faux robot (vrai_robot: false) sur un vrai adaptateur ferait
    croire à des personnes simulées. Pas de démarrage."""
    from briques.b01_prise.adaptateur import Adaptateur
    from briques.b01_prise.carte import CarteIdentite
    from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES
    from commun.systeme import CarteIncoherente, Systeme

    class VraiAdaptateurFictif(Adaptateur):  # n'est jamais branché : la construction doit refuser avant
        def carte(self):
            return CarteIdentite.charger(DOSSIER_CARTES / "humanoide.yaml")  # dit vrai_robot: false

        async def demarrer(self, action): raise NotImplementedError
        async def suivre(self, ident): raise NotImplementedError
        async def annuler(self, ident): raise NotImplementedError
        async def arret_urgence(self): raise NotImplementedError
        async def rearmer(self): raise NotImplementedError
        async def etat_robot(self): raise NotImplementedError

    r = {**reglages, "cerveau": {**reglages["cerveau"], "choix": "regles"}}
    with pytest.raises(CarteIncoherente):
        Systeme(r, dossier_journal=tmp_path / "j", adaptateur=VraiAdaptateurFictif())


def test_un_ordre_verifie_pendant_l_arret_d_urgence_ne_part_pas_au_rearmement(fabrique_systeme):
    """Relecture du lot B (2e passage) : « Va à la table » pendant l'arrêt d'urgence, Réarmer pendant la vérification
    (état lent) : le robot ne doit pas partir tout seul. Testé sur faux robot."""
    import asyncio

    s = fabrique_systeme()
    lire = s.gardien.perception._lire_etat

    async def etat_lent():
        await asyncio.sleep(0.3)
        return await lire()

    async def go():
        await s.demarrer()
        await s.prise.arret_urgence(raison="essai")
        s.gardien.perception._lire_etat = etat_lent
        aller = asyncio.create_task(s.chaine.traiter("Va à la table", "fr"))
        await asyncio.sleep(0.1)
        assert await s.prise.rearmer()
        r = await aller
        await s.arreter()
        return r

    r = lancer(go())
    parties = [e.donnees["action"]["nom"] for e in s.bus.historique if e.type == "action_demarree"]
    assert "se_deplacer" not in parties and r.statut_action in (None, "refusee")


def test_preuve_6_un_agent_d_ia_passe_par_la_porte_des_agents_et_le_gardien_le_controle(fabrique_systeme):
    """Un agent d'IA (ici : appel direct de la porte, sans MCP) : ordre dangereux refusé et expliqué ; ordre normal en
    attente de l'accord d'un humain ; « stop » toujours accepté. Rien ne part sans le gardien. Testé sur faux robot."""
    from briques.b14_porte_agents.porte import PorteDesAgents

    s = fabrique_systeme()

    async def go():
        await s.demarrer()
        porte = PorteDesAgents(s, nom="preuve")
        await porte.ouvrir("memoire")
        try:
            danger = await porte.dire("Va à la cuisine à 5 mètres par seconde", "fr")
            normal = await porte.dire("Va à la table", "fr")
            stop = await porte.dire("Stop", "fr")
            return danger, normal, stop
        finally:
            await s.arreter()

    danger, normal, stop = lancer(go())
    assert danger["verdict_gardien"] == "non" and danger["reponses"], danger
    assert normal["statut"] == "attend_un_humain", normal  # l'accord d'un humain est allumé par défaut
    assert stop["statut"] != "ordre_invalide", stop
    parties = [e.donnees["action"]["nom"] for e in s.bus.historique if e.type == "action_demarree"]
    assert parties == ["arreter"], parties
    assert all(e.source.startswith("agent:") for e in s.bus.historique if e.type == "parole_entendue")
