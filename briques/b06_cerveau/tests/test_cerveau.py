"""Brique 6 — le cerveau. Testé sur faux robot. Les tests du formulaire et de la cascade n'ont besoin d'aucun modèle :
un faux serveur (httpx.MockTransport) joue le modèle. Le test avec le vrai petit Apertus saute s'il n'est pas lancé."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from briques.b01_prise.carte import CarteIdentite
from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES
from briques.b06_cerveau.branchements.cascade import CerveauCascade, Etage
from briques.b06_cerveau.branchements.llm import CerveauIndisponible, CerveauLLM
from briques.b06_cerveau.branchements.regles import CerveauRegles
from briques.b06_cerveau.formulaire import FormulaireInvalide, lire_reponse, schema
from commun.bus import Bus
from commun.monde import Monde
from conftest import lancer

HUMANOIDE = CarteIdentite.charger(DOSSIER_CARTES / "humanoide.yaml")
BRAS = CarteIdentite.charger(DOSSIER_CARTES / "bras.yaml")
MONDE = Monde.charger()


def _faux_modele(reponses, delai_s: float = 0.0, statut: int = 200):
    """Un faux serveur de modèle : rend les réponses prévues, dans l'ordre."""
    file = list(reponses)
    vus = []

    async def gerer(requete: httpx.Request) -> httpx.Response:
        vus.append(json.loads(requete.content))
        if delai_s:
            await asyncio.sleep(delai_s)
        contenu = file.pop(0) if file else '{"type":"question","question":"?"}'
        return httpx.Response(statut, json={"choices": [{"message": {"content": contenu}}]})

    return httpx.MockTransport(gerer), vus


def _llm(nom, transport, **kw):
    c = CerveauLLM(nom, "http://modele.local:1", **kw)
    c.transport = transport
    return c


# ---------------------------------------------------------------- formulaire
def test_le_formulaire_ne_contient_que_les_actions_de_la_carte():
    for carte in (HUMANOIDE, BRAS):
        noms = {v["properties"]["action"]["const"] for v in schema(carte, MONDE)["oneOf"] if "action" in v["properties"]}
        assert noms == set(carte.capacites)


@pytest.mark.parametrize("contenu", [
    "Bien sûr, je vais à la cuisine !",                                     # pas du JSON
    '{"type":"action","action":"voler","parametres":{}}',                    # action inconnue
    '{"type":"action","action":"se_deplacer","parametres":{"lieu":"lune"}}',  # lieu inconnu
    '{"type":"action","action":"se_deplacer","parametres":{"lieu":"cuisine","laser":1}}',  # précision inventée
    '{"type":"action","action":"saisir","parametres":{}}',                   # précision obligatoire manquante
    '{"type":"action","action":"se_deplacer","parametres":{"vitesse":NaN}}',  # pas un vrai nombre
    '{"type":"reponse","texte":"ok"}',                                       # autre forme
    '{"type":"question","question":"","extra":1}',
    '{"type":"question","question":" "}',                                    # question vide (sans autre défaut)
    '{"type":"action","action":"se_deplacer","parametres":{"vitesse":0.2}}',  # ni lieu ni distance
    '{"type":"action","action":"se_deplacer","parametres":{"dx":1e400}}',    # nombre infini
])
def test_toute_reponse_hors_formulaire_est_refusee(contenu):
    with pytest.raises(FormulaireInvalide):
        lire_reponse(contenu, HUMANOIDE, MONDE)


def test_le_bras_ne_peut_pas_recevoir_un_deplacement():
    with pytest.raises(FormulaireInvalide):
        lire_reponse('{"type":"action","action":"se_deplacer","parametres":{"lieu":"cuisine"}}', BRAS, MONDE)


def test_reponses_conformes():
    d = lire_reponse('{"type":"action","action":"se_deplacer","parametres":{"lieu":"cuisine","vitesse":5}}', HUMANOIDE, MONDE)
    assert d.genre == "action" and d.action.parametres == {"lieu": "cuisine", "vitesse": 5}
    q = lire_reponse('{"type":"question","question":"Quel objet ?"}', HUMANOIDE, MONDE)
    assert q.genre == "question" and q.texte == "Quel objet ?"


# ---------------------------------------------------------------- branchement modèle de langue
def test_le_formulaire_est_force_et_la_cle_n_apparait_jamais(monkeypatch):
    transport, vus = _faux_modele(['{"type":"action","action":"regarder","parametres":{"cible":"table"}}'])
    monkeypatch.setenv("CLE_DE_TEST", "secret-123")
    c = _llm("test", transport, cle_env="CLE_DE_TEST", formulaire="json_schema")
    d = lancer(c.decider("Regarde la table", "fr", HUMANOIDE, MONDE))
    assert d.action.nom == "regarder" and d.cerveau == "test"
    corps = vus[0]
    assert corps["response_format"]["type"] == "json_schema" and corps["temperature"] == 0
    assert "secret-123" not in repr(c) and "secret-123" not in json.dumps(corps)


def test_service_qui_refuse_le_formulaire_passe_par_un_appel_d_outil():
    vus = []

    async def gerer(requete):
        corps = json.loads(requete.content)
        vus.append(corps)
        if "response_format" in corps:
            return httpx.Response(400, json={"error": "response_format non permis"})
        args = '{"type":"action","action":"etat","parametres":{}}'
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"function": {"name": "reponse_robot", "arguments": args}}]}}]})

    c = _llm("en_ligne", httpx.MockTransport(gerer), formulaire="json_schema")
    d = lancer(c.decider("Batterie ?", "fr", HUMANOIDE, MONDE))
    assert d.action.nom == "etat" and vus[1]["tool_choice"]["function"]["name"] == "reponse_robot"


def test_le_mode_force_envoie_le_schema_a_llama_cpp():
    transport, vus = _faux_modele(['{"type":"question","question":"Quel objet ?"}'])
    lancer(_llm("test", transport).decider("Prends ça", "fr", HUMANOIDE, MONDE))
    rf = vus[0]["response_format"]
    assert rf["type"] == "json_object" and "oneOf" in rf["schema"]


def test_reponse_hors_formulaire_devient_indisponible():
    transport, _ = _faux_modele(['{"type":"action","action":"voler","parametres":{}}'])
    with pytest.raises(CerveauIndisponible):
        lancer(_llm("test", transport).decider("Vole", "fr", HUMANOIDE, MONDE))


# ---------------------------------------------------------------- cascade : secours automatique
def test_cascade_trop_lent_puis_secours_puis_regles():
    lent, _ = _faux_modele(['{"type":"action","action":"etat","parametres":{}}'], delai_s=2.0)
    casse, _ = _faux_modele([], statut=500)
    bus = Bus()
    cascade = CerveauCascade([Etage(_llm("apertus_8b", lent), delai_s=0.3), Etage(_llm("apertus_4b", casse), delai_s=0.3),
                              Etage(CerveauRegles())], bus)

    async def go():
        d = await cascade.decider("Va à la cuisine", "fr", HUMANOIDE, MONDE)
        d2 = await cascade.decider("Va à la table", "fr", HUMANOIDE, MONDE)  # les deux en pause : réponse immédiate
        return d, d2

    d, d2 = lancer(go())
    assert d.cerveau == "regles" and d.action.parametres["lieu"] == "cuisine"
    secours = [e.donnees for e in bus.historique if e.type == "cerveau_secours"]
    assert [s["de"] for s in secours] == ["apertus_8b", "apertus_4b"] and secours[0]["raison"] == "trop lent"
    assert d2.cerveau == "regles" and len([e for e in bus.historique if e.type == "cerveau_secours"]) == 2


def test_cascade_premier_cerveau_repond():
    rapide, _ = _faux_modele(['{"type":"question","question":"Quel objet ?"}'])
    cascade = CerveauCascade([Etage(_llm("apertus_8b", rapide), delai_s=2), Etage(CerveauRegles())])
    d = lancer(cascade.decider("Prends ça", "fr", HUMANOIDE, MONDE))
    assert d.cerveau == "apertus_8b" and d.genre == "question"


class FauxServeur:
    """Joue un serveur de modèle : lancé, en chargement, arrêté."""

    def __init__(self, charge_apres: int = 0):
        self.lance, self.arrete, self.appels_chargement = 0, 0, 0
        self.charge_apres = charge_apres
        self._tourne = False

    def tourne(self):
        return self._tourne

    def lancer(self):
        self.lance += 1
        self._tourne = True

    def eteindre(self):
        self.arrete += 1
        self._tourne = False

    def en_chargement(self):
        self.appels_chargement += 1
        return self._tourne and self.appels_chargement <= self.charge_apres


def test_cascade_secours_lance_au_besoin_puis_arrete_quand_le_principal_revient():
    reponses = {"n": 0}

    async def principal(requete):
        reponses["n"] += 1
        if reponses["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"type":"action","action":"etat","parametres":{}}'}}]})

    serveur_4b = FauxServeur()
    casse, _ = _faux_modele([], statut=500)
    etage_8b = Etage(_llm("apertus_8b", httpx.MockTransport(principal)), delai_s=1, pause_apres_echec_s=0)
    etage_4b = Etage(_llm("apertus_4b", casse), delai_s=1, serveur=serveur_4b, demarrage="au_besoin")
    cascade = CerveauCascade([etage_8b, etage_4b, Etage(CerveauRegles())])

    async def go():
        await cascade.decider("Stop", "fr", HUMANOIDE, MONDE)  # 8B en panne : le 4B est lancé
        lance = serveur_4b.lance
        d = await cascade.decider("Batterie ?", "fr", HUMANOIDE, MONDE)  # le 8B répond : le 4B est arrêté…
        await cascade.arreter()  # …à côté, sans faire attendre la réponse (relecture du lot A) ; arreter() attend la fin
        return lance, d

    lance, d = lancer(go())
    assert lance == 1 and d.cerveau == "apertus_8b" and serveur_4b.arrete == 1 and not serveur_4b.tourne()


def test_un_secours_non_lance_n_est_pas_mis_de_cote_et_un_principal_qui_charge_non_plus():
    serveur_8b = FauxServeur(charge_apres=99)
    serveur_8b.lancer()  # lancé au démarrage, encore en chargement
    serveur_4b = FauxServeur()
    lent, _ = _faux_modele([])
    cascade = CerveauCascade([Etage(_llm("apertus_8b", lent), delai_s=1, serveur=serveur_8b, demarrage="toujours"),
                              Etage(_llm("apertus_4b", lent), delai_s=1, serveur=serveur_4b, demarrage="au_besoin"),
                              Etage(CerveauRegles())])
    d = lancer(cascade.decider("Regarde la table", "fr", HUMANOIDE, MONDE))
    assert d.cerveau == "regles"
    assert serveur_4b.lance == 0  # pas de secours lancé pendant que le 8B se charge
    assert all(e.en_pause_jusqua == 0 for e in cascade.etages)


# ---------------------------------------------------------------- chaîne : verrou des chiffres
@pytest.mark.parametrize("texte,parametre,valeur", [
    ("Va à la cuisine à 5 mètres par seconde", "vitesse", 5.0),
    ("Avance de 20 mètres", "dx", 20.0),
])
def test_un_cerveau_qui_oublie_un_chiffre_ne_fait_pas_partir_le_robot(fabrique_systeme, texte, parametre, valeur):
    """Le faux modèle « oublie » la vitesse ou la distance : le verrou des chiffres la remet, le gardien refuse."""
    oublieux, _ = _faux_modele(['{"type":"action","action":"se_deplacer","parametres":{"lieu":"cuisine"}}'
                                if "cuisine" in texte else '{"type":"action","action":"se_deplacer","parametres":{"dx":1}}'])

    async def go():
        s = fabrique_systeme()
        s.chaine.cerveau = _llm("oublieux", oublieux)
        await s.demarrer()
        r = await s.chaine.traiter(texte, "fr")
        await s.arreter()
        return r

    r = lancer(go())
    assert r.action.parametres[parametre] == valeur and r.verdict == "non" and r.statut_action is None


@pytest.mark.parametrize("texte,attendu", [
    ("Va à la cuisine à cinq mètres par seconde", ("vitesse", 5.0)),
    ("Go to the kitchen at five meters per second", ("vitesse", 5.0)),
    ("Geh zur Küche mit fünf Metern pro Sekunde", ("vitesse", 5.0)),
    ("Geh zur Küche mit 5 Metern pro Sekunde", ("vitesse", 5.0)),
    ("Gang mit füf Meter i de Sekunde i d'Chuchi", ("vitesse", 5.0)),
    ("Vai in cucina a cinque metri al secondo", ("vitesse", 5.0)),
    ("以每秒五米的速度去厨房", ("vitesse", 5.0)),
    ("à un mètre par seconde", ("vitesse", 1.0)),
    ("Avance de vingt-cinq mètres", ("distance", 25.0)),
    ("Avance de deux cents mètres", ("distance", 200.0)),
    ("Geh fünfundzwanzig Meter nach vorne", ("distance", 25.0)),
    ("Avanza di venticinque metri", ("distance", 25.0)),
    ("Avance de zéro virgule cinq mètre", ("distance", 0.5)),
    ("往前走二十米", ("distance", 20.0)),
    ("Grip the cup with one hundred and twenty newtons", ("force", 120.0)),
    ("用一百牛的力抓杯子", ("force", 100.0)),
    ("Avance un peu", ("distance", None)),
    ("往前走一点", ("distance", None)),
    ("Tu sei bravo", ("distance", None)),
])
def test_les_nombres_dits_en_lettres_sont_lus(texte, attendu):
    from briques.b06_cerveau.branchements.regles import lire_distance, lire_force, lire_vitesse

    lire = {"vitesse": lire_vitesse, "distance": lire_distance, "force": lire_force}[attendu[0]]
    assert lire(texte) == attendu[1]


@pytest.mark.parametrize("texte,langue", [
    ("Va à la cuisine à cinq mètres par seconde", "fr"),
    ("Geh zur Küche mit 5 Metern pro Sekunde", "de"),
    ("Geh zur Küche mit fünf Metern pro Sekunde", "de"),
    ("Go to the kitchen at five meters per second", "en"),
])
def test_un_ordre_trop_rapide_en_lettres_est_refuse_par_toute_la_chaine(fabrique_systeme, texte, langue):
    """Cerveau à règles, faux robot : le robot ne part pas, le gardien refuse et explique."""
    async def go():
        s = fabrique_systeme()
        await s.demarrer()
        r = await s.chaine.traiter(texte, langue)
        await s.arreter()
        return r

    r = lancer(go())
    assert r.verdict == "non" and r.statut_action is None, (r.decision, r.reponses)


# Relecture du lot A : des nombres mal lus changeaient un « non » du gardien en « oui ». Sens dangereux d'abord.
@pytest.mark.parametrize("texte,lire,attendu", [
    ("Go 5,000 meters forward", "distance", 5000), ("Geh 5.000 Meter vor", "distance", 5000),
    ("Avanza di 5.000 metri", "distance", 5000), ("Avance de 1 000 mètres", "distance", 1000),
    ("Gang 5'000 Meter füre", "distance", 5000), ("Grab it with 1,000 newtons", "force", 1000),
    ("Nimm es mit 2.000 Newton", "force", 2000), ("Avance de cinq mètres cinquante", "distance", 5.5),
    ("Avance de 5 mètres 50", "distance", 5.5), ("往前走五米五", "distance", 5.5), ("往前走五米半", "distance", 5.5),
    ("Avance de 4 mètres puis encore 10 mètres", "distance", 14), ("Avance de 2 kilomètres", "distance", 2000),
    ("Avance à 2 m par seconde", "vitesse", 2), ("Vai in cucina a un metro al secondo", "vitesse", 1),
    ("Go at 1 meter/second", "vitesse", 1), ("Va à 0,5 m / s", "vitesse", 0.5), ("Fahr 4 Kilometer pro Stunde", "vitesse", 1.111),
    ("Go to the kitchen at a meter per second", "vitesse", 1), ("half a meter per second", "vitesse", 0.5),
    ("un mètre et demi par seconde", "vitesse", 1.5), ("sechzehn Meter", "distance", 16), ("sixteen meters", "distance", 16),
    ("sedici metri", "distance", 16), ("quatre-vingts mètres", "distance", 80), ("quatre-vingt-dix mètres", "distance", 90),
    ("mille mètres", "distance", 1000), ("one thousand meters", "distance", 1000), ("一千米", "distance", 1000),
    ("foif Meter", "distance", 5), ("nüün Meter", "distance", 9), ("sibezäh Meter", "distance", 17),
    ("Geh nun zwei Meter vor", "distance", 2), ("Fahr nun null Komma zwei Meter pro Sekunde", "vitesse", 0.2),
])
def test_les_nombres_sont_lus_sans_les_sous_estimer(texte, lire, attendu):
    from briques.b06_cerveau.branchements.regles import lire_distance, lire_force, lire_vitesse

    valeur = {"vitesse": lire_vitesse, "distance": lire_distance, "force": lire_force}[lire](texte)
    assert valeur == pytest.approx(attendu, abs=0.01)


def test_avance_a_2_m_par_seconde_n_invente_pas_une_distance():
    from briques.b06_cerveau.branchements.regles import lire_distance

    assert lire_distance("Avance à 2 m par seconde") is None


@pytest.mark.parametrize("texte,langue", [
    ("Go 5,000 meters forward", "en"), ("Avance de 1 000 mètres", "fr"), ("Gang 5'000 Meter füre", "gsw"),
    ("Avance de cinq mètres cinquante", "fr"), ("往前走五米五", "zh"),
    ("Grab the cup with 1,000 newtons", "en"), ("Prends la tasse avec 20 N", "fr"),
    ("Vai in cucina a un metro al secondo", "it"), ("Va à la cuisine à 2 m par seconde", "fr"),
])
def test_ces_ordres_dangereux_sont_refuses_par_toute_la_chaine(fabrique_systeme, texte, langue):
    """Cerveau à règles, faux robot : refusés et expliqués, rien ne part."""
    async def go():
        s = fabrique_systeme()
        await s.demarrer()
        r = await s.chaine.traiter(texte, langue)
        await s.arreter()
        return r

    r = lancer(go())
    assert r.verdict == "non" and r.statut_action is None, (r.decision, r.reponses)


@pytest.mark.parametrize("texte,langue,question", [
    ("往前走两米左右", "zh", None),
    ("Go forward 2 meters, right?", "en", "sens"), ("All right, go forward 2 meters", "en", "sens"),
    # Relecture du lot A (4e passage) : un mot de côté ailleurs dans la phrase n'est jamais un sens.
    ("Va 2 mètres en ligne droite", "fr", "sens"), ("Va 2 mètres, la tasse est dans ma main droite", "fr", "sens"),
    ("You're right, go 2 meters", "en", "sens"), ("Right, go 2 meters", "en", "sens"),
    ("Okay right, 2 meters please, go", "en", "sens"), ("Vai 2 metri, con la mano destra", "it", "sens"),
    ("Go 2 meters, I left my bag there", "en", "sens"), ("Go 1 meter, right in front of you", "en", "sens"),
    ("Go 1 meter with your back straight", "en", "sens"), ("Go 2 meters left", "en", "sens"),
    ("Va un mètre derrière", "fr", "sens"), ("Go 1 meter to my left", "en", "sens"),
    ("Go 1 meter, people step back", "en", "sens"), ("Va 1 mètre, c'est à droite que tu dois regarder", "fr", "sens"),
    ("Go 2 meters, the exit is to the left", "en", "sens"), ("Go 1 meter, the cup is behind you", "en", "sens"),
    ("Geh 1 Meter, die Tasse steht nach links", "de", "sens"),
    ("Avance de 3 mètres puis recule de 1 mètre", "fr", "sens"), ("Recule, puis avance de 2 mètres", "fr", "sens"),
    ("Avance de 2 mètres, la porte est à droite", "fr", "sens"), ("Avance de 4 mètres puis encore 10 mètres", "fr", "sens"),
    ("Avance de plus de 2 mètres", "fr", "chiffre"), ("Avance de 5 mètres ou plus", "fr", "chiffre"),
    ("Go 5 meters or more", "en", "chiffre"), ("Avance de 2 mètres, trois fois", "fr", "sens"),
    ("Va 1 mètre sur le côté", "fr", "sens"), ("Go 1 meter sideways", "en", "sens"), ("Geh einen Meter zur Seite", "de", "sens"),
    ("Spostati di un metro di lato", "it", "sens"),
])
def test_le_cerveau_a_regles_ne_devine_jamais_le_sens(fabrique_systeme, texte, langue, question):
    """Relecture du lot A : « right? », « all right », « 左右 » (environ) ne sont pas des sens ; deux sens, deux
    distances ou « plus de » → une question. Le sens est dit dans l'annonce. Testé sur faux robot."""
    async def go():
        s = fabrique_systeme()
        await s.demarrer()
        r = await s.chaine.traiter(texte, langue)
        await s.arreter()
        return r

    r = lancer(go())
    if question:
        assert r.decision.genre == "question" and r.statut_action is None, r.reponses
        assert r.decision.question == f"question_{question}"
    else:
        assert r.action.parametres["dx"] == 2.0 and r.action.parametres["dy"] == 0.0, r.action
        assert any(m in r.reponses[0] for m in ("forward", "向前")), r.reponses


@pytest.mark.parametrize("texte,langue,dx,dy", [
    ("Geh 2 Meter links", "de", 0, 2), ("Gang zwöi Meter links", "gsw", 0, 2), ("Va d'un mètre à votre droite", "fr", 0, -1),
    ("Va d'un mètre vers l'arrière", "fr", -1, 0), ("Va à reculons d'un mètre", "fr", -1, 0),
    ("Go 1 meter to the left", "en", 0, 1), ("Move right 1 meter", "en", 0, -1), ("Move 1 meter behind you", "en", -1, 0),
    ("往右走一米", "zh", 0, -1), ("向后走一米", "zh", -1, 0),
    ("Fahr 1 Meter retour", "gsw", -1, 0), ("倒退一米", "zh", -1, 0),
])
def test_un_cote_ou_l_arriere_dit_autrement_n_est_jamais_l_avant(texte, langue, dx, dy):
    """Relecture du lot A (3e passage) : tout mot de côté ou d'arrière compte, même seul."""
    d = lancer(CerveauRegles().decider(texte, langue, HUMANOIDE, MONDE))
    assert d.genre == "action" and (d.action.parametres["dx"], d.action.parametres["dy"]) == (dx, dy), d


@pytest.mark.parametrize("texte,attendu", [
    ("Avance à 50 centimètres par seconde", ("vitesse", 0.5)), ("Va à la cuisine à 50 cm/s", ("vitesse", 0.5)),
    ("Va à la cuisine à 30 mètres par minute", ("vitesse", 0.5)), ("Avance de 2 mètres en une seconde", ("vitesse", 2.0)),
    ("1 m.s-1", ("vitesse", 1.0)), ("1 mètre-seconde", ("vitesse", 1.0)), ("每秒50厘米", ("vitesse", 0.5)),
    ("Avance à 50 centimètres par seconde", ("distance", None)),
    ("Avance de zéro virgule zéro cinq mètre", ("distance", 0.05)), ("null Komma null fünf Meter", ("distance", 0.05)),
    ("zero point zero five meters", ("distance", 0.05)), ("Avance de 0,125 mètre", ("distance", 0.125)),
    ("Va à mètre près", ("distance", None)), ("一百零五米", ("distance", 105.0)),
])
def test_vitesses_et_decimales_relues(texte, attendu):
    from briques.b06_cerveau.branchements.regles import lire_distance, lire_vitesse

    valeur = (lire_vitesse if attendu[0] == "vitesse" else lire_distance)(texte)
    assert valeur == (pytest.approx(attendu[1], abs=0.001) if attendu[1] is not None else None)


@pytest.mark.parametrize("mot", ["unten", "Seiten", "Uneins", "万一"])
def test_des_mots_ordinaires_ne_deviennent_pas_des_nombres(mot):
    from briques.b06_cerveau.branchements.regles import nombres_en_chiffres

    assert not any(c.isdigit() for c in nombres_en_chiffres(mot).replace("1", "")) and "11" not in nombres_en_chiffres(mot)


def test_chiffres_en_desaccord_le_robot_demande(fabrique_systeme):
    """Le cerveau (modèle) comprend 5000 m, la phrase relue dit autre chose : question, aucune action."""
    from commun.chaine import chiffres_en_desaccord

    from briques.b01_prise.actions import ActionDemandee

    assert chiffres_en_desaccord(ActionDemandee(nom="se_deplacer", parametres={"dx": 5000.0}), "Go 5 meters forward")
    assert not chiffres_en_desaccord(ActionDemandee(nom="se_deplacer", parametres={"dx": 5.0}), "Go 5 meters forward")

    def avec(reponse: str, phrase: str):
        modele, _ = _faux_modele([reponse])

        async def go():
            s = fabrique_systeme()
            s.chaine.cerveau = _llm("modele", modele)
            await s.demarrer()
            r = await s.chaine.traiter(phrase, "fr")
            await s.arreter()
            return r

        return lancer(go())

    # Le plus grand des deux dépasse la limite : refus expliqué.
    r = avec('{"type":"action","action":"se_deplacer","parametres":{"dx":5000}}', "Avance de cinq mètres")
    assert r.verdict == "non" and r.statut_action is None
    # Les deux sont permis, mais différents : le robot ne choisit pas, il demande.
    r = avec('{"type":"action","action":"se_deplacer","parametres":{"dx":4}}', "Avance de deux mètres")
    assert r.statut_action is None and r.reponses and "chiffre" in r.reponses[-1]


@pytest.mark.parametrize("texte,negatif", [
    ("Prends la tasse avec 20 N", False), ("Ne va pas à la cuisine", True), ("N'avance pas", True),
    ("对不起，去厨房", False), ("不去厨房", True), ("不要去厨房", True), ("别动", True),
])
def test_la_negation_est_vue_sans_fausse_alarme(texte, negatif):
    from commun.chaine import contient_negation

    assert contient_negation(texte) is negatif


# ---------------------------------------------------------------- banc d'essai
def test_le_banc_a_30_demandes_dans_6_langues():
    from briques.b06_cerveau.banc_cerveau import charger_demandes

    demandes = charger_demandes()
    assert len(demandes) == 30
    assert all(set(d["phrases"]) == {"fr", "de", "gsw", "it", "en", "zh"} for d in demandes)
    sortes = {d["categorie"] for d in demandes}
    assert sortes == {"normal", "dangereux", "flou", "impossible", "pas_un_ordre"}


def test_avec_le_vrai_petit_apertus_si_lance():
    """Le vrai Apertus 0.5B (outils/telecharger.py --seulement apertus-0.5b-gguf), s'il tourne sur le port 8091."""
    try:
        httpx.get("http://127.0.0.1:8091/v1/models", timeout=1)
    except Exception:
        pytest.skip("pas de serveur sur le port 8091")
    c = CerveauLLM("apertus_0.5b", "http://127.0.0.1:8091")
    for texte in ["Va à la cuisine", "Il fait beau", "Fly to the moon"]:
        d = lancer(c.decider(texte, "fr", BRAS, MONDE))
        assert d.genre in ("action", "question")
        if d.genre == "action":
            assert BRAS.sait(d.action.nom)  # jamais hors de la carte, même avec un tout petit modèle


def test_systeme_en_cascade_sans_modele_repond_avec_les_regles(reglages, tmp_path):
    """Réglages réels (cascade), aucun modèle lancé ni téléchargé : le robot répond quand même, et le dit."""
    from commun.systeme import Systeme

    r = {**reglages, "cerveau": {**reglages["cerveau"], "choix": "cascade",
                                 "cascade": [{"nom": "apertus_8b", "url": "http://127.0.0.1:9", "delai_s": 1},
                                             {"nom": "apertus_4b", "url": "http://127.0.0.1:9", "delai_s": 1}, {"nom": "regles"}],
                                 "serveurs": {"apertus_8b": {"modele": "modeles/absent.gguf", "port": 9, "demarrage": "toujours"}}}}

    async def go():
        s = Systeme(r, dossier_journal=tmp_path / "j", acceleration=20)
        await s.demarrer()
        res = await s.chaine.traiter("Regarde la table", "fr")
        await s.arreter()
        return s, res

    s, res = lancer(go())
    assert res.statut_action == "reussie"
    assert [e.donnees["de"] for e in s.bus.historique if e.type == "cerveau_secours"] == ["apertus_8b", "apertus_4b"]
    assert s.serveurs["apertus_8b"].proc is None  # modèle absent : rien n'a été lancé


# ---------------------------------------------------------------- relecture de l'étape 3 : la chaîne avec un cerveau modèle
def _chaine_avec(fabrique_systeme, contenu: str, phrases, delai_s: float = 0.0):
    transport, _ = _faux_modele([contenu] * len(phrases), delai_s=delai_s)

    async def go():
        s = fabrique_systeme(acceleration=1.0)
        s.chaine.cerveau = _llm("modele", transport)
        await s.demarrer()
        res = [await s.chaine.traiter(t, "fr") for t in phrases]
        await asyncio.sleep(0.3)
        etat = await s.prise.etat()
        await s.arreter()
        return s, res, etat

    return lancer(go())


def test_un_stop_pendant_que_le_cerveau_reflechit_annule_sa_reponse(fabrique_systeme):
    transport, _ = _faux_modele(['{"type":"action","action":"se_deplacer","parametres":{"lieu":"cuisine"}}'], delai_s=1.0)

    async def go():
        s = fabrique_systeme(acceleration=1.0)
        s.chaine.cerveau = _llm("modele", transport)
        await s.demarrer()
        aller = asyncio.create_task(s.chaine.traiter("Va à la cuisine", "fr"))
        await asyncio.sleep(0.3)
        await s.chaine.traiter("Stop !", "fr")
        r = await aller
        await asyncio.sleep(0.3)
        etat = await s.prise.etat()
        await s.arreter()
        return r, etat

    r, etat = lancer(go())
    assert r.statut_action is None and not etat.en_mouvement


@pytest.mark.parametrize("phrase,params,attendu", [
    ("Recule de 2 mètres", {"dx": -2}, (-2.0, 0.0)),
    ("Va 2 mètres à gauche", {"dx": 0, "dy": 2}, (0.0, 2.0)),
    ("Avance un peu", {"dx": 3}, (0.5, 0.0)),
])
def test_le_verrou_garde_le_sens_et_l_axe(phrase, params, attendu):
    from briques.b01_prise.actions import ActionDemandee
    from commun.chaine import verrou_des_chiffres

    a = verrou_des_chiffres(ActionDemandee(nom="se_deplacer", parametres=params), phrase)
    assert (a.parametres["dx"], a.parametres["dy"]) == attendu


@pytest.mark.parametrize("phrase,contenu", [
    ("Fais quelque chose d'amusant", '{"type":"action","action":"se_deplacer","parametres":{"dx":4.9}}'),
    ("Fais quelque chose d'amusant", '{"type":"action","action":"rejouer_geste","parametres":{"nom":"incliner"}}'),
    ("Ne va surtout pas à la cuisine", '{"type":"action","action":"se_deplacer","parametres":{"lieu":"cuisine"}}'),
])
def test_rien_d_invente_et_pas_d_action_sur_une_negation(fabrique_systeme, phrase, contenu):
    s, (r,), etat = _chaine_avec(fabrique_systeme, contenu, [phrase])
    assert r.statut_action is None and not etat.en_mouvement


def test_pluriels_et_mots_composes_acceptes(fabrique_systeme):
    s, (r,), _ = _chaine_avec(fabrique_systeme, '{"type":"action","action":"regarder","parametres":{"cible":"tasse"}}',
                              ["Regarde les tasses"])
    assert r.statut_action == "reussie"
