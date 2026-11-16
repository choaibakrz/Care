"""Brique 14 — aucun chemin hors du gardien. Testé sur faux robot.

Deux preuves, en plus de tests_bout_en_bout/test_aucun_contournement.py (qui lit aussi le code de cette brique) :
1. en lisant le code de la porte (sans l'exécuter) : sur la prise, seulement lire et l'arrêt d'urgence ; rien du
   gardien qui fabrique un ticket ou change une règle ; chaque phrase va à `chaine.traiter` avec la source de l'agent ;
2. en faisant tourner une vraie session MCP (ordres normaux, dangereux, flous, stop, accord d'un humain) : chaque action
   partie vers le robot a d'abord reçu le « oui » du gardien, dans la même conversation ; la prise n'est appelée
   que par la chaîne.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from conftest import lancer
from porte_pour_tests import appeler, evenements, session, systeme  # noqa: F401  (systeme : une fixture)

ICI = Path(__file__).resolve().parents[1]
FICHIERS = sorted(ICI.glob("*.py"))

PERMIS = {  # ce que la porte a le droit de toucher, par objet
    "prise": {"carte", "etat", "arret_urgence", "robot"},  # lire, et l'arrêt d'urgence (comme le bouton ouvert de l'écran)
    "gardien": {"accord_humain_agents", "plafonds", "regles_lisibles", "demandes_en_attente"},  # lire seulement
    "chaine": {"traiter"},  # LE chemin des ordres : cerveau → gardien (ticket) → prise
    "systeme": {"chaine", "prise", "gardien", "bus", "monde", "compteur", "reglages", "demarrer", "arreter", "boite_noire"},
}
INTERDITS = {"executer", "verifier", "verificateur", "rearmer", "changer_regle", "recharger", "reponse_humaine",
             "provoquer_panne", "reparer", "simulation", "apprendre", "annuler", "arreter_tout", "suivre", "perception"}
MODULES_INTERDITS = ("briques.b01_prise", "briques.b02_faux_robot", "briques.b03_adaptateurs", "briques.b06_cerveau")


def _arbres():
    assert {p.name for p in FICHIERS} >= {"porte.py", "serveur_mcp.py", "commande.py"}
    for p in FICHIERS:
        yield p.name, ast.parse(p.read_text(encoding="utf-8"))


def test_la_porte_ne_touche_que_ce_qui_est_permis():
    fautes = []
    for nom, arbre in _arbres():
        for n in ast.walk(arbre):
            if isinstance(n, ast.Attribute):
                recepteur = ast.unparse(n.value).split(".")[-1]
                if recepteur in PERMIS and n.attr not in PERMIS[recepteur]:
                    fautes.append(f"{nom}:{n.lineno} {ast.unparse(n)}")
                if n.attr in INTERDITS:
                    fautes.append(f"{nom}:{n.lineno} {ast.unparse(n)}")
            if isinstance(n, ast.Name) and n.id in INTERDITS | {"Prise", "Guichet", "Ticket", "Adaptateur", "FauxRobot"}:
                fautes.append(f"{nom}:{n.lineno} {n.id}")
    assert not fautes, "La porte touche ce qui ne lui est pas permis :\n" + "\n".join(fautes)


def test_la_porte_n_importe_ni_prise_ni_robot_ni_cerveau():
    fautes = []
    for nom, arbre in _arbres():
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom) and n.level == 0:
                module = n.module or ""
                if module.startswith(MODULES_INTERDITS):
                    fautes.append(f"{nom}:{n.lineno} {module}")
                if module == "briques.b07_gardien.gardien" and {a.name for a in n.names} != {"PREFIXE_AGENT"}:
                    fautes.append(f"{nom}:{n.lineno} {module} {[a.name for a in n.names]}")
            if isinstance(n, ast.Import):
                fautes += [f"{nom}:{n.lineno} {a.name}" for a in n.names if a.name.startswith(MODULES_INTERDITS)]
    assert not fautes, "\n".join(fautes)


def test_chaque_phrase_va_a_la_chaine_avec_la_source_de_l_agent():
    appels = []
    for nom, arbre in _arbres():
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "traiter":
                source = next((ast.unparse(k.value) for k in n.keywords if k.arg == "source"), None)
                appels.append((nom, source))
    assert appels == [("porte.py", "self.source")]


def test_en_vrai_chaque_action_a_d_abord_le_oui_du_gardien(systeme):
    """Une session complète, accord d'un humain allumé. On espionne qui appelle la prise et le gardien."""
    s = systeme(accord_humain=True)
    appelants = {"executer": [], "verifier": []}

    def espionner(objet, methode):
        vraie = getattr(objet, methode)

        async def espion(*a, **k):
            appelants[methode].append(Path(inspect.stack()[1].filename).relative_to(ICI.parents[1]).as_posix())
            return await vraie(*a, **k)

        setattr(objet, methode, espion)

    espionner(s.prise, "executer")
    espionner(s.gardien, "verifier")

    async def jouer():
        async with session(s, ordres_par_minute=30) as (c, _):
            r = await appeler(c, "dire_au_robot", texte="Va à la table", langue="fr", source="clavier")  # se faire passer pour une personne ?
            assert r["statut"] == "attend_un_humain", "un argument en trop ne change pas la source"
            await s.chaine.reponse_humaine(r["numero_demande"], True, qui="Hiba", attendre_fin=True)
            for texte in ("Va à la table à 2 mètres par seconde", "Take the suitcase", "va", "Batterie ?",
                          "Prends la bouteille", "Salue", "Nimm die Kiste", "stop"):
                r = await appeler(c, "dire_au_robot", texte=texte)
                if r["statut"] == "attend_un_humain":
                    await s.chaine.reponse_humaine(r["numero_demande"], True, qui="Hiba", attendre_fin=True)
            await appeler(c, "arreter")
            await appeler(c, "dire_au_robot", texte="Va à la scène", langue="fr")  # arrêt d'urgence actif : refusé

    lancer(jouer())
    agents = {e.conversation for e in evenements(s, "parole_entendue") if e.source.startswith("agent:")}
    assert {e.source for e in evenements(s, "parole_entendue")} == {"agent:test"}
    demarrees = evenements(s, "action_demarree")
    assert len(demarrees) >= 4 and {e.conversation for e in demarrees} <= agents
    for d in demarrees:
        oui = [g for g in evenements(s, "gardien_decision", d.conversation)
               if g.numero < d.numero and g.donnees["verdict"] == "oui"
               and g.donnees["action"]["nom"] == d.donnees["action"]["nom"]]
        assert oui, f"action partie sans le oui du gardien : {d.donnees}"
        assert oui[-1].donnees["demandeur"].startswith(("agent:", "humain:"))
    for g in evenements(s, "gardien_decision"):
        assert g.donnees["demandeur"] == "agent:test" or g.donnees["demandeur"].startswith("humain:"), g.donnees
    for r in evenements(s, "action_refusee"):
        assert {x["code"] for x in r.donnees["raisons"]} & {"sans_ticket", "ticket_invalide"} == set()
    assert appelants["executer"] and set(appelants["executer"]) == {"commun/chaine.py"}
    assert appelants["verifier"] and set(appelants["verifier"]) == {"commun/chaine.py"}
    assert evenements(s, "arret_urgence")[-1].donnees["qui"] == "agent:test"


def test_un_vrai_robot_n_ouvre_pas_la_porte(reglages, capsys, tmp_path):
    """« python3 lancer.py porte-agents » : faux robot seulement (un vrai robot : feu orange, décision de Hiba)."""
    import argparse

    from briques.b14_porte_agents.commande import main, options

    p = argparse.ArgumentParser()
    options(p)
    args = p.parse_args(["--agent", "test", "--journal", str(tmp_path)])
    vrai = {**reglages, "robot": {**reglages["robot"], "vrai_robot": True}}
    assert main(args, vrai) == 2
    autre = {**reglages, "robot": {**reglages["robot"], "adaptateur": "unitree"}}
    assert main(args, autre) == 2
    sortie = capsys.readouterr()
    assert sortie.out == "" and "FAUX robot" in sortie.err  # rien sur la sortie standard (réservée au protocole MCP)
    assert main(p.parse_args(["--agent", "Pas Bon", "--journal", str(tmp_path)]), reglages) == 2
    assert not list(tmp_path.glob("*.jsonl")), "refusé avant de démarrer quoi que ce soit"
