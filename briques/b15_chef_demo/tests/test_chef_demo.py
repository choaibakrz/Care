"""Brique 15 — le chef de démonstration. Testé sur faux robot, cerveau à règles, Internet coupé (conftest.py).

Le faux robot et les pauses du scénario sont accélérés : le scénario de trois minutes se joue en quelques secondes.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import time

import pytest

from briques.b06_cerveau.branchements.cascade import CerveauCascade, Etage
from briques.b06_cerveau.branchements.regles import CerveauRegles
from briques.b06_cerveau.prise_cerveau import Cerveau
from briques.b15_chef_demo.chef import ChefDemo, tirer_pagaille
from briques.b15_chef_demo.commande import main as commande
from briques.b15_chef_demo.compte_rendu import ecrire
from briques.b15_chef_demo.scenario import DOSSIER_SCENARIOS, ScenarioInvalide, charger, lire, lire_pannes
from briques.b15_chef_demo.verifier import avertissements
from commun.evenements import Evenement
from conftest import lancer

ESSAI = DOSSIER_SCENARIOS / "essai_3_minutes.yaml"
ACC = 60.0  # faux robot et pauses 60 fois plus vite


def _jouer(s, scenario, **options):
    async def go():
        await s.demarrer()
        try:
            return await ChefDemo(s, scenario, acceleration=options.pop("acceleration", ACC), **options).jouer()
        finally:
            await s.arreter()

    return lancer(go())


def _evs(s, type_):
    return [e for e in s.bus.historique if e.type == type_]


def _petit(*etapes, **en_plus):
    return lire({"titre": "petit essai", "plan_b": ["tablette", "mode_local", "main_humaine", "sauter"],
                 **en_plus, "etapes": list(etapes)})


class _CerveauEnLigne(Cerveau):
    """Factice : un cerveau « par Internet » (adresse hors de cet ordinateur) qui répond comme le cerveau à règles."""

    nom = "en_ligne"
    url = "https://cerveau.exemple.invalid"

    def __init__(self) -> None:
        self._regles = CerveauRegles()
        self.appels = 0

    async def decider(self, texte, langue, carte, monde):
        self.appels += 1
        d = await self._regles.decider(texte, langue, carte, monde)
        d.cerveau = self.nom
        return d


def _avec_cerveau_en_ligne(s, delai_s: float):
    en_ligne = _CerveauEnLigne()
    cascade = CerveauCascade([Etage(en_ligne, delai_s=delai_s), Etage(CerveauRegles())], s.bus)
    s.cerveau = s.chaine.cerveau = cascade
    return en_ligne, cascade


# ---------------------------------------------------------------- le format
@pytest.mark.parametrize("chemin", sorted(DOSSIER_SCENARIOS.glob("*.yaml")), ids=lambda p: p.name)
def test_les_scenarios_du_dossier_suivent_le_format_et_les_noms_existent(chemin):
    sc = charger(chemin)
    assert sc.etapes and avertissements(sc) == []


@pytest.mark.parametrize("etape,morceau", [
    ({"nom": "x", "dire": "Salue", "annonce": "Bonjour"}, "une seule chose"),
    ({"nom": "x"}, "une seule chose"),
    ({"nom": "x", "dire": "Salue", "plan_b": ["priere"]}, "plan B inconnu"),
    ({"nom": "x", "annonce": "Bonjour", "attendu": "question"}, "« attendu » ne va qu'avec « dire »"),
    ({"nom": "x", "dire": "Salue", "atendu": "question"}, "atendu"),  # faute de frappe : clé inconnue
    ({"nom": "x", "dire": {"texte": "Salue", "langue": "xx"}}, "langue inconnue"),
    ({"nom": "x", "dire": "Salue", "attendu": {"action": "voler"}}, "action inconnue"),
    ({"nom": "x", "dire": "Salue", "attendu": "danse"}, "attendu"),
    ({"nom": "x", "provoquer_panne": "meteorite"}, "panne inconnue"),
    ({"nom": "x", "dire": "Va", "attendre_fin": False, "attendu": {"action": "se_deplacer"}}, "statut: demarree"),
])
def test_le_format_refuse_les_fautes_avant_de_jouer(etape, morceau):
    with pytest.raises(ScenarioInvalide) as e:
        lire({"titre": "t", "etapes": [etape]})
    assert morceau in str(e.value)


def test_deux_etapes_du_meme_nom_et_un_nom_inconnu_du_monde():
    with pytest.raises(ScenarioInvalide, match="unique"):
        lire({"titre": "t", "etapes": [{"nom": "a", "dire": "Salue"}, {"nom": "a", "dire": "Wave"}]})
    sc = lire({"titre": "t", "robot": "humanoide", "etapes": [
        {"nom": "a", "dire": "Va à la table", "attendu": {"action": "se_deplacer", "parametres": {"lieu": "tabel"}}},
        {"nom": "b", "dire": "Danse", "attendu": {"action": "rejouer_geste", "parametres": {"nom": "danser"}}}]})
    notes = avertissements(sc)
    assert len(notes) == 2 and "tabel" in notes[0] and "danser" in notes[1]


def test_lire_les_pannes_de_la_ligne_de_commande():
    sc = charger(ESSAI)
    assert lire_pannes(["robot@7", "voix@salut_gsw", "reseau@4"], sc) == {7: "robot", 3: "voix", 4: "reseau"}
    for faux in ["robot", "robot@99", "meteorite@3", "voix@inconnue", "@3"]:
        with pytest.raises(ScenarioInvalide):
            lire_pannes([faux], sc)


# ---------------------------------------------------------------- « fini quand » : le scénario se joue seul
def test_le_scenario_de_trois_minutes_se_joue_seul_jusqu_au_bout(fabrique_systeme):
    s = fabrique_systeme("humanoide", ACC)
    sc = charger(ESSAI)
    t0 = time.monotonic()
    res = _jouer(s, sc)
    assert time.monotonic() - t0 < 60  # quelques secondes grâce à l'accélération
    assert [e.resultat for e in res.etapes] == ["reussie"] * len(sc.etapes) and res.interrompu is None
    f = res.fiche
    assert f.mention == "testé sur faux robot" and f.plans_b == 0 and f.arrets_urgence == 0
    assert f.refus_gardien == 1 and f.questions_posees == 1 and f.confirmations_demandees == 1
    assert {"fr", "gsw", "en", "zh"} <= {e.donnees["langue"] for e in _evs(s, "parole_entendue")}
    finies = [(e.donnees["action"]["nom"], e.donnees["statut"]) for e in _evs(s, "action_terminee")]
    assert ("saisir", "reussie") in finies and ("se_deplacer", "annulee") in finies  # pris la bouteille, arrêté en route
    dites = [e.donnees["texte"] for e in _evs(s, "reponse_dite") if e.source == "chef_demo"]
    assert any(t.startswith("Fiche de vérité") and "Testé sur faux robot" in t for t in dites)
    # Chaque action du robot a reçu le « oui » du gardien dans la même conversation : rien n'a contourné la chaîne.
    oui = {e.conversation for e in _evs(s, "gardien_decision") if e.donnees["verdict"] == "oui"}
    assert all(e.conversation in oui for e in _evs(s, "action_demarree"))
    fin = _evs(s, "scenario_fin")[-1].donnees
    assert fin["reussies"] == len(sc.etapes) and fin["interrompu"] is False
    assert [e.donnees["quoi"] for e in _evs(s, "scenario_etape")] == ["debut", "fin"] * len(sc.etapes)


# ---------------------------------------------------------------- les plans B
def test_panne_du_robot_la_main_humaine_prend_le_relais(fabrique_systeme):
    s = fabrique_systeme("humanoide", ACC)
    sc = charger(ESSAI)
    n = sc.numero("salut_fr")
    res = _jouer(s, sc, repetition=True, pannes={n: "robot"})
    e = res.etapes[n - 1]
    assert e.resultat == "rattrapee" and e.cause == "robot" and "robot_refuse" in e.detail
    # Rejouer la phrase ne répare pas un robot en panne : tablette et mode local sont passés, notés « inutile ».
    assert [(p.moyen, p.resultat) for p in e.plans_b] == [("tablette", "inutile"), ("mode_local", "inutile"),
                                                          ("main_humaine", "reussi")]
    assert [x.donnees["quoi"] for x in _evs(s, "pilotage_humain")] == ["reprise", "rendu"]
    assert [(x.donnees["etat"], x.donnees["moyen"]) for x in _evs(s, "plan_b")] == [("essai", "main_humaine"),
                                                                                      ("reussi", "main_humaine")]
    assert [x.donnees["quoi"] for x in _evs(s, "panne") if x.source == "chef_demo"] == ["robot"]
    assert any(x.donnees.get("quoi") == "robot" for x in _evs(s, "reparation"))
    assert all(x.resultat == "reussie" for x in res.etapes if x.numero != n)  # la panne ne dure que cette étape
    f = res.fiche
    assert f.plans_b == f.plans_b_reussis == 1 and f.pannes_provoquees == 1
    # Brique 11 : la main humaine de l'opérateur automatique est SIMULÉE : comptée à part, jamais comme un vrai humain.
    assert f.part_humain_simulee_pct > 0 and f.part_humain_pct == 0
    assert all(x.donnees["simulee"] is True for x in _evs(s, "pilotage_humain"))


@pytest.mark.parametrize("nom_etape", ["aller_table", "confirmer_oui"])
def test_panne_de_voix_on_passe_a_la_tablette(fabrique_systeme, nom_etape):
    s = fabrique_systeme("humanoide", ACC)
    sc = charger(ESSAI)
    n = sc.numero(nom_etape)
    res = _jouer(s, sc, repetition=True, pannes={n: "voix"})
    e = res.etapes[n - 1]
    assert e.resultat == "rattrapee" and e.cause == "voix"
    assert [(p.moyen, p.resultat) for p in e.plans_b] == [("tablette", "reussi")]
    assert all(x.resultat == "reussie" for x in res.etapes if x.numero != n)
    paroles = _evs(s, "parole_entendue")
    assert any(p.donnees["texte"] == "…" and p.source == "micro" for p in paroles)  # la phrase brouillée
    assert paroles[-1].source == "clavier"  # la tablette reste jusqu'à la fin
    finies = [(x.donnees["action"]["nom"], x.donnees["statut"]) for x in _evs(s, "action_terminee")]
    assert ("saisir", "reussie") in finies  # même quand la voix tombe sur le « oui » : l'ordre est redemandé


def test_panne_reseau_le_cerveau_passe_en_mode_local(fabrique_systeme):
    """Le cerveau en ligne ne répond plus : la cascade attend, passe aux règles ; le chef passe en mode local
    pour que la suite ne paie plus l'attente."""
    s = fabrique_systeme("humanoide", ACC)
    en_ligne, cascade = _avec_cerveau_en_ligne(s, delai_s=0.3)
    sc = charger(ESSAI)
    n = sc.numero("aller_table")
    res = _jouer(s, sc, repetition=True, pannes={n: "reseau"})
    e = res.etapes[n - 1]
    assert all(x.resultat == "reussie" for x in res.etapes)
    assert [(p.moyen, p.resultat, p.preventif) for p in e.plans_b] == [("mode_local", "reussi", True)]
    assert [x.donnees["de"] for x in _evs(s, "cerveau_secours")] == ["en_ligne"]  # une seule attente, puis plus jamais
    assert en_ligne.appels == 4  # les quatre saluts avant la panne ; ensuite, mode local jusqu'à la fin
    assert cascade.etages[0].cerveau is en_ligne and cascade.etages[0].en_pause_jusqua != math.inf  # rendu comme avant
    assert res.fiche.plans_b_reussis == 0  # préventif : il n'a rien rattrapé, la fiche ne le compte pas


def test_panne_reseau_etape_trop_longue_plan_b_mode_local_puis_on_rejoue(fabrique_systeme):
    """Le cerveau en ligne met plus longtemps que la limite de l'étape : raté, mode local, la phrase est rejouée."""
    s = fabrique_systeme("humanoide", ACC)
    en_ligne, _ = _avec_cerveau_en_ligne(s, delai_s=30)
    sc = _petit({"nom": "saluer", "dire": "Salue", "attendu": {"action": "rejouer_geste"}, "duree_max_s": 1})
    res = _jouer(s, sc, repetition=True, pannes={1: "reseau"})
    e = res.etapes[0]
    assert e.resultat == "rattrapee" and e.cause == "reseau" and "pas fini" in e.detail
    assert [(p.moyen, p.resultat) for p in e.plans_b] == [("tablette", "inutile"), ("mode_local", "reussi")]
    assert en_ligne.appels == 0
    assert [x.donnees["statut"] for x in _evs(s, "action_terminee")] == ["reussie"]  # le robot n'a salué qu'une fois


def test_sauter_et_main_humaine_qui_ne_peut_pas(fabrique_systeme):
    class Absent:
        nom = "absent"

        async def prendre_la_main(self, consigne):
            return False

    s = fabrique_systeme("humanoide", ACC)
    sc = _petit({"nom": "saluer", "dire": "Salue", "attendu": {"action": "rejouer_geste"},
                 "plan_b": ["main_humaine", "sauter"]}, {"nom": "suite", "dire": "Applaudis",
                                                         "attendu": {"action": "rejouer_geste"}})
    res = _jouer(s, sc, repetition=True, pannes={1: "robot"}, operateur=Absent())
    assert [e.resultat for e in res.etapes] == ["sautee", "reussie"]
    assert [(p.moyen, p.resultat) for p in res.etapes[0].plans_b] == [("main_humaine", "rate"), ("sauter", "saute")]
    assert any(e.donnees["texte"] == "On passe à la suite." for e in _evs(s, "reponse_dite"))
    assert [x.donnees.get("fait") for x in _evs(s, "pilotage_humain")] == [None, False]


# ---------------------------------------------------------------- répétition : compte rendu, pagaille
def test_le_compte_rendu_contient_le_chronometre_et_les_rates(fabrique_systeme, tmp_path):
    s = fabrique_systeme("humanoide", ACC)
    sc = _petit({"nom": "saluer", "dire": "Salue", "attendu": {"action": "rejouer_geste"}},
                {"nom": "applaudir", "dire": "Applaudis", "attendu": {"action": "rejouer_geste"}, "plan_b": ["tablette"]},
                {"nom": "fin", "annonce": "Merci !"}, duree_visee_s=30)
    res = _jouer(s, sc, repetition=True, pannes={2: "robot"})
    assert [e.resultat for e in res.etapes] == ["reussie", "ratee", "reussie"]  # on continue après un raté
    chemin = ecrire(res, tmp_path)
    texte = chemin.read_text(encoding="utf-8")
    for morceau in ["## Chronomètre", "| 1 | saluer |", "| 2 | applaudir |", "✘ ratée", "## Ce qui a raté",
                    "panne du robot", "robot_refuse", "plan B tablette : inutile", "Durée totale mesurée",
                    "visée : 30 s", "testé sur faux robot", "Accéléré ×60", "Pannes provoquées : robot@2",
                    "## Fiche de vérité de cette répétition"]:
        assert morceau in texte, morceau
    assert chemin.parent == tmp_path and chemin.name.startswith("repetition_petit_essai_")


def test_le_compte_rendu_note_les_etapes_reussies_apres_leur_limite():
    from briques.b15_chef_demo.chef import ResultatEtape, ResultatScenario
    from briques.b15_chef_demo.compte_rendu import texte

    res = ResultatScenario(titre="t", fichier="", repetition=True, acceleration=1.0, mention="testé sur faux robot",
                           robot="faux-humanoide", cerveau="regles", debut="11.11.2026", pannes={}, graine=None,
                           duree_visee_s=None, nb_etapes=1, operateur="automatique (simulé)",
                           etapes=[ResultatEtape(numero=1, nom="aller_table", genre="dire", duree_s=21.5, limite_s=20.0)])
    t = texte(res)
    assert "fini, mais après la limite" in t and "1 « aller_table » (21,50 s > 20,00 s)" in t
    assert "Accéléré" not in t  # à ×1 : pas d'avertissement


def test_mode_pagaille_meme_graine_memes_pannes_et_on_va_jusqu_au_bout(fabrique_systeme):
    sc = charger(ESSAI)
    pannes = tirer_pagaille(sc, graine=7)
    assert pannes == tirer_pagaille(sc, graine=7) and pannes
    assert all(sc.etapes[n - 1].dire is not None for n in pannes) and set(pannes.values()) <= {"robot", "voix", "reseau"}
    s = fabrique_systeme("humanoide", ACC)
    res = _jouer(s, sc, repetition=True, pannes=pannes, graine=7)
    assert res.interrompu is None and len(res.etapes) == len(sc.etapes)
    assert res.fiche.pannes_provoquees == len(pannes)
    utilises = sum(1 for e in res.etapes for p in e.plans_b if p.resultat in ("reussi", "rate", "saute"))
    assert res.fiche.plans_b == utilises


def test_hors_repetition_aucune_panne_n_est_provoquee(fabrique_systeme):
    s = fabrique_systeme("humanoide", ACC)
    sc = _petit({"nom": "panne", "provoquer_panne": "robot"}, {"nom": "saluer", "dire": "Salue",
                                                                "attendu": {"action": "rejouer_geste"}},
                {"nom": "reparer", "reparer": True})
    res = _jouer(s, sc)
    assert [e.resultat for e in res.etapes] == ["ignoree", "reussie", "ignoree"]
    assert not _evs(s, "panne")
    with pytest.raises(ValueError):
        ChefDemo(s, sc, pannes={2: "robot"})  # pannes de la ligne de commande : répétition seulement


# ---------------------------------------------------------------- l'arrêt d'urgence passe avant tout
def test_l_arret_d_urgence_interrompt_le_scenario_et_le_chef_ne_rearme_pas(fabrique_systeme):
    s = fabrique_systeme("humanoide", 2.0)  # lent : le robot est encore en route quand on appuie
    sc = _petit({"nom": "cuisine", "dire": "Va à la cuisine", "attendu": {"action": "se_deplacer"}, "duree_max_s": 60},
                {"nom": "saluer", "dire": "Salue"}, {"nom": "fin", "annonce": "Merci !"})

    async def go():
        await s.demarrer()
        try:
            tache = asyncio.create_task(ChefDemo(s, sc, acceleration=2.0).jouer())
            while not _evs(s, "action_demarree"):
                await asyncio.sleep(0.02)
            await s.prise.arret_urgence(raison="bouton_test")
            res = await asyncio.wait_for(tache, 10)
            return res, s.prise.arret_urgence_actif
        finally:
            await s.arreter()

    res, toujours_actif = lancer(go())
    assert res.interrompu and "arrêt d'urgence" in res.interrompu and "bouton_test" in res.interrompu
    assert [e.resultat for e in res.etapes] == ["interrompue"]
    assert toujours_actif  # seul un humain réarme
    assert not any(e.donnees["texte"] == "Salue" for e in _evs(s, "parole_entendue"))
    assert any("Arrêt d'urgence" in e.donnees["texte"] for e in _evs(s, "reponse_dite") if e.source == "chef_demo")
    assert _evs(s, "scenario_fin")[-1].donnees["interrompu"] is True
    assert not any(e.donnees.get("quoi") == "rearmement" for e in _evs(s, "reparation"))


def test_arret_d_urgence_deja_actif_le_chef_ne_commence_pas(fabrique_systeme):
    s = fabrique_systeme("humanoide", ACC)

    async def go():
        await s.demarrer()
        try:
            await s.prise.arret_urgence()
            return await ChefDemo(s, charger(ESSAI), acceleration=ACC).jouer()
        finally:
            await s.arreter()

    res = lancer(go())
    assert res.etapes == [] and "déjà actif" in res.interrompu
    assert not _evs(s, "parole_entendue")


# ---------------------------------------------------------------- la commande
def test_la_commande_repetition_ecrit_le_compte_rendu(reglages, tmp_path, capsys):
    chemin = tmp_path / "court.yaml"
    chemin.write_text("titre: Court\nrobot: humanoide\nplan_b: [main_humaine]\netapes:\n"
                      "  - {nom: saluer, dire: Salue, attendu: {action: rejouer_geste}}\n"
                      "  - {nom: fiche, fiche: de}\n", encoding="utf-8")
    r = {**reglages, "cerveau": {**reglages["cerveau"], "choix": "regles"}}

    def args(**kw):
        base = dict(chemin=str(chemin), repetition=True, panne=["robot@1"], pagaille=False, graine=1,
                    acceleration=ACC, rapport=str(tmp_path / "cr"), operateur=None, robot=None)
        return argparse.Namespace(**{**base, **kw})

    assert commande(args(), reglages=r, dossier_journal=tmp_path / "journal") == 0
    sortie = capsys.readouterr().out
    assert "rattrapee" in sortie and "Compte rendu" in sortie and "Wahrheitsblatt" in sortie
    assert len(list((tmp_path / "cr").glob("repetition_court_*.md"))) == 1
    assert commande(args(repetition=False), reglages=r, dossier_journal=tmp_path / "journal") == 2  # pannes : répétition
    assert commande(args(panne=["robot@9"]), reglages=r, dossier_journal=tmp_path / "journal") == 2


def test_attendu_aide_le_robot_demande_un_humain_et_ne_bouge_pas(fabrique_systeme):
    """Faux bras : « verser » demande l'accord d'un humain (règle du gardien) ; l'étape « aide » réussit, rien ne part."""
    s = fabrique_systeme("bras", ACC)
    sc = _petit({"nom": "verser", "dire": {"texte": "Verse", "langue": "fr"}, "attendu": "aide"})
    res = _jouer(s, sc)
    assert [e.resultat for e in res.etapes] == ["reussie"]
    assert not _evs(s, "action_demarree")
    assert any(e.donnees["verdict"] == "humain" for e in _evs(s, "gardien_decision"))


def test_attendu_aide_seulement_pour_le_verdict_humain_du_gardien(fabrique_systeme):
    """Relecture du lot B : « pas compris » deux fois, le robot lève aussi la main (brique 8), mais ce n'est PAS
    l'attendu « aide » (le gardien qui demande l'accord d'un humain). L'étape n'est pas réussie. Faux robot."""
    from briques.b15_chef_demo.scenario import Attendu

    s = fabrique_systeme("humanoide", ACC)
    s.doute.actif = True  # la main levée « il bute » allumée, quel que soit reglages.yaml
    sc = _petit({"nom": "un", "dire": {"texte": "blabla", "langue": "fr"}, "attendu": "rien"},
                {"nom": "deux", "dire": {"texte": "blublu", "langue": "fr"}, "attendu": "aide"})
    res = _jouer(s, sc)
    assert [a.donnees["raison"] for a in _evs(s, "aide_demandee")][:1] == ["incompris_de_suite"]
    assert res.etapes[0].resultat == "reussie" and res.etapes[1].resultat != "reussie"
    assert not any(e.donnees["verdict"] == "humain" for e in _evs(s, "gardien_decision"))
    # Directement : une aide_demandee sans verdict « humain » ne suffit pas ; avec, oui ; et si une action part, non.
    aide = Evenement(type="aide_demandee", source="doute", donnees={"raison": "echecs_de_suite"})
    humain = Evenement(type="gardien_decision", source="gardien", donnees={"verdict": "humain"})
    partie = Evenement(type="action_demarree", source="prise", donnees={"action": {"nom": "saisir"}})
    attendu = Attendu(genre="aide")
    assert not ChefDemo._verifie(attendu, [aide])
    assert ChefDemo._verifie(attendu, [humain, aide])
    assert not ChefDemo._verifie(attendu, [humain, partie])


def test_un_stop_dit_par_une_personne_arrete_tout_le_scenario(fabrique_systeme):
    """Relecture du lot A : « stop » au micro pendant un trajet ; les étapes suivantes ne doivent PAS faire repartir
    le robot. Testé sur faux robot."""
    s = fabrique_systeme("humanoide", 4)
    sc = _petit({"nom": "cuisine", "dire": "Va à la cuisine", "attendu": {"action": "se_deplacer"}, "duree_max_s": 60},
                {"nom": "entree", "dire": "Va à l'entrée", "attendu": {"action": "se_deplacer"}},
                {"nom": "table", "dire": "Va à la table", "attendu": {"action": "se_deplacer"}})

    async def go():
        await s.demarrer()
        try:
            chef = asyncio.create_task(ChefDemo(s, sc, acceleration=4).jouer())
            for _ in range(200):
                if _evs(s, "action_demarree"):
                    break
                await asyncio.sleep(0.02)
            await s.chaine.traiter("Stop", "fr", source="micro")
            return await asyncio.wait_for(chef, 30)
        finally:
            await s.arreter()

    res = lancer(go())
    assert res.interrompu and "stop" in res.interrompu
    assert [e.resultat for e in res.etapes] == ["interrompue"]
    parties = [e.donnees["action"]["nom"] for e in _evs(s, "action_demarree")]
    assert parties.count("se_deplacer") == 1, parties  # rien n'est reparti après le stop


def test_apres_un_refus_du_gardien_jamais_la_main_humaine(fabrique_systeme):
    """Relecture du lot A : on ne demande pas à un humain de faire ce que le gardien refuse. Seul « sauter » reste."""
    s = fabrique_systeme("humanoide", ACC)
    sc = _petit({"nom": "trop_vite", "dire": "Va à la cuisine à 5 mètres par seconde",
                 "attendu": {"action": "se_deplacer"}, "plan_b": ["tablette", "main_humaine", "sauter"]})
    res = _jouer(s, sc, repetition=True)
    e = res.etapes[0]
    assert e.cause == "gardien" and e.resultat == "sautee"
    essayes = [p.moyen for p in e.plans_b if p.resultat != "inutile"]
    assert "main_humaine" not in essayes and "tablette" not in essayes
    assert not [x for x in _evs(s, "pilotage_humain")]


def test_un_robot_inconnu_dans_le_scenario_est_refuse_a_la_lecture():
    with pytest.raises(ScenarioInvalide):
        _petit({"nom": "a", "dire": "Salue"}, robot="humanoïde")
