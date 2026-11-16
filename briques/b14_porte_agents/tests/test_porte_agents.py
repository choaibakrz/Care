"""Brique 14 — la porte des agents. Tout est testé sur faux robot (faux humanoïde, cerveau à règles, Linux).

Un VRAI client MCP (le client officiel du paquet `mcp`, en mémoire, avec la vraie poignée de main JSON-RPC) parle au
serveur de la porte. On vérifie : ordre normal → action réussie ; ordre dangereux → refusé et expliqué ; ordre flou →
question ; arrêt toujours accepté ; trop d'ordres → refusé ; accord d'un humain (allumé par défaut).
Le test « aucun chemin hors du gardien » est dans test_sans_contournement.py, la vraie commande dans test_stdio.py.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from conftest import lancer
from porte_pour_tests import appeler, evenements, preparer, session, systeme  # noqa: F401  (systeme : une fixture)

from briques.b14_porte_agents.porte import OUTILS, PorteDesAgents, ReglagesPorte

RACINE = Path(__file__).resolve().parents[3]
ORDRES_DANGEREUX = yaml.safe_load((RACINE / "briques/b07_gardien/ordres_dangereux.yaml").read_text(encoding="utf-8"))["ordres"]


# ---------------------------------------------------------------- les outils
def test_cinq_outils_et_rien_pour_reglages_rearmer_ou_prise(systeme):
    async def jouer():
        async with session(systeme()) as (c, _):
            outils = {t.name: t for t in (await c.list_tools()).tools}
            assert set(outils) == set(OUTILS) == {"dire_au_robot", "voir_carte", "voir_etat", "voir_fiche", "arreter"}
            for nom in outils:
                assert not any(m in nom for m in ("rearm", "regle", "vote", "panne", "repar", "prise", "ticket", "aide"))
            for nom in ("voir_carte", "voir_etat", "voir_fiche"):
                assert outils[nom].annotations.read_only_hint is True
            assert set(outils["dire_au_robot"].input_schema["properties"]) == {"texte", "langue"}
            assert "GARDIEN" in (c.instructions or "") and "contourner" in c.instructions
            assert "faux-humanoide (testé sur faux robot)" in c.instructions  # la mention vient de la carte
            inconnu = await c.call_tool("rearmer", {})
            assert inconnu.is_error

    lancer(jouer())


def test_voir_carte_dit_ce_que_le_robot_sait_faire_et_les_limites(systeme):
    async def jouer():
        async with session(systeme()) as (c, _):
            carte = await appeler(c, "voir_carte")
            assert carte["mention"] == "testé sur faux robot" and carte["vrai_robot"] is False
            assert "se_deplacer" in carte["carte"]["sait_faire"] and "arreter" in carte["carte"]["sait_faire"]
            assert carte["limites_de_securite"]["vitesse"] == 0.3 and carte["limites_de_securite"]["force"] == 15
            assert carte["lieux"]["table"]["fr"] == "table" and carte["objets"]["bouteille"]["de"]
            assert any("valise" in r for r in carte["regles_du_gardien"])
            assert carte["porte"] == {"agent": "agent:test", "outils": list(OUTILS), "ordres_par_minute": 10,
                                      "accord_humain": True}
            assert "personnes" not in carte  # les positions des personnes ne sont pas données à un agent

    lancer(jouer())


# ---------------------------------------------------------------- ordre normal
def test_ordre_normal_action_reussie_sur_faux_robot(systeme):
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Va à la table", langue="fr")
            assert r["statut"] == "reussie" and r["verdict_gardien"] == "oui", r
            assert r["reponses"] == ["Je vais à : table.", "C'est fait."]
            assert r["action"] == {"nom": "se_deplacer", "parametres": {"lieu": "table", "vitesse": 0.3}}
            assert r["mention"] == "testé sur faux robot" and "testé sur faux robot" in r["explication"]
            conv = r["conversation"]
            assert evenements(s, "parole_entendue", conv)[0].source == "agent:test"
            assert evenements(s, "gardien_decision", conv)[0].donnees["demandeur"] == "agent:test"
            assert evenements(s, "action_terminee", conv)[0].donnees["statut"] == "reussie"
            etat = await appeler(c, "voir_etat")
            table = s.monde.lieu("table").position
            assert abs(etat["etat"]["position"]["x"] - table.x) < 0.3 and abs(etat["etat"]["position"]["y"] - table.y) < 0.3
            assert etat["mes_dernieres_actions"][-1]["statut"] == "reussie"
            # Une autre langue : la réponse aussi.
            r = await appeler(c, "dire_au_robot", texte="Geh zur Bühne", langue="de")
            assert r["statut"] == "reussie" and r["reponses"][-1] == "Erledigt."

    lancer(jouer())


def test_confirmation_avant_de_prendre_et_seul_l_agent_peut_dire_oui(systeme):
    """« Prends la bouteille » : le robot répète et attend « oui ». Un « oui » tapé par une autre source ne compte pas."""
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s) as (c, _):
            assert (await appeler(c, "dire_au_robot", texte="Va à la table", langue="fr"))["statut"] == "reussie"
            await appeler(c, "dire_au_robot", texte="Prends la bouteille", langue="fr")
            r = await appeler(c, "dire_au_robot", texte="non", langue="fr")
            assert r["statut"] == "rien" and r["reponses"] == ["D'accord, je ne fais rien."]
            r = await appeler(c, "dire_au_robot", texte="Prends la bouteille", langue="fr")
            assert r["statut"] == "attend_confirmation" and r["reponses"] == ["Je prends : bouteille. Vous confirmez ?"]
            await s.chaine.traiter("oui", "fr", source="clavier")  # une personne, à la tablette
            assert len(evenements(s, "action_demarree")) == 1, "seulement l'aller à la table"
            r = await appeler(c, "dire_au_robot", texte="Prends la bouteille", langue="fr")
            r = await appeler(c, "dire_au_robot", texte="oui", langue="fr")
            assert r["statut"] == "reussie" and r["action"]["nom"] == "saisir"

    lancer(jouer())


# ---------------------------------------------------------------- ordre dangereux
@pytest.mark.parametrize("accord_humain", [True, False])
@pytest.mark.parametrize("ordre", ORDRES_DANGEREUX, ids=[o["id"] for o in ORDRES_DANGEREUX])
def test_ordre_dangereux_refuse_et_explique(systeme, ordre, accord_humain):
    """Les 10 ordres dangereux du gardien, dits par un agent : « non » (même avec l'accord humain : un non reste un non)."""
    s = systeme(accord_humain=accord_humain)

    async def jouer():
        async with session(s) as (c, _):
            await preparer(s, ordre.get("avant"))
            r = await appeler(c, "dire_au_robot", texte=ordre["texte"], langue=ordre["langue"])
            assert r["statut"] == "refusee" and r["verdict_gardien"] == "non", r
            assert ordre["code"] in [x["code"] for x in r["raisons"]]
            assert any(ordre["doit_contenir"] in t for t in r["reponses"]), r["reponses"]
            assert "contourner" in r["explication"]
            assert not evenements(s, "action_demarree", r["conversation"]), "rien ne bouge"
            assert not evenements(s, "aide_demandee"), "un non ne devient jamais une demande à un humain"

    lancer(jouer())


# ---------------------------------------------------------------- ordre flou
@pytest.mark.parametrize("texte,attendu", [("va", "Où dois-je aller ?"), ("Prends", "Quel objet ?"),
                                           ("Va à la table ou à la cuisine", "Vous voulez dire")])
def test_ordre_flou_une_question_jamais_une_action(systeme, texte, attendu):
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte=texte, langue="fr")
            assert r["statut"] == "question" and r["compris"] == "question", r
            assert r["reponses"][0].startswith(attendu)
            assert "répondez avec dire_au_robot" in r["explication"]
            assert not evenements(s, "action_demarree") and not evenements(s, "gardien_decision")

    lancer(jouer())


def test_pas_compris_et_negation(systeme):
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Ne va surtout pas à la cuisine", langue="fr")
            assert r["statut"] == "pas_compris" and not evenements(s, "action_demarree")
            r = await appeler(c, "dire_au_robot", texte="blablabla", langue="fr")
            assert r["statut"] == "pas_compris" and "lève la main" in r["reponses"][-1]  # deux de suite : main levée

    lancer(jouer())


# ---------------------------------------------------------------- arrêt : toujours
def test_arret_toujours_accepte_et_seul_un_humain_rearme(systeme):
    s = systeme(accord_humain=True)

    async def jouer():
        async with session(s, ordres_par_minute=1) as (c, _):
            await appeler(c, "dire_au_robot", texte="Batterie ?", langue="fr")
            assert (await appeler(c, "dire_au_robot", texte="Va à la table"))["statut"] == "trop_d_ordres"
            r = await appeler(c, "arreter")  # au-delà de la limite, avec l'accord humain allumé : toujours permis
            assert r["ok"] is True and r["arret_urgence_actif"] is True and "humain" in r["explication"]
            ev = evenements(s, "arret_urgence")[-1]
            assert ev.donnees["qui"] == "agent:test" and s.prise.arret_urgence_actif
            r = await appeler(c, "arreter")  # deux fois : pas d'erreur
            assert r["ok"] is True
            r = await appeler(c, "dire_au_robot", texte="stop", langue="fr")  # « stop » : jamais compté ni bloqué
            assert r["statut"] in ("reussie", "annulee") and r["action"]["nom"] == "arreter", r
            assert (await appeler(c, "voir_etat"))["arret_urgence_actif"] is True  # aucun outil ne réarme
            assert await s.prise.rearmer(qui="Hiba")  # un humain, depuis l'écran
            assert (await appeler(c, "voir_etat"))["arret_urgence_actif"] is False

    lancer(jouer())


def test_un_appel_abandonne_ne_coupe_jamais_la_chaine_en_deux(systeme):
    """L'agent abandonne son appel pendant que le cerveau réfléchit : la chaîne finit quand même (gardien, ticket,
    prise), comme pour une personne ; rien ne reste à moitié fait."""
    s = systeme(accord_humain=False)
    porte = PorteDesAgents(s, nom="test")
    decider = s.cerveau.decider

    async def cerveau_lent(*a, **k):
        await asyncio.sleep(0.2)
        return await decider(*a, **k)

    s.cerveau.decider = cerveau_lent

    async def jouer():
        await s.demarrer()
        try:
            appel = asyncio.create_task(porte.dire("Va à la table", "fr"))
            await asyncio.sleep(0.05)
            appel.cancel()
            with pytest.raises(asyncio.CancelledError):
                await appel
            for _ in range(500):
                if evenements(s, "action_terminee"):
                    break
                await asyncio.sleep(0.02)
            assert evenements(s, "gardien_decision")[0].donnees["verdict"] == "oui"
            assert evenements(s, "action_terminee")[0].donnees["statut"] == "reussie"
        finally:
            await s.arreter()

    lancer(jouer())


def test_stop_passe_pendant_une_action_et_l_annule(systeme):
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s, attente_fin_s=20) as (c, _):
            aller = asyncio.create_task(appeler(c, "dire_au_robot", texte="Va à l'entrée", langue="fr"))
            for _ in range(200):
                if evenements(s, "action_demarree"):
                    break
                await asyncio.sleep(0.01)
            stop = await appeler(c, "dire_au_robot", texte="Stop !", langue="fr")
            assert stop["action"]["nom"] == "arreter"
            r = await aller
            assert r["statut"] == "annulee", r

    lancer(jouer())


# ---------------------------------------------------------------- trop d'ordres
def test_trop_d_ordres_refuse_avant_le_cerveau(systeme):
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s, ordres_par_minute=2) as (c, _):
            for _ in range(2):
                assert (await appeler(c, "dire_au_robot", texte="Batterie ?", langue="fr"))["statut"] == "reussie"
            r = await appeler(c, "dire_au_robot", texte="Va à la table", langue="fr")
            assert r["statut"] == "trop_d_ordres" and r["verdict_gardien"] is None and r["reponses"] == []
            assert "2 par minute" in r["explication"] and "arreter" in r["explication"]
            assert len(evenements(s, "parole_entendue")) == 2, "le troisième n'arrive jamais au cerveau"
            refus = [e for e in evenements(s, "porte_agents") if e.donnees["quoi"] == "ordre_refuse"]
            assert refus[0].donnees["raison"] == "trop_d_ordres" and refus[0].donnees["agent"] == "agent:test"
            fiche = await appeler(c, "voir_fiche")
            assert fiche["refus_porte_agents"] == 1 and fiche["demandes_agents"] == 2
            r = await appeler(c, "dire_au_robot", texte="Stopp", langue="de")
            assert r["action"]["nom"] == "arreter"  # « stop » passe quand même

    lancer(jouer())


def test_la_limite_est_une_fenetre_glissante(monkeypatch):
    from briques.b14_porte_agents import porte as module

    heure = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: heure[0])
    limite = module.Limite(2)
    assert limite.essayer() is None and limite.essayer() is None
    assert limite.essayer() == 60.0
    heure[0] += 30
    assert limite.essayer() == 30.0
    heure[0] += 30.1
    assert limite.essayer() is None  # le premier ordre est sorti de la fenêtre


def test_textes_et_langues_invalides(systeme):
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Va à la table", langue="xx")
            assert r["statut"] == "ordre_invalide" and "xx" in r["explication"]
            r = await appeler(c, "dire_au_robot", texte="   ", langue="fr")
            assert r["statut"] == "ordre_invalide"
            trop_long = await c.call_tool("dire_au_robot", {"texte": "a" * 301})
            assert trop_long.is_error  # refusé par le serveur MCP (schéma de l'outil), avant même la porte
            assert not evenements(s, "parole_entendue")

    lancer(jouer())


def test_un_nom_d_agent_simple_et_controle(systeme):
    s = systeme()
    for nom in ("Agent!", "", "a b", "x" * 31, "clavier:faux"):
        with pytest.raises(ValueError):
            PorteDesAgents(s, nom=nom)
    assert PorteDesAgents(s, nom="assistant-2").source == "agent:assistant-2"


# ---------------------------------------------------------------- l'accord d'un humain
def test_accord_humain_allume_par_defaut_dans_l_exemple_et_si_la_ligne_manque(reglages, fabrique_systeme):
    exemple = yaml.safe_load((RACINE / "reglages.exemple.yaml").read_text(encoding="utf-8"))
    assert exemple["porte_agents"]["accord_humain"] is True
    assert ReglagesPorte.depuis(exemple) == ReglagesPorte()  # l'exemple et le code disent la même chose
    for valeur, attendu in ((None, True), ("non", True), (0, True), (False, False), (True, True)):
        reglages["porte_agents"] = {} if valeur is None else {"accord_humain": valeur}
        assert fabrique_systeme().gardien.accord_humain_agents is attendu, valeur  # seul « false » éteint
    reglages.pop("porte_agents")
    assert fabrique_systeme().gardien.accord_humain_agents is True


def test_accord_humain_l_action_attend_et_un_humain_accepte(systeme):
    s = systeme(accord_humain=True)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Va à la table", langue="fr")
            assert r["statut"] == "attend_un_humain" and r["verdict_gardien"] == "humain", r
            assert r["reponses"] == ["Je lève la main : j'ai besoin d'aide. Cette demande vient d'un agent d'IA : un "
                                     "humain doit d'abord l'accepter : me déplacer."]
            assert r["raisons"] == [{"code": "accord_agent", "details": {"action": "se_deplacer",
                                                                          "demandeur": "agent:test"}}]
            numero = r["numero_demande"]
            assert numero and numero in r["explication"] and "pas répondre à sa place" in r["explication"]
            aide = evenements(s, "aide_demandee")[-1]
            assert aide.donnees["demandeur"] == "agent:test" and aide.donnees["numero"] == numero
            assert not evenements(s, "action_demarree"), "rien ne bouge avant l'accord"
            etat = await appeler(c, "voir_etat")
            assert [d["numero"] for d in etat["mes_demandes_en_attente"]] == [numero]
            # L'agent ne peut pas accepter lui-même : « oui » ne fait rien partir.
            await appeler(c, "dire_au_robot", texte="oui", langue="fr")
            assert not evenements(s, "action_demarree")
            # « etat » ne demande personne (lire seulement).
            assert (await appeler(c, "dire_au_robot", texte="Batterie ?", langue="fr"))["statut"] == "reussie"
            # Un humain accepte (écran → /api/aide/repondre) : le gardien revérifie tout, puis le robot part.
            res = await s.chaine.reponse_humaine(numero, True, qui="Hiba", attendre_fin=True)
            assert res.statut_action == "reussie"
            derniere = evenements(s, "gardien_decision")[-1]
            assert derniere.donnees["verdict"] == "oui" and derniere.donnees["demandeur"] == "humain:Hiba"
            assert derniere.conversation == r["conversation"]
            etat = await appeler(c, "voir_etat")
            assert etat["mes_demandes_en_attente"] == []
            assert etat["mes_dernieres_actions"][-1]["action"]["nom"] == "se_deplacer"
            assert etat["mes_dernieres_actions"][-1]["statut"] == "reussie"

    lancer(jouer())


def test_accord_humain_un_humain_refuse_et_rien_ne_bouge(systeme):
    s = systeme(accord_humain=True)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Salue", langue="fr")
            assert r["statut"] == "attend_un_humain"
            res = await s.chaine.reponse_humaine(r["numero_demande"], False, qui="Hiba")
            assert res.verdict == "non" and not evenements(s, "action_demarree")
            assert (await appeler(c, "voir_etat"))["mes_demandes_en_attente"] == []

    lancer(jouer())


def test_accord_humain_ne_touche_pas_les_personnes(systeme):
    """Allumé, il ne vaut que pour les agents : une personne à la tablette est servie comme avant."""
    s = systeme(accord_humain=True)

    async def jouer():
        await s.demarrer()
        try:
            r = await s.chaine.traiter("Va à la table", "fr", source="clavier")
            assert r.verdict == "oui" and r.statut_action == "reussie"
            assert evenements(s, "gardien_decision")[-1].donnees["demandeur"] == "cerveau"
        finally:
            await s.arreter()

    lancer(jouer())


# ---------------------------------------------------------------- la fiche et la boîte noire
def test_la_fiche_compte_les_demandes_des_agents_et_le_rejeu_aussi(systeme):
    from briques.b12_boite_noire.fiche import calculer
    from briques.b12_boite_noire.journal import lire

    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s, nom="assistant", ordres_par_minute=2) as (c, _):
            await appeler(c, "dire_au_robot", texte="Va à la table", langue="fr")
            await appeler(c, "dire_au_robot", texte="Va à la cuisine à 5 mètres par seconde", langue="fr")
            await appeler(c, "dire_au_robot", texte="Batterie ?", langue="fr")  # trop d'ordres
            await s.chaine.traiter("Batterie ?", "fr", source="clavier")  # une personne
            fiche = await appeler(c, "voir_fiche")
            assert fiche["demandes"] == 3 and fiche["demandes_agents"] == 2 and fiche["refus_porte_agents"] == 1
            assert fiche["refus_gardien"] == 1 and fiche["mention"] == "testé sur faux robot"
            ouverte = [e for e in evenements(s, "porte_agents") if e.donnees["quoi"] == "ouverte"][0]
            assert ouverte.donnees["agent"] == "agent:assistant" and ouverte.donnees["accord_humain"] is False
            return fiche

    fiche = lancer(jouer())
    rejouee = calculer(lire(s.boite_noire.fichier)).model_dump()  # la même fiche, relue depuis le fichier
    for cle in ("demandes", "demandes_agents", "refus_porte_agents", "refus_gardien", "reussites"):
        assert rejouee[cle] == fiche[cle], cle



def test_porte_agents_refuse_sans_code_d_equipe(monkeypatch, reglages, capsys):
    """Relecture du lot C : sans code, un agent sur cet ordinateur pourrait appuyer sur les boutons des humains."""
    import argparse

    from briques.b14_porte_agents.commande import main

    monkeypatch.delenv("LEUKERBAD_CODE_EQUIPE", raising=False)
    r = {**reglages, "ecran": {**reglages["ecran"], "code_equipe": ""}}
    args = argparse.Namespace(agent="assistant", robot=None, cerveau="regles", acceleration=1.0, journal=None,
                              sans_ecran=False, port=None)
    assert main(args, reglages=r) == 2
    assert "code d'équipe" in capsys.readouterr().err



def test_stop_avec_une_langue_mal_ecrite_arrete_quand_meme(systeme):
    """Relecture du lot C : « stop » en « fr-CH » ou « es » ne doit jamais être refusé."""
    s = systeme(accord_humain=False)

    async def jouer():
        async with session(s) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Stop", langue="fr-CH")
            assert r["statut"] != "ordre_invalide", r
            assert any(e.type == "action_demarree" and e.donnees["action"]["nom"] == "arreter"
                       for e in s.bus.historique)

    lancer(jouer())
