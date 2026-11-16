"""Brique 15 — Vérifier un scénario SANS robot : le format, puis les noms (lieux, objets, gestes, actions).

    python3 -m briques.b15_chef_demo.verifier briques/b15_chef_demo/scenarios/essai_3_minutes.yaml
    python3 -m briques.b15_chef_demo.verifier --tous        (tous les fichiers de scenarios/)

Une faute de format = erreur (le chef refuse de jouer). Un nom inconnu du monde ou de la carte = avertissement
(l'étape raterait le jour J).
"""
from __future__ import annotations

import sys
from pathlib import Path

from briques.b01_prise.carte import CarteIdentite
from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES
from commun.monde import Monde

from .scenario import DOSSIER_SCENARIOS, Scenario, ScenarioInvalide, charger


def avertissements(sc: Scenario, carte: str | None = None) -> list[str]:
    """Les noms de l'attendu existent-ils dans le monde (commun/monde.yaml) et sur la carte du faux robot ?"""
    monde = Monde.charger()
    nom_carte = carte or sc.robot
    c = CarteIdentite.charger(DOSSIER_CARTES / f"{nom_carte}.yaml") if nom_carte else None
    lieux = {l.id for l in monde.lieux}
    objets = {o.id for o in monde.objets}
    notes = []
    for i, e in enumerate(sc.etapes, 1):
        a = e.attendu
        if a is None or a.genre not in ("action", "confirmation") or not a.action:
            continue
        ou = f"étape {i} « {e.nom} »"
        p = a.parametres
        if p.get("lieu") and p["lieu"] not in lieux | {"ici"}:
            notes.append(f"{ou} : lieu inconnu « {p['lieu']} » (connus : {', '.join(sorted(lieux))})")
        if p.get("objet") and p["objet"] not in objets:
            notes.append(f"{ou} : objet inconnu « {p['objet']} » (connus : {', '.join(sorted(objets))})")
        if c is not None:
            if not c.sait(a.action):
                notes.append(f"{ou} : le faux {nom_carte} ne sait pas faire « {a.action} »")
            if a.action == "rejouer_geste" and p.get("nom") and p["nom"] not in c.gestes:
                notes.append(f"{ou} : geste « {p['nom']} » absent de la carte (gestes : {', '.join(c.gestes)})")
    return notes


def resume(sc: Scenario) -> list[str]:
    lignes = [f"{sc.titre} — {len(sc.etapes)} étapes"
              + (f", durée visée {sc.duree_visee_s:g} s" if sc.duree_visee_s else "")
              + (f", pour le faux {sc.robot}" if sc.robot else "")]
    for i, e in enumerate(sc.etapes, 1):
        quoi = {"dire": lambda: f"dire [{e.dire.langue}] « {e.dire.texte} »",
                "annonce": lambda: f"annonce [{e.annonce.langue}] « {e.annonce.texte} »",
                "attendre_s": lambda: f"attendre {e.attendre_s:g} s",
                "provoquer_panne": lambda: f"provoquer la panne « {e.provoquer_panne} » (répétition)",
                "reparer": lambda: "réparer les pannes (répétition)",
                "fiche": lambda: "dire la fiche de vérité",
                "controle": lambda: f"contrôle « {e.controle} »"}[e.genre]()
        attendu = f" → attendu : {e.attendu.decrire()}" if e.attendu else ""
        plan_b = f" · plan B : {', '.join(sc.plan_b_de(e)) or 'aucun'}" if e.dire is not None else ""
        lignes.append(f"  {i:>2}. {e.nom} : {quoi}{attendu}{plan_b}")
    return lignes


def main(argv: list[str]) -> int:
    chemins = sorted(DOSSIER_SCENARIOS.glob("*.yaml")) if argv[:1] == ["--tous"] else [Path(a) for a in argv]
    if not chemins:
        print(__doc__)
        return 2
    code = 0
    for chemin in chemins:
        try:
            sc = charger(chemin)
        except (ScenarioInvalide, OSError) as e:
            print(f"✘ {e}\n")
            code = 2
            continue
        print(f"✔ {chemin}")
        print("\n".join(resume(sc)))
        for a in avertissements(sc):
            print(f"  ⚠ {a}")
        print()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
