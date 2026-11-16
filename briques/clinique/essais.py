"""Les essais comptés : le scénario joué vingt fois, avec de petits changements (avenant jury, J01).

    python3 lancer.py essais                 les vingt essais de essais.yaml, sur le faux robot
    python3 lancer.py essais --nombre 5      les cinq premiers seulement (le tableau le dit)

« Sur vingt essais, combien réussissent ? » : pour chaque étape de la répétition, « réussie tant de fois sur vingt ».
Pour chaque échec : le numéro de l'essai, l'étape, et l'heure dans la boîte noire.

- La liste des changements est FIXE (essais.yaml) : la langue d'arrivée, le point oublié, l'objet demandé, un objet
  absent de la réserve. On rejoue exactement les mêmes essais. On n'ajuste pas la liste pour réussir.
- Un échec se montre. Aucun essai raté n'est effacé, caché ou rejoué.
- Chaque étape de chaque essai est écrite dans une boîte noire (un fichier dans journal/).
- DIRE VRAI : aucun modèle ne sert ici. Les pièces de la version simple marchent par des règles ; « cerveau plus
  lent » est écrit dans la liste mais n'a aucun effet tant qu'aucune pièce n'appelle le cerveau. L'option
  « --apertus » le dit et s'arrête. Aucun vrai robot : étiquette FAUX ROBOT (étape 8, reprise de l'étape 12), les
  autres étapes sont SIMULÉ.
Commande longue : elle n'est pas dans la vérification rapide.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from briques.b12_boite_noire.journal import DOSSIER_DEFAUT, BoiteNoire
from commun.bus import Bus

from . import aide_humaine, chef_clinique, repetition
from .essais_reels import CompteurReel

FICHIER = Path(__file__).resolve().parent / "essais.yaml"
LANGUES = ("it", "de", "fr", "en")
SOURCE = "essais_clinique"
CERVEAU = "aucun modèle (version simple : des règles et des réponses fixes ; Apertus n'est pas encore branché)"


class EssaisInvalides(ValueError):
    """Le fichier des essais n'a pas la forme attendue. Le message dit quoi."""


def charger(fichier: Path = FICHIER) -> list[dict[str, Any]]:
    donnees = yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))
    if not isinstance(donnees, dict) or donnees.get("marque") != "inventé":
        raise EssaisInvalides(f"{fichier} : il faut « marque: inventé » puis « essais: »")
    liste = []
    for i, essai in enumerate(donnees.get("essais") or [], 1):
        attendues = {"numero", "langue", "point_oublie", "objet", "objet_absent", "cerveau_lent"}
        if not isinstance(essai, dict) or set(essai) != attendues:
            raise EssaisInvalides(f"essai {i} : il faut exactement {', '.join(sorted(attendues))}")
        if essai["numero"] != i:
            raise EssaisInvalides(f"essai {i} : les essais sont numérotés 1, 2, 3… (trouvé {essai['numero']})")
        if essai["langue"] not in LANGUES:
            raise EssaisInvalides(f"essai {i} : langue inconnue « {essai['langue']} » (connues : {', '.join(LANGUES)})")
        if essai["point_oublie"] not in range(1, 7):
            raise EssaisInvalides(f"essai {i} : point oublié {essai['point_oublie']} : la liste a six points, de 1 à 6")
        if not str(essai["objet"]).strip():
            raise EssaisInvalides(f"essai {i} : l'objet demandé est vide")
        liste.append(dict(essai))
    if not liste:
        raise EssaisInvalides(f"{fichier} : aucun essai")
    return liste


def jouer_les_essais(liste: list[dict[str, Any]], controles: dict[int, Callable] | None = None,
                     ecrire: Callable[[str], None] = print, dossier: str | Path = DOSSIER_DEFAUT,
                     total_de_la_liste: int | None = None, compteur_reel: CompteurReel | None = None) -> dict[str, Any]:
    """Joue chaque essai une fois, dans l'ordre, sans jamais rejouer. Écrit le tableau. Rend le bilan."""
    controles = repetition.CONTROLES if controles is None else controles
    total_de_la_liste = total_de_la_liste or len(charger())
    debut = datetime.now()
    bus = Bus()
    boite = BoiteNoire(bus, dossier, nom=debut.strftime("essais_%Y-%m-%d_%H%M%S_%f"))
    par_etape = {e.numero: {"reussies": 0, "essais": 0, "etiquettes": set(), "construite": True} for e in repetition.ETAPES}
    echecs: list[dict[str, Any]] = []
    par_essai: dict[int, dict[str, Any]] = {}  # avenant 2, K02 : la case de chaque essai, ses aides humaines, ses tâches de robot

    async def noter(**donnees: Any):
        return await bus.emettre("note", SOURCE, quoi="etape_d_un_essai", **donnees)

    async def noter_autre(quoi: str, **donnees: Any):
        return await bus.emettre("note", SOURCE, quoi=quoi, **donnees)

    try:
        for essai in liste:
            sortie: list[str] = []
            seances: list[repetition.Seance] = []
            with repetition.variation(essai), aide_humaine.compter() as compte:
                chef_clinique.jouer(controles, ecrire=sortie.append, garder=seances)
            seance = seances[0]
            reussi = all(seance.issues.get(e.numero) == "reussie" for e in repetition.ETAPES)
            case = aide_humaine.classer(reussi, len(compte.aides), compte.reprises_imprevues)
            par_essai[essai["numero"]] = {"case": case, "aides": len(compte.aides), "taches_de_robot": compte.taches_de_robot,
                                          "reprises_prevues": compte.reprises_prevues, "reprises_imprevues": compte.reprises_imprevues,
                                          "livraisons": compte.livraisons, "constatees": compte.constatees}
            for aide in compte.aides:  # l'événement AIDE HUMAINE, dans la boîte noire, avec le numéro de l'essai
                asyncio.run(noter_autre(**{c: v for c, v in aide.items() if c != "dans_la_boite"}, essai=essai["numero"]))
            asyncio.run(noter_autre("essai_classe", essai=essai["numero"], **par_essai[essai["numero"]]))
            for etape in repetition.ETAPES:
                issue, resultat = seance.issues.get(etape.numero, "manquante"), seance.resultats.get(etape.numero)
                ligne = next((l for l in sortie if l.startswith(f"{etape.numero:>2}. ")), "")
                etiquette = resultat.etiquette if resultat is not None else ""
                evenement = asyncio.run(noter(essai=essai["numero"], etape=etape.numero, issue=issue, etiquette=etiquette,
                                              changements={c: essai[c] for c in essai if c != "numero"},
                                              ligne=ligne[:400]))
                compte = par_etape[etape.numero]
                if issue == "manquante":
                    compte["construite"] = False
                    continue
                compte["essais"] += 1
                if etiquette:
                    compte["etiquettes"].add(etiquette)
                if issue == "reussie":
                    compte["reussies"] += 1
                else:
                    echecs.append({"essai": essai["numero"], "etape": etape.numero,
                                   "moment": f"/clinique/moments/voir?seance={boite.fichier.stem}&m={evenement.id}",
                                   "heure": str(evenement.heure)[:19].replace(" ", "T"), "cause": ligne[:400],
                                   "changements": {c: essai[c] for c in essai if c != "numero"}})
    finally:
        boite.fermer()

    n = len(liste)
    for compte in par_etape.values():
        compte["etiquettes"] = sorted(compte["etiquettes"])
    ecrire(f"LES ESSAIS COMPTÉS — la clinique en boîte — FAUX ROBOT — {debut.strftime('%d.%m.%Y, %H:%M')} — DONNÉES INVENTÉES")
    ecrire(f"Cerveau : {CERVEAU}.")
    ecrire("Robot : le faux robot (étape 8, et la reprise de l'étape 12) ; aucun vrai robot. Les autres étapes sont SIMULÉ : "
           "chaque ligne porte son étiquette.")
    ecrire("Changements à chaque essai (liste fixe, essais.yaml) : la langue d'arrivée, le point oublié, l'objet demandé, "
           "un objet absent de la réserve. « cerveau plus lent » : écrit dans la liste, sans effet aujourd'hui (aucune "
           "pièce n'appelle le cerveau).")
    ecrire("À savoir : seules les étapes 1, 7 et 8 changent d'un essai à l'autre (leur titre garde les mots du cahier : "
           "italien, la sonnette, un coussin). Les onze autres rejouent vingt fois le même contrôle, sans hasard : "
           "leur « 20 sur 20 » dit qu'elles sont stables, pas qu'elles résistent à des cas nouveaux.")
    if n != total_de_la_liste:
        ecrire(f"Attention : {n} essais joués, sur les {total_de_la_liste} de la liste.")
    manquantes = 0
    for etape in repetition.ETAPES:
        compte = par_etape[etape.numero]
        if not compte["construite"]:
            manquantes += 1
            ecrire(f"{etape.numero:>2}. [—] pas encore construite ({etape.piece}) — {etape.titre}")
        else:
            ecrire(f"{etape.numero:>2}. [{', '.join(compte['etiquettes']) or '—'}] réussie {compte['reussies']} fois sur "
                   f"{compte['essais']} — {etape.titre}")
    if echecs:
        ecrire(f"Échecs : {len(echecs)} (aucun n'est effacé ni rejoué)")
        for e in echecs:
            ecrire(f"  - essai {e['essai']}, étape {e['etape']} — heure dans la boîte noire : {e['heure']} (UTC) — "
                   f"changements : {e['changements']} — {e['cause']} → moment : {e['moment']}")
    else:
        ecrire("Aucun échec dans ces essais.")
    # ---- avenant 2, K02 : les quatre cases, puis les chiffres (ajoutés ; les lignes de J01 ne changent pas)
    cases = {c: sum(1 for e in par_essai.values() if e["case"] == c) for c in aide_humaine.CASES}
    aides = sum(e["aides"] for e in par_essai.values())
    taches = sum(e["taches_de_robot"] for e in par_essai.values())
    prevues = sum(e["reprises_prevues"] for e in par_essai.values())
    ecrire("Les quatre cases (un essai ne va que dans une case) : " + " ; ".join(f"{c} : {cases[c]}" for c in aide_humaine.CASES)
           + f" — sur {n} essais")
    ecrire(f"À savoir : {prevues} reprise{'s' if prevues > 1 else ''} après une panne PROVOQUÉE : elles font partie du scénario, "
           "elles ne comptent pas comme « reprise automatique ». Un objet absent, passé à un humain, compte comme une aide humaine.")
    from .endurance import plus_longue

    for ligne in aide_humaine.chiffres(cases, aides, taches, "FAUX ROBOT", debut.strftime("%d.%m.%Y"), endurance=plus_longue(dossier)):
        ecrire(ligne)
    # ---- avenant 2, K03 : réussis ET constatés (une ligne de plus ; les lignes de K02 ne changent pas)
    livraisons = sum(e["livraisons"] for e in par_essai.values())
    constatees = sum(e["constatees"] for e in par_essai.values())
    constates = sum(1 for e in par_essai.values() if e["case"] != aide_humaine.CASES[3] and e["constatees"] == e["livraisons"])
    ecrire(f"EN PLUS — réussis et constatés : {constates} sur {n} [FAUX ROBOT, {n} essais, {debut.strftime('%d.%m.%Y')}] — "
           f"livraisons constatées : {constatees} sur {livraisons} (constat : l'état du monde simulé, SIMULÉ ; un essai compte "
           "s'il est réussi et si chaque livraison a été constatée)")
    ecrire((compteur_reel or CompteurReel()).resume()["texte"])
    ecrire(f"Boîte noire : {boite.fichier}")
    toujours = sum(1 for c in par_etape.values() if c["construite"] and c["essais"] and c["reussies"] == c["essais"])
    ecrire(f"ESSAIS COMPTÉS : {n} essais, {toujours} étapes sur {len(par_etape)} toujours réussies, "
           f"{len(echecs)} échec{'s' if len(echecs) > 1 else ''}")
    fiche = {"etiquette": "FAUX ROBOT", "date": debut.isoformat(timespec="seconds"), "cerveau": CERVEAU, "essais": n,
             "essais_de_la_liste": total_de_la_liste, "par_etape": par_etape, "echecs": echecs,
             "cases": cases, "par_essai": par_essai, "aides_humaines": aides, "taches_de_robot": taches,
             "reprises_prevues": prevues, "reussis_et_constates": constates,
             "livraisons": livraisons, "livraisons_constatees": constatees,
             "boite_noire": str(boite.fichier), "marque": "données inventées"}
    (Path(dossier) / "essais_dernier.json").write_text(json.dumps(fiche, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"essais": n, "echecs": echecs, "code": 0 if not echecs and not manquantes else 1, "fiche": fiche,
            "boite_noire": boite.fichier}


def main(reste: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lancer.py essais", description="La clinique en boîte : les essais comptés")
    p.add_argument("--nombre", type=int, help="jouer seulement les N premiers essais de la liste")
    p.add_argument("--apertus", action="store_true", help="jouer avec le vrai Apertus (pas encore possible)")
    args = p.parse_args(reste or [])
    if args.apertus:
        print("Option --apertus : pas encore possible. Aucune pièce de la version simple n'appelle le cerveau ; "
              "Apertus sera branché avec les tâches R2 et T13. Rien n'a été joué.")
        return 2
    liste = charger()
    if args.nombre is not None:
        liste = liste[:max(1, args.nombre)]
    return jouer_les_essais(liste)["code"]
