"""Brique 7 — le gardien complet. Testé sur faux robot, Internet coupé (conftest.py).

Les 10 ordres dangereux (ordres_dangereux.yaml), les règles lues et rechargées, une règle changée en direct,
le vote du public, le verdict « humain », la distance aux personnes, les zones, et le chien de garde.
"""
from __future__ import annotations

import asyncio
import math
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.adaptateur import EtatRobot
from briques.b01_prise.carte import CarteIdentite
from briques.b01_prise.raisons import CODES, CODES_HUMAIN
from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES
from briques.b07_gardien.gardien import Gardien, LimitesParDefaut
from briques.b07_gardien.geometrie import Rectangle, distance_point_segment
from briques.b07_gardien.perception import PARTOUT, Perception, PersonneVue
from briques.b07_gardien.regles import CHEMIN_REGLES, SORTES, ReglesInvalides, charger_regles, problemes
from briques.b07_gardien.vote import appliquer_vote, depouiller
from commun.bus import Bus
from commun.monde import Monde
from commun.phrases import _chercher, dire, expliquer_refus
from conftest import lancer, robot

ICI = Path(__file__).resolve().parents[1]
ORDRES = yaml.safe_load((ICI / "ordres_dangereux.yaml").read_text(encoding="utf-8"))["ordres"]
HUMANOIDE = CarteIdentite.charger(DOSSIER_CARTES / "humanoide.yaml")
CODE = {"X-Code-Equipe": "code-de-test"}
LANGUES_PHRASES = ["fr", "de", "it", "en", "zh"]


@pytest.fixture
def systeme(tmp_path, reglages):
    """Un Système complet (faux robot, cerveau à règles), main levée et vote allumés, mots appris dans tmp_path."""
    from commun.systeme import Systeme

    def fabrique(carte: str = "humanoide", acceleration: float = 20.0, attente_humain_s: float = 120.0):
        inter = dict(reglages.get("interrupteurs") or {})
        inter.update(main_levee={"actif": True}, vote_public={"actif": True})
        r = {**reglages, "robot": {**reglages["robot"], "carte": carte},
             "ecran": {**reglages["ecran"], "code_equipe": "code-de-test"},
             "cerveau": {**reglages["cerveau"], "choix": "regles"}, "interrupteurs": inter,
             "gardien": {"attente_humain_s": attente_humain_s},
             "doute": {"aides_apprises": str(tmp_path / "aides_apprises.yaml")}}
        return Systeme(r, dossier_journal=tmp_path / "journal", acceleration=acceleration)

    return fabrique


def _scenario(fabrique, carte="humanoide", acceleration=20.0, **kw):
    def deco(fonction):
        async def go():
            s = fabrique(carte, acceleration, **kw)
            await s.demarrer()
            try:
                return await fonction(s)
            finally:
                await s.arreter()

        return lancer(go())

    return deco


async def _preparer(s, avant: dict | None) -> None:
    avant = avant or {}
    if "allumer" in avant:
        await s.gardien.changer_regle(avant["allumer"], active=True, qui="test")
    if "personne" in avant:
        s.gardien.perception.placer_personne("essai", avant["personne"]["x"], avant["personne"]["y"])
    if "vote" in avant:
        await appliquer_vote(s.gardien, avant["vote"]["vote"], avant["vote"]["resultats"], qui="test")


def _evenements(s, type_: str) -> list:
    return [e for e in s.bus.historique if e.type == type_]


# ================================================================ les règles, lues au démarrage
def test_les_regles_sont_lues_au_demarrage_et_disent_la_meme_chose_que_leurs_valeurs():
    g = Gardien(Bus())
    assert g.chemin_regles == CHEMIN_REGLES
    ids = {r.id for r in g.regles.regles}
    assert {"vitesse_max", "force_max", "distance_personnes", "escalier", "cuisine_pendant_le_service",
            "rester_dans_la_halle", "valise", "poids_max", "objets_fragiles", "verser"} <= ids
    assert all(r.sorte in SORTES and r.phrase.strip() for r in g.regles.regles)
    assert problemes(g.regles, Monde.charger()) == []
    guide = (ICI / "GUIDE.md").read_text(encoding="utf-8")
    assert all(f"`{s}`" in guide for s in SORTES), "chaque sorte de règle est expliquée dans GUIDE.md"


@pytest.mark.parametrize("remplacer,attendu", [
    (("m_s: 0.3", "m_s: 0.5"), "ne dit pas le chiffre 0,5"),          # la phrase dit 0,3, la valeur 0,5
    (("sorte: force_max", "sorte: force_maxi"), "sorte inconnue"),
    (("lieu: escalier", "lieu: grenier"), "lieu inconnu"),
    (("objets: [valise]", "objets: [parapluie]"), "objet inconnu"),
    (("valeurs: {n: 15}", "valeurs: {n: 15, laser: 1}"), "valeurs inconnues"),
    # Relecture sécurité du lot B : une clé mal écrite n'est plus ignorée en silence.
    (("    en_direct: false\n", "    en_dirct: false\n"), "règle « distance_personnes » : clé inconnue « en_dirct »"),
    (("plus_lent: {texte: \"Oui : 0,2 mètre par seconde\", valeurs: {m_s: 0.2}}",
      "plus_lent: {texte: \"Oui : 0,2 mètre par seconde\", valeurs: {m_s: 0.2}, couleur: rouge}"),
     "vote « vitesse », choix « plus_lent » : clé inconnue « couleur »"),
    (("\nvotes:\n", "\nvote:\n"), "le fichier : clé inconnue « vote »"),
    # Sans distance aux personnes ou sans zone permise (allumées), le gardien ne démarre pas.
    (("si_personnes_inconnues: humain}\n", "si_personnes_inconnues: humain}\n    active: false\n"),
     "il manque la règle de la distance aux personnes"),
    (("    sorte: zone_permise\n", "    sorte: zone_interdite\n"), "il manque la règle de la zone permise"),
    (("actions: [se_deplacer, saisir, poser, rejouer_geste]", "actions: []"), "« actions » est vide"),
])
def test_un_fichier_de_regles_faux_empeche_de_demarrer_et_dit_quoi_corriger(tmp_path, remplacer, attendu):
    texte = CHEMIN_REGLES.read_text(encoding="utf-8")
    assert remplacer[0] in texte
    faux = tmp_path / "regles.yaml"
    faux.write_text(texte.replace(remplacer[0], remplacer[1], 1), encoding="utf-8")
    with pytest.raises(ReglesInvalides) as e:
        Gardien(Bus(), regles=faux)
    assert attendu in str(e.value)


@pytest.mark.parametrize("texte", ["regles: []\n", "regles: []\nvotes: []\n"])
def test_un_fichier_sans_aucune_regle_empeche_de_demarrer(tmp_path, texte):
    (tmp_path / "regles.yaml").write_text(texte, encoding="utf-8")
    with pytest.raises(ReglesInvalides, match="aucune règle"):
        Gardien(Bus(), regles=tmp_path / "regles.yaml")


def test_chaque_code_de_refus_a_sa_phrase_dans_les_cinq_langues():
    for code in CODES:
        for lg in LANGUES_PHRASES:
            assert _chercher(lg, f"refus.{code}"), f"phrases.yaml : refus.{code} manque en {lg}"
    for lg in LANGUES_PHRASES + ["gsw"]:  # suisse allemand → allemand
        assert "…" not in dire("main_levee", lg) and dire("main_levee", lg) != "main_levee"
    assert CODES_HUMAIN <= set(CODES)


# ================================================================ les 10 ordres dangereux
def test_il_y_a_dix_ordres_dangereux_dans_les_six_langues():
    assert len(ORDRES) == 10 and len({o["id"] for o in ORDRES}) == 10
    assert {o["langue"] for o in ORDRES} == {"fr", "de", "gsw", "it", "en", "zh"}


@pytest.mark.parametrize("ordre", ORDRES, ids=[o["id"] for o in ORDRES])
def test_dix_ordres_dangereux_par_la_chaine_tous_refuses_et_expliques(systeme, ordre):
    @_scenario(systeme)
    async def resultat(s):
        await _preparer(s, ordre.get("avant"))
        depart = (await s.prise.etat()).position
        r = await s.chaine.traiter(ordre["texte"], ordre["langue"])
        await asyncio.sleep(0.1)
        return r, depart, await s.prise.etat(), _evenements(s, "action_demarree"), _evenements(s, "gardien_decision")

    r, depart, etat, demarrees, decisions = resultat
    assert r.decision.genre == "action", "le cerveau à règles a compris l'ordre"
    assert r.verdict == "non" and r.statut_action is None
    assert not demarrees and not etat.en_mouvement and etat.position == depart, "le robot n'a pas bougé"
    assert ordre["code"] in [x["code"] for x in decisions[-1].donnees["raisons"]]
    explication = r.reponses[-1]
    assert explication.startswith(dire("refus_intro", ordre["langue"])) and ordre["doit_contenir"] in explication
    assert "…" not in explication and "{" not in explication


@pytest.mark.parametrize("ordre", ORDRES, ids=[o["id"] for o in ORDRES])
def test_dix_ordres_dangereux_directement_au_gardien(systeme, ordre):
    @_scenario(systeme)
    async def resultat(s):
        await _preparer(s, ordre.get("avant"))
        return await s.gardien.verifier(ActionDemandee(**ordre["action"]), s.prise.carte(), demandeur="agent")

    decision, ticket = resultat
    assert decision.verdict == "non" and ticket is None
    assert ordre["code"] in [x.code for x in decision.raisons]
    assert ordre["doit_contenir"] in expliquer_refus(decision.raisons, ordre["langue"])


# ================================================================ la plus stricte gagne ; changer en direct
def test_la_limite_la_plus_stricte_gagne():
    assert Gardien(Bus(), LimitesParDefaut(vitesse_m_s=0.25)).plafonds()["vitesse"] == 0.25  # reglages plus strict

    async def go():
        g = Gardien(Bus())
        await g.changer_regle("vitesse_max", valeurs={"m_s": 0.2}, qui="test")
        assert g.plafonds()["vitesse"] == 0.2  # la règle plus stricte
        with pytest.raises(ValueError, match="reglages.yaml"):
            await g.changer_regle("vitesse_max", valeurs={"m_s": 0.5}, qui="test")  # jamais au-dessus de reglages
        assert g.plafonds()["vitesse"] == 0.2
        d, _ = await g.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"}), HUMANOIDE)
        assert d.action.parametres["vitesse"] == 0.2  # vitesse non dite : la plus petite limite

    lancer(go())


def test_regle_changee_en_direct_notee_dans_la_boite_noire(systeme):
    @_scenario(systeme)
    async def _(s):
        nouvelle = await s.gardien.changer_regle("cuisine_pendant_le_service", active=True, qui="Hiba")
        assert nouvelle.active
        r = await s.chaine.traiter("Geh in die Küche", "de")
        assert r.verdict == "non" and "Dorthin darf ich nicht: Küche" in r.reponses[-1]
        await s.gardien.changer_regle("vitesse_max", valeurs={"m_s": 0.2}, qui="Hiba")
        ev = [e for e in _evenements(s, "regle_changee") if e.donnees["regle"] == "vitesse_max"][0]
        assert ev.donnees["qui"] == "Hiba" and ev.donnees["avant"]["valeurs"]["m_s"] == 0.3
        assert ev.donnees["apres"]["valeurs"]["m_s"] == 0.2 and "0,2 mètre" in ev.donnees["apres"]["phrase"]
        await s.gardien.changer_regle("cuisine_pendant_le_service", active=False, qui="Hiba")
        r = await s.chaine.traiter("Geh in die Küche", "de")
        assert r.statut_action == "reussie"
        journal = s.boite_noire.fichier.read_text(encoding="utf-8")
        assert journal.count('"regle_changee"') == 3 and "Hiba" in journal


@pytest.mark.parametrize("ident,changement", [
    ("distance_personnes", {"active": False}), ("valise", {"active": False}), ("escalier", {"active": False}),
    ("poids_max", {"active": False}), ("rester_dans_la_halle", {"active": False}),
    ("distance_personnes", {"valeurs": {"m": 0.1}}), ("objets_fragiles", {"valeurs": {"objets": []}}),
    ("vitesse_max", {"valeurs": {"m_s": -1}}), ("vitesse_max", {"valeurs": {"m_s": math.nan}}), ("inconnue", {"active": True}),
])
def test_certaines_regles_ne_se_changent_pas_en_direct(ident, changement):
    async def go():
        g = Gardien(Bus())
        with pytest.raises(ValueError):
            await g.changer_regle(ident, qui="test", **changement)
        return g

    g = lancer(go())
    assert g.regles.regle("distance_personnes").active and g.regles.regle("valise").active


def test_une_regle_qui_ne_dit_pas_en_direct_ne_se_change_jamais_en_direct():
    """Relecture du lot B : `en_direct` est faux par défaut (ici « objets_fragiles » et « verser » ne le disent pas)."""
    async def go():
        g = Gardien(Bus())
        for ident in ("objets_fragiles", "verser"):
            assert g.regles.regle(ident).en_direct is False
            with pytest.raises(ValueError, match="ne se change pas en direct"):
                await g.changer_regle(ident, active=False, qui="test")
        await g.changer_regle("force_max", valeurs={"n": 10}, qui="test")  # écrit « en_direct: true » : permis
        assert g.plafonds()["force"] == 10
        with pytest.raises(ValueError, match="reglages.yaml"):
            await g.changer_regle("force_max", valeurs={"n": 40}, qui="test")  # jamais au-dessus de reglages
        return g

    g = lancer(go())
    assert g.regles.regle("objets_fragiles").active and g.regles.regle("verser").active


def _regles_avec_distance_en_direct(tmp_path, en_plus: str = "") -> Path:
    texte = CHEMIN_REGLES.read_text(encoding="utf-8")
    ancien = "si_personnes_inconnues: humain}\n    en_direct: false\n"
    assert ancien in texte
    fichier = tmp_path / "regles.yaml"
    fichier.write_text(texte.replace(ancien, "si_personnes_inconnues: humain}\n    en_direct: true\n") + en_plus,
                       encoding="utf-8")
    return fichier


def test_la_distance_aux_personnes_ne_peut_que_grandir_en_direct_et_ne_s_eteint_jamais(tmp_path):
    """Même écrite « en_direct: true » : plus grande (plus stricte) oui ; plus petite ou éteinte, jamais."""
    async def go():
        g = Gardien(Bus(), regles=_regles_avec_distance_en_direct(tmp_path))
        nouvelle = await g.changer_regle("distance_personnes", valeurs={"m": 1.5}, qui="test")
        assert nouvelle.valeurs["m"] == 1.5 and "1,5 mètre" in nouvelle.phrase
        with pytest.raises(ValueError, match="ne peut que grandir"):
            await g.changer_regle("distance_personnes", valeurs={"m": 1.2}, qui="test")  # moins strict qu'avant
        with pytest.raises(ValueError, match="ne s'éteint jamais"):
            await g.changer_regle("distance_personnes", active=False, qui="test")
        assert g.regles.regle("distance_personnes").active and g.regles.regle("distance_personnes").valeurs["m"] == 1.5

    lancer(go())


def test_un_vote_ne_peut_pas_rapprocher_le_robot_des_personnes(tmp_path):
    """Un vote écrit à l'avance qui ferait baisser la distance (ou l'éteindre) : le gardien ne démarre pas."""
    for choix, attendu in (("{texte: \"0,5 m\", valeurs: {m: 0.5}}", "ne peut que grandir"),
                           ("{texte: \"éteinte\", active: false}", "ne s'éteint jamais")):
        vote = ("  - id: distance\n    question: \"Plus loin ?\"\n    regle: distance_personnes\n    choix:\n"
                f"      plus_loin: {{texte: \"2 m\", valeurs: {{m: 2}}}}\n      moins: {choix}\n")
        with pytest.raises(ReglesInvalides, match=attendu):
            Gardien(Bus(), regles=_regles_avec_distance_en_direct(tmp_path, vote))

    async def go():  # un vote qui l'agrandit : permis
        vote = ("  - id: distance\n    question: \"Plus loin ?\"\n    regle: distance_personnes\n    choix:\n"
                "      plus_loin: {texte: \"2 m\", valeurs: {m: 2}}\n      pareil: {texte: \"1 m\", valeurs: {m: 1}}\n")
        g = Gardien(Bus(), regles=_regles_avec_distance_en_direct(tmp_path, vote))
        assert (await appliquer_vote(g, "distance", {"plus_loin": 5, "pareil": 1}))["change"] is True
        assert g.regles.regle("distance_personnes").valeurs["m"] == 2
        with pytest.raises(ValueError, match="ne peut que grandir"):  # revenir à 1 m par un vote : non
            await appliquer_vote(g, "distance", {"plus_loin": 1, "pareil": 5})

    lancer(go())


def test_relire_les_regles_garde_ce_qui_a_ete_rendu_plus_strict_en_direct(tmp_path):
    """Relecture du lot B : relire le fichier n'annule pas en silence un changement plus strict fait en direct.
    Il est gardé, et c'est écrit dans la réponse et dans la boîte noire."""
    fichier = _regles_avec_distance_en_direct(tmp_path)

    async def go():
        bus = Bus()
        g = Gardien(bus, regles=fichier)
        await appliquer_vote(g, "vitesse", {"plus_lent": 9, "comme_avant": 1})  # 0,2 m/s
        await g.changer_regle("cuisine_pendant_le_service", active=True, qui="Hiba")  # le fichier dit : éteinte
        await g.changer_regle("distance_personnes", valeurs={"m": 2}, qui="Hiba")  # le fichier dit : 1 m
        res = await g.recharger(qui="Hiba")
        assert g.plafonds()["vitesse"] == 0.2 and "0,2 mètre" in g.regles.regle("vitesse_max").phrase
        assert g.regles.regle("cuisine_pendant_le_service").active
        assert g.regles.regle("distance_personnes").valeurs["m"] == 2
        assert {x["regle"] for x in res["gardees"]} == {"vitesse_max", "cuisine_pendant_le_service", "distance_personnes"}
        note = [e for e in bus.historique if e.type == "note" and e.source == "gardien"][-1]
        assert "gardés" in note.donnees["texte"] and "vitesse_max" in note.donnees["texte"]
        # Le fichier devient plus strict que le direct : c'est le fichier qui gagne, et plus rien n'est « gardé ».
        texte = fichier.read_text(encoding="utf-8")
        fichier.write_text(texte.replace("0,3 mètre", "0,15 mètre").replace("m_s: 0.3}", "m_s: 0.15}", 1), encoding="utf-8")
        res = await g.recharger(qui="Hiba")
        assert g.plafonds()["vitesse"] == 0.15 and "vitesse_max" not in {x["regle"] for x in res["gardees"]}
        assert g.regles.regle("distance_personnes").valeurs["m"] == 2  # toujours plus strict que le fichier
        # Un changement moins strict fait en direct (vitesse remise plus haut) : le fichier relu gagne, normalement.
        await g.changer_regle("vitesse_max", valeurs={"m_s": 0.25}, qui="Hiba")
        res = await g.recharger(qui="Hiba")
        assert g.plafonds()["vitesse"] == 0.15 and "vitesse_max" not in {x["regle"] for x in res["gardees"]}

    lancer(go())


def test_regles_rechargees_depuis_le_fichier(tmp_path):
    fichier = tmp_path / "regles.yaml"
    fichier.write_text(CHEMIN_REGLES.read_text(encoding="utf-8"), encoding="utf-8")

    async def go():
        bus = Bus()
        g = Gardien(bus, regles=fichier)
        texte = fichier.read_text(encoding="utf-8")
        fichier.write_text(texte.replace("0,3 mètre", "0,25 mètre").replace("m_s: 0.3", "m_s: 0.25"), encoding="utf-8")
        assert await g.recharger(qui="Hiba") == {"changees": ["vitesse_max"], "gardees": []}
        assert g.plafonds()["vitesse"] == 0.25
        ev = [e for e in bus.historique if e.type == "regle_changee"][-1]
        assert ev.donnees["comment"] == "fichier relu" and ev.donnees["apres"]["valeurs"]["m_s"] == 0.25
        fichier.write_text("regles: [{id: x, phrase: '', sorte: rien}]", encoding="utf-8")  # fichier cassé
        with pytest.raises(ReglesInvalides):
            await g.recharger()
        assert g.plafonds()["vitesse"] == 0.25 and g.regles.regle("valise")  # les règles d'avant restent

    lancer(go())


def test_vote_du_public():
    assert depouiller({"a": 3, "b": 3}) is None and depouiller({"a": 0}) is None and depouiller({"a": 4, "b": 1}) == "a"

    async def go():
        bus = Bus()
        g = Gardien(bus)
        assert (await appliquer_vote(g, "vitesse", {"plus_lent": 4, "comme_avant": 4}))["change"] is False  # égalité
        assert g.plafonds()["vitesse"] == 0.3
        res = await appliquer_vote(g, "vitesse", {"plus_lent": 12, "comme_avant": 5})
        assert res["gagnant"] == "plus_lent" and g.plafonds()["vitesse"] == 0.2 and "0,2" in res["phrase"]
        ev = [e for e in bus.historique if e.type == "regle_changee"][-1]
        assert ev.donnees["vote"]["resultats"] == {"plus_lent": 12, "comme_avant": 5} and ev.donnees["qui"] == "vote du public"
        await appliquer_vote(g, "service", {"oui": 30, "non": 2})
        assert g.regles.regle("cuisine_pendant_le_service").active
        with pytest.raises(ValueError):
            await appliquer_vote(g, "vitesse", {"tres_vite": 99})
        with pytest.raises(ValueError):
            await appliquer_vote(g, "inconnu", {"oui": 1})

    lancer(go())


def test_un_vote_qui_depasserait_reglages_est_refuse_au_moment_du_vote(tmp_path):
    """Un choix de vote à 0,9 m/s : le robot démarre quand même, mais ce choix ne s'applique jamais."""
    texte = CHEMIN_REGLES.read_text(encoding="utf-8").replace("valeurs: {m_s: 0.3}}", "valeurs: {m_s: 0.9}}")
    assert "m_s: 0.9" in texte
    (tmp_path / "regles.yaml").write_text(texte, encoding="utf-8")
    assert charger_regles(tmp_path / "regles.yaml", Monde.charger()).vote("vitesse")

    async def go():
        g = Gardien(Bus(), regles=tmp_path / "regles.yaml")
        with pytest.raises(ValueError, match="ne peut pas dépasser"):
            await appliquer_vote(g, "vitesse", {"plus_lent": 1, "comme_avant": 9})
        assert g.plafonds()["vitesse"] == 0.3

    lancer(go())


def test_l_ecran_change_une_regle_avec_le_code_d_equipe(systeme):
    from briques.b13_ecran.serveur import creer_app

    s = systeme()
    with TestClient(creer_app(s)) as client:
        regles = client.get("/api/gardien/regles").json()  # lisible par tous
        assert any(r["id"] == "valise" and "valise" in r["phrase"] for r in regles["regles"])
        corps = {"id": "cuisine_pendant_le_service", "active": True, "qui": "Hiba"}
        assert client.post("/api/gardien/regle", json=corps).status_code == 403  # sans le code d'équipe
        assert client.post("/api/gardien/regle", json=corps, headers=CODE).json()["regle"]["active"] is True
        assert client.post("/api/gardien/regle", json={"id": "valise", "active": False}, headers=CODE).status_code == 400
        vote = {"vote": "vitesse", "resultats": {"plus_lent": 7, "comme_avant": 2}}
        assert client.post("/api/gardien/vote", json=vote, headers=CODE).json()["gagnant"] == "plus_lent"
        relu = client.post("/api/gardien/recharger", json={"qui": "Hiba"}, headers=CODE).json()
        assert relu["ok"] and "ATTENTION" in relu["message"]
        assert {x["regle"] for x in relu["gardees"]} == {"vitesse_max", "cuisine_pendant_le_service"}
        # Le vote (0,2 m/s) était plus strict que le fichier (0,3) : il est gardé, pas annulé en silence.
        assert client.get("/api/gardien/regles").json()["plafonds"]["vitesse"] == 0.2
        s.reglages["interrupteurs"]["vote_public"] = {"actif": False}
        assert client.post("/api/gardien/vote", json=vote, headers=CODE).status_code == 400  # interrupteur éteint


# ================================================================ « demande à un humain »
def test_verdict_humain_l_action_ne_part_pas_le_robot_leve_la_main_puis_un_humain_accepte(systeme):
    @_scenario(systeme, "bras")
    async def _(s):
        r = await s.chaine.traiter("Prends la tasse", "fr")
        assert r.verdict == "humain" and r.statut_action is None
        assert r.reponses[-1].startswith("Je lève la main : j'ai besoin d'aide.") and "fragile : tasse" in r.reponses[-1]
        aide = _evenements(s, "aide_demandee")[-1]
        assert aide.donnees["raison"] == "gardien" and aide.donnees["raisons"][0]["code"] == "objet_fragile"
        assert not _evenements(s, "action_demarree") and not _evenements(s, "confirmation_demandee")
        (attente,) = s.gardien.demandes_en_attente()
        assert attente["numero"] == aide.donnees["numero"] and attente["action"]["parametres"]["objet"] == "tasse"
        fin = await s.chaine.reponse_humaine(attente["numero"], True, qui="Hiba", attendre_fin=True)
        assert fin.verdict == "oui" and fin.statut_action == "reussie"
        assert (await s.prise.etat()).objet_tenu == "tasse"
        assert _evenements(s, "aide_recue")[-1].donnees["accepte"] is True
        assert _evenements(s, "gardien_decision")[-1].donnees["demandeur"] == "humain:Hiba"
        assert s.compteur.fiche().aides_demandees == 1 and s.compteur.fiche().aides_recues == 1
        assert s.gardien.demandes_en_attente() == []


def test_verdict_humain_un_humain_refuse(systeme):
    @_scenario(systeme, "bras")
    async def _(s):
        r = await s.chaine.traiter("Nimm die Tasse", "de")
        assert r.reponses[-1].startswith("Ich hebe die Hand")
        fin = await s.chaine.reponse_humaine(s.gardien.demandes_en_attente()[0]["numero"], False, qui="Hiba")
        assert fin.verdict == "non" and fin.reponses[-1] == "Das kann ich nicht. Ein Mensch hat Nein gesagt."
        assert not _evenements(s, "action_demarree")


def test_un_humain_accepte_mais_le_gardien_reverifie_tout(systeme):
    """Entre la demande et le « oui », une personne s'approche du bras : c'est « non », malgré l'accord."""
    @_scenario(systeme, "bras")
    async def _(s):
        await s.chaine.traiter("Take the cup", "en")
        numero = s.gardien.demandes_en_attente()[0]["numero"]
        s.gardien.perception.placer_personne("enfant", 5.3, 2.6)  # 0,3 m du bras
        fin = await s.chaine.reponse_humaine(numero, True, qui="Hiba", attendre_fin=True)
        assert fin.verdict == "non" and "too close to a person" in fin.reponses[-1]
        assert not _evenements(s, "action_demarree") and (await s.prise.etat()).objet_tenu is None


def test_un_stop_ou_un_arret_d_urgence_annule_la_demande_a_un_humain(systeme):
    @_scenario(systeme, "bras")
    async def _(s):
        await s.chaine.traiter("Prends la tasse", "fr")
        numero = s.gardien.demandes_en_attente()[0]["numero"]
        await s.chaine.traiter("Stop !", "fr")
        assert s.gardien.demandes_en_attente() == []
        assert await s.chaine.reponse_humaine(numero, True, qui="Hiba", attendre_fin=True) is None
        await s.chaine.traiter("Prends la tasse", "fr")
        numero = s.gardien.demandes_en_attente()[0]["numero"]
        await s.prise.arret_urgence(raison="test")
        assert await s.chaine.reponse_humaine(numero, True, qui="Hiba", attendre_fin=True) is None
        assert not _evenements(s, "action_demarree") or all(
            e.donnees["action"]["nom"] == "arreter" for e in _evenements(s, "action_demarree"))
        assert (await s.prise.etat()).objet_tenu is None


def test_une_demande_trop_ancienne_ne_part_plus(systeme):
    @_scenario(systeme, "bras", attente_humain_s=0.1)
    async def _(s):
        await s.chaine.traiter("Prends la tasse", "fr")
        numero = _evenements(s, "aide_demandee")[-1].donnees["numero"]
        await asyncio.sleep(0.2)
        fin = await s.chaine.reponse_humaine(numero, True, qui="Hiba", attendre_fin=True)
        assert fin.verdict == "non" and "trop ancienne" in fin.reponses[-1]
        assert not _evenements(s, "action_demarree")


def test_un_non_ne_devient_jamais_humain_et_un_faux_numero_ne_donne_rien(systeme):
    @_scenario(systeme, "bras")
    async def _(s):
        d, t = await s.gardien.verifier(ActionDemandee(nom="saisir", parametres={"objet": "tasse", "force": 100}),
                                        s.prise.carte())
        assert d.verdict == "non" and t is None and s.gardien.demandes_en_attente() == []  # force : non, pas « humain »
        d, t = await s.gardien.reponse_humaine("pas-un-numero", True, s.prise.carte(), qui="pirate")
        assert d.verdict == "non" and t is None and d.raisons[0].code == "demande_perimee"
        assert s.compteur.fiche().aides_recues == 0  # un faux numéro n'est pas une aide


def test_modifier_l_action_apres_la_demande_ne_change_pas_ce_que_l_humain_accepte(systeme):
    @_scenario(systeme, "bras")
    async def _(s):
        d, _ = await s.gardien.verifier(ActionDemandee(nom="saisir", parametres={"objet": "tasse"}), s.prise.carte())
        assert d.verdict == "humain"
        d.action.parametres["objet"] = "valise"  # on triche après coup
        d.action.parametres["force"] = 99
        oui, ticket = await s.gardien.reponse_humaine(d.numero_demande, True, s.prise.carte(), qui="Hiba")
        assert oui.verdict == "oui" and ticket.action.parametres["objet"] == "tasse" and ticket.action.parametres["force"] <= 15
        deux, ticket2 = await s.gardien.reponse_humaine(d.numero_demande, True, s.prise.carte(), qui="Hiba")  # double clic
        assert deux.verdict == "non" and ticket2 is None and s.compteur.fiche().aides_recues == 1


def test_l_ecran_montre_la_main_levee_et_un_humain_repond(systeme):
    from briques.b13_ecran.serveur import creer_app

    s = systeme("bras")
    with TestClient(creer_app(s)) as client:
        assert client.post("/api/dire", json={"texte": "Prends la tasse", "langue": "fr"}, headers=CODE).json()["verdict"] == "humain"
        (attente,) = client.get("/api/aides").json()["en_attente"]
        corps = {"numero": attente["numero"], "accepte": True, "qui": "Hiba"}
        assert client.post("/api/aide/repondre", json=corps).status_code == 403  # sans le code d'équipe
        assert client.post("/api/aide/repondre", json=corps, headers=CODE).json()["ok"] is True
        for _ in range(100):
            if client.get("/api/etat").json()["objet_tenu"] == "tasse":
                break
            time.sleep(0.05)
        assert client.get("/api/etat").json()["objet_tenu"] == "tasse"
        assert client.get("/api/fiche").json()["aides_demandees"] == 1


def test_verser_demande_un_humain_et_un_objet_inconnu_aussi(systeme):
    @_scenario(systeme, "bras")
    async def _(s):
        r = await s.chaine.traiter("Verse", "fr")
        assert r.verdict == "humain" and "faire un geste" in r.reponses[-1]
        d, _ = await s.gardien.verifier(ActionDemandee(nom="saisir", parametres={"objet": "parapluie"}), s.prise.carte())
        assert d.verdict == "humain" and d.raisons[0].code == "poids_inconnu"


# ================================================================ distance aux personnes, zones, perception
def test_geometrie():
    assert distance_point_segment((3, 2), (1, 1), (5, 3)) == pytest.approx(0)
    assert distance_point_segment((3, 3.5), (1, 1), (5, 3)) == pytest.approx(6 / math.hypot(4, 2))
    assert distance_point_segment((0, 0), (1, 1), (1, 1)) == pytest.approx(math.sqrt(2))
    r = Rectangle(2, 2, 3, 3)
    assert r.coupe((0, 2.5), (5, 2.5)) and r.coupe((2.5, 0), (2.5, 9)) and not r.coupe((0, 0), (5, 1))
    assert r.coupe((0, 0), (4, 4)) and not r.coupe((0, 4), (1, 5)) and r.coupe((2.5, 2.5), (9, 9))


def test_le_chemin_passe_trop_pres_d_une_personne_ou_assez_loin(systeme):
    @_scenario(systeme)
    async def _(s):
        a = ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"})
        s.gardien.perception.placer_personne("p", 3.0, 3.5)  # 1,34 m du chemin
        d, t = await s.gardien.verifier(a, s.prise.carte())
        assert d.verdict == "oui" and t is not None
        s.gardien.perception.placer_personne("p", 3.0, 2.6)  # 0,45 m du chemin
        d, t = await s.gardien.verifier(a, s.prise.carte())
        assert d.verdict == "non" and d.raisons[0].code == "trop_pres_personne" and d.raisons[0].details["distance"] < 1
        s.gardien.perception.retirer_personne("p")
        relatif = ActionDemandee(nom="se_deplacer", parametres={"dx": 2.0})  # cap 0 : vers (3, 1)
        s.gardien.perception.placer_personne("q", 2.0, 1.5)
        d, _ = await s.gardien.verifier(relatif, s.prise.carte())
        assert d.verdict == "non" and d.raisons[0].code == "trop_pres_personne"


def _gardien_avec(position=None, liaison=True, simulation=True, **kw) -> Gardien:
    async def lire_etat():
        return EtatRobot(position=position or {}, liaison_ok=liaison)

    return Gardien(Bus(), perception=Perception(lire_etat=lire_etat, simulation=simulation, **kw))


def test_les_zones_le_chemin_et_la_halle():
    async def go():
        g = _gardien_avec({"x": 6.5, "y": 4.5, "cap": 0})
        await g.changer_regle("cuisine_pendant_le_service", active=True, qui="test")
        traverse = ActionDemandee(nom="se_deplacer", parametres={"dx": 3.0})  # de (6,5 ; 4,5) à (9,5 ; 4,5)
        d, _ = await g.verifier(traverse, HUMANOIDE)
        assert d.verdict == "non" and d.raisons[0].code == "chemin_zone_interdite"
        assert "Mein Weg würde durch einen verbotenen Ort führen: Küche" in expliquer_refus(d.raisons, "gsw")
        g = _gardien_avec({"x": 8.0, "y": 4.5, "cap": 0})  # déjà DANS la cuisine : il a le droit d'en sortir
        await g.changer_regle("cuisine_pendant_le_service", active=True, qui="test")
        d, _ = await g.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"}), HUMANOIDE)
        assert d.verdict == "oui"
        g = _gardien_avec({"x": 1.0, "y": 1.0, "cap": 0})
        d, _ = await g.verifier(ActionDemandee(nom="se_deplacer", parametres={"dy": -3.0}), HUMANOIDE)  # 3 m à droite
        assert d.verdict == "non" and d.raisons[0].code == "hors_zone_permise"
        assert "I must stay inside this area: the hall" in expliquer_refus(d.raisons, "en")
        d, _ = await g.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "lune"}), HUMANOIDE)
        assert d.verdict == "non" and d.raisons[0].code == "lieu_inconnu"

    lancer(go())


def test_vrai_robot_sans_les_yeux_le_gardien_demande_un_humain_avant_de_bouger():
    async def go():
        g = _gardien_avec({"x": 1.0, "y": 1.0, "cap": 0}, simulation=False, fraicheur_max_s=0.1)
        with pytest.raises(ValueError):
            g.perception.placer_personne("faux", 2, 2)  # jamais de personne simulée avec un vrai robot
        aller = ActionDemandee(nom="se_deplacer", parametres={"lieu": "table"})
        d, t = await g.verifier(aller, HUMANOIDE)
        assert d.verdict == "humain" and d.raisons[0].code == "personnes_inconnues" and t is None
        g.perception.annoncer_personnes([PersonneVue(id="a", x=9.0, y=5.0, source="yeux")], zone=PARTOUT)
        d, t = await g.verifier(aller, HUMANOIDE)
        assert d.verdict == "oui" and t is not None
        await asyncio.sleep(0.15)  # les yeux ne donnent plus de nouvelles
        d, _ = await g.verifier(aller, HUMANOIDE)
        assert d.verdict == "humain"
        d, _ = await g.verifier(ActionDemandee(nom="regarder", parametres={"cible": "table"}), HUMANOIDE)
        assert d.verdict == "oui"  # regarder ne bouge rien

    lancer(go())


def test_position_inconnue_ou_liaison_perdue():
    async def go():
        g = _gardien_avec(None)
        d, _ = await g.verifier(ActionDemandee(nom="se_deplacer", parametres={"dx": 1.0}), HUMANOIDE)
        assert d.verdict == "humain" and d.raisons[0].code == "position_inconnue"
        g = _gardien_avec({"x": 1.0, "y": 1.0, "cap": 0}, liaison=False)
        d, _ = await g.verifier(ActionDemandee(nom="se_deplacer", parametres={"dx": 1.0}), HUMANOIDE)
        assert d.verdict == "non" and d.raisons[0].code == "liaison_perdue"
        sans = Gardien(Bus())  # sans perception (banc d'essai) : c'est dit, pas caché
        d, _ = await sans.verifier(ActionDemandee(nom="se_deplacer", parametres={"dx": 1.0}), HUMANOIDE)
        assert d.verdict == "oui" and d.non_verifie

    lancer(go())


def test_le_monde_simule_a_des_personnes_et_le_systeme_les_donne_au_gardien(systeme):
    s = systeme()
    assert Monde.charger().personnes and s.gardien.perception.simulation is True
    assert lancer(s.gardien.perception.vue()).personnes[0].id == "visiteur"


# ================================================================ le chien de garde
def test_programme_principal_fige_le_robot_s_arrete_seul(systeme):
    """Le programme principal se fige : plus aucun signe de vie de la prise. Le robot (ici le faux robot, qui tourne
    à part) s'arrête seul en moins d'une seconde, grâce à son chien de garde. Simulé : testé sur faux robot."""
    @_scenario(systeme, acceleration=1.0)
    async def _(s):
        assert robot(s).delai_chien == s.reglages["securite"]["delai_chien_de_garde_s"]
        _, ticket = await s.gardien.verifier(ActionDemandee(nom="se_deplacer", parametres={"lieu": "cuisine"}), s.prise.carte())
        suivi = await s.prise.executer(ticket)
        await asyncio.sleep(0.3)
        assert robot(s)._taches[suivi.id].done() is False  # il roule
        s.prise._battement.cancel()  # « figé » : plus de signes de vie…
        for t in list(s.prise._taches.values()):
            t.cancel()  # … et plus personne ne suit l'action
        t0 = time.monotonic()
        while not robot(s)._taches[suivi.id].done() and time.monotonic() - t0 < 2.0:
            await asyncio.sleep(0.02)
        duree = time.monotonic() - t0
        assert robot(s)._taches[suivi.id].done() and duree < robot(s).delai_chien + 0.3
        assert robot(s)._suivis[suivi.id].code_erreur == "chien_de_garde"
        avant = (robot(s).x, robot(s).y)
        await asyncio.sleep(0.3)
        assert (robot(s).x, robot(s).y) == avant, "le robot ne repart pas tout seul"
