"""La fiche de vérité de la clinique : ce qui s'est vraiment passé, calculé depuis la boîte noire (cahier 5.11).

    from briques.b12_boite_noire.journal import lire
    fiche_clinique(lire("journal/2026-11-14_090000.jsonl"))

Rien n'est tapé à la main : chaque chiffre vient des événements. Cette fiche s'ajoute à celle de l'ossature
(brique 12), elle ne la remplace pas. Elle grandira avec les pièces (la version complète : tâche T27).
Aujourd'hui elle note : les sauts de l'horloge (« temps accéléré »).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import horloge


def temps_accelere(evenements: Iterable) -> dict[str, Any]:
    sauts = [{"repere": e.donnees.get("repere"), "de": e.donnees.get("de"), "vers": e.donnees.get("vers"),
              "heure_reelle": e.heure}
             for e in evenements
             if e.type == "note" and e.source == horloge.SOURCE and e.donnees.get("quoi") == "saut_horloge"]
    return {"sauts": len(sauts), "marque": horloge.MARQUE if sauts else "", "liste": sauts}


def fiche_clinique(evenements: Iterable) -> dict[str, Any]:
    evenements = list(evenements)
    return {"marque": "données inventées", "temps_accelere": temps_accelere(evenements)}


# ---------------------------------------------------------------------- la fiche de la répétition (tâche T11d)
NON_MESURE = "non mesuré"


def fiche_de_la_repetition(seance) -> dict[str, Any]:
    """Les sept lignes du cahier (5.11), calculées depuis ce que la répétition a noté. Version simple (complète : T27).
    Rien n'est tapé à la main : ce qui n'a pas été mesuré s'écrit « non mesuré », avec la raison."""
    from . import dossier, repetition
    from .flotte import FICHIER as FICHIER_FLOTTE

    import yaml

    jouees = {n: r for n, r in seance.resultats.items() if n <= 12}
    total = 12  # les étapes 1 à 12 : les étapes 13 et 14 sont des contrôles, pas des scènes

    try:  # le faux dossier refuse de se charger si une fiche ne porte pas la marque « inventé »
        charge = dossier.charger()
        inventees = f"oui ({len(dossier.fichiers())} fichiers du faux dossier contrôlés : tous portent la marque « inventé »)"
        del charge
    except Exception as erreur:
        inventees = f"{NON_MESURE} : le faux dossier ne se charge pas ({type(erreur).__name__})"

    robots = yaml.safe_load(FICHIER_FLOTTE.read_text(encoding="utf-8"))["robots"]
    simules = sum(1 for r in robots if r["simule"])

    if seance.sauts is None:
        accelere = f"{NON_MESURE} : la répétition a été jouée sans l'horloge du scénario"
    elif seance.sauts:
        accelere = (f"oui ({seance.sauts} saut{'s' if seance.sauts > 1 else ''} de l'horloge d'affichage du scénario ; "
                    f"chaque pièce a sa propre horloge, dont les sauts ne sont pas comptés ici)")
    else:
        accelere = "non (aucun saut de l'horloge du scénario)"

    joue = sorted(n for n, r in jouees.items() if r.etiquette == "JOUÉ")
    if joue:
        humain = (f"{len(joue)} étape{'s' if len(joue) > 1 else ''} sur {total} jouée{'s' if len(joue) > 1 else ''} "
                  f"par une personne ({', '.join(str(n) for n in joue)})")
    else:
        humain = (f"aucune : 0 étape sur {total} (étapes 1 à 12) jouée par une personne ; les gestes des soignants, de la patiente et "
                  f"du médecin sont faits par le programme")

    comptes = [r.mesures["phrases_retirees"] for r in jouees.values() if "phrases_retirees" in r.mesures]
    retirees = (f"{sum(comptes)} (compté par le résumé du médecin, version simple, sans modèle)" if comptes
                else f"{NON_MESURE} : le résumé du médecin n'a pas donné son compte")

    etiquettes: dict[str, int] = {}
    for r in jouees.values():
        etiquettes[r.etiquette] = etiquettes.get(r.etiquette, 0) + 1
    pas_reussies = sorted(n for n in range(1, 13) if seance.issues.get(n) != "reussie")

    lignes = [
        {"titre": "Données inventées", "valeur": inventees},
        {"titre": "Robots simulés", "valeur": f"{simules} sur {len(robots)} (lu dans flotte.yaml)"},
        {"titre": "Temps accéléré", "valeur": accelere},
        {"titre": "Part de l'humain", "valeur": humain},
        {"titre": "Phrases retirées faute de source", "valeur": retirees},
        *ligne_de_la_lecture(),
        *ligne_de_la_voix(),
        {"titre": "Étiquettes des étapes",
         "valeur": " · ".join(f"{e} : {n}" for e, n in sorted(etiquettes.items())) or "aucune étape jouée"},
        {"titre": "Étapes ratées ou manquantes",
         "valeur": ", ".join(str(n) for n in pas_reussies) if pas_reussies else "aucune parmi les étapes 1 à 12"},
    ]
    from . import essais_reels
    from briques.b12_boite_noire.journal import DOSSIER_DEFAUT

    lignes += lignes_des_essais(essais_reels.CompteurReel(essais_reels.FICHIER), DOSSIER_DEFAUT / "essais_dernier.json")
    from . import brancher

    lignes += lignes_du_branchement(brancher.DOSSIER / brancher.FICHIER)
    from . import mesures_cerveau  # T21 : les temps et les taux mesurés avec le vrai cerveau (lus dans des fichiers)

    lignes += mesures_cerveau.lignes_de_la_fiche()
    lignes += lignes_des_chiffres(seance)  # T27 : les trois chiffres (K02), « réussis et constatés » (K03), le logiciel (L03)
    return {"marque": "données inventées", "lignes": lignes, "du_cahier": 7}


# ---------------------------------------------------------------------- T27 : les chiffres de K02, K03 et L03
LIGNES_EN_PLUS = ("Réussis du premier coup", "Aide humaine", "Plus longue durée sans arrêt", "Réussis et constatés",
                  "Logiciel administratif")
ETIQUETTE_DES_ESSAIS = "FAUX ROBOT ET SIMULÉ"
FICHIER_DE_LA_FICHE = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "fiche_derniere.json"


def cases_de_la_seance(seance) -> dict[str, int]:
    """Une étape de la répétition (1 à 12) = un essai, dans une seule case (avenant 2, K02)."""
    from . import aide_humaine

    cases = {case: 0 for case in aide_humaine.CASES}
    for numero in range(1, 13):
        aides, reprises = seance.par_etape.get(numero, (0, 0))
        cases[aide_humaine.classer(seance.issues.get(numero) == "reussie", aides, reprises)] += 1
    return cases


def lignes_des_chiffres(seance) -> list[dict[str, str]]:
    """Comptés pendant la répétition, jamais tapés. Sans compte (séance d'avant T27) : « non mesuré »."""
    from datetime import date

    from . import aide_humaine, endurance

    if getattr(seance, "aide", None) is None:
        raison = f"{NON_MESURE} : cette répétition n'a pas compté les aides humaines"
        return [{"titre": titre, "valeur": raison} for titre in LIGNES_EN_PLUS]
    compte, cases = seance.aide, cases_de_la_seance(seance)
    passees = endurance.mesures()
    un, deux, trois = aide_humaine.chiffres(cases, len(compte.aides), compte.taches_de_robot, ETIQUETTE_DES_ESSAIS,
                                            date.today().strftime("%d.%m.%Y"), endurance=passees[-1] if passees else None)
    coupe = lambda texte: texte.split(" — ", 1)[1]  # noqa: E731 — sans « CHIFFRE n — »
    un = coupe(un).replace("réussis du premier coup : ", "", 1) + " — une étape de la répétition = un essai"
    trois = coupe(trois).replace("plus longue durée sans arrêt : ", "", 1)
    if compte.livraisons:
        constates = (f"{compte.constatees} sur {compte.livraisons} livraison{'s' if compte.livraisons > 1 else ''} d'un robot "
                     f"[constat par le monde simulé, SIMULÉ ; aucune personne n'a regardé]")
    else:
        constates = "aucune livraison d'un robot dans cette répétition : pas de chiffre"
    admin = seance.admin or {"lus": 0, "a_trier": 0}
    return [{"titre": "Réussis du premier coup", "valeur": un},
            {"titre": "Aide humaine", "valeur": coupe(deux)},
            {"titre": "Plus longue durée sans arrêt", "valeur": trois},
            {"titre": "Réussis et constatés", "valeur": constates},
            {"titre": "Logiciel administratif",
             "valeur": f"SIMULÉ ; messages lus : {admin['lus']} ; messages à trier : {admin['a_trier']} (pendant cette répétition ; "
                       f"un faux logiciel, sur cet ordinateur)"}]


def garder(la_fiche: dict[str, Any], fichier: str | Path | None = None, reussie: bool | None = None) -> dict[str, Any]:
    """Écrit la fiche de la dernière répétition dans un fichier (jamais vers GitHub : le dossier journal/), avec sa date."""
    import json
    from datetime import datetime

    fichier = Path(fichier) if fichier else FICHIER_DE_LA_FICHE
    ecrite = {"marque": "données inventées", "quand": datetime.now().isoformat(timespec="seconds"), "reussie": reussie,
              "lignes": la_fiche["lignes"]}
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(ecrite, ensure_ascii=False, indent=1), encoding="utf-8")
    return ecrite


def derniere(fichier: str | Path | None = None) -> dict[str, Any] | None:
    """La fiche gardée par la dernière répétition. None : aucune, ou fichier abîmé (on n'invente rien)."""
    import json

    fichier = Path(fichier) if fichier else FICHIER_DE_LA_FICHE
    try:
        lue = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return lue if isinstance(lue, dict) and lue.get("marque") == "données inventées" and isinstance(lue.get("lignes"), list) else None


def ligne_de_la_voix(fichier=None) -> list[dict[str, str]]:
    """Le taux d'erreur de la voix, par langue (cahier 5.11), mesuré par « lancer.py ecoute-mesure ». Sinon : non mesuré."""
    import json
    from datetime import datetime
    from pathlib import Path

    from . import ecoute

    try:
        m = json.loads(Path(fichier or ecoute.FICHIER_MESURE).read_text(encoding="utf-8"))
        langues = " ; ".join(f"{l} {b['taux_d_erreur'] * 100:.1f} %" for l, b in m["par_langue"].items())
        n = min(b["phrases"] for b in m["par_langue"].values())
        quand = datetime.fromisoformat(m["date"]).strftime("%d.%m.%Y")
        valeur = (f"{langues} des mots, sur {n} vraies voix par langue (enregistrements FLEURS : des phrases lues, pas des "
                  f"phrases de la clinique, pas de bruit de salle), {m['outil']}, le {quand} ; dans la répétition, rien "
                  f"n'est dit : tout est tapé")
    except (OSError, ValueError, KeyError, TypeError):
        valeur = (f"{NON_MESURE} sur cet ordinateur : lancer « python3 lancer.py ecoute-mesure » (il faut le modèle "
                  "d'écoute) ; dans la répétition, rien n'est dit : tout est tapé")
    return [{"titre": "Taux d'erreur de la voix, par langue", "valeur": valeur}]


def ligne_de_la_lecture(fichier=None) -> list[dict[str, str]]:
    """Le taux d'erreur de lecture des papiers (cahier 5.11), mesuré par « lancer.py papiers-images ». Sinon : non mesuré."""
    import json
    from datetime import datetime
    from pathlib import Path

    from . import papiers_images

    try:
        m = json.loads(Path(fichier or papiers_images.FICHIER_MESURE).read_text(encoding="utf-8"))
        quand = datetime.fromisoformat(m["date"]).strftime("%d.%m.%Y")
        valeur = (f"{m['taux_d_erreur'] * 100:.1f} % des caractères, sur {m['images']} images fabriquées par le programme "
                  f"(pas des photos ; écriture « à la main » imitée par une police), {m['outil']}, le {quand}")
    except (OSError, ValueError, KeyError, TypeError):
        valeur = (f"{NON_MESURE} sur cet ordinateur : lancer « python3 lancer.py papiers-images » (sur un Mac) ; dans la "
                  "répétition, les papiers sont des textes déjà tapés")
    return [{"titre": "Taux d'erreur de lecture des papiers", "valeur": valeur}]


def lignes_du_branchement(fichier) -> list[dict[str, str]]:
    """Deux lignes séparées (avenant jury, J04) : le temps pour brancher une carte sur le FAUX ROBOT, mesuré par la
    commande « brancher-carte » ; et la ligne RÉEL, que ce programme ne remplit jamais."""
    import json
    from datetime import datetime
    from pathlib import Path

    from .brancher import REEL, _duree

    try:
        notes = json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        notes = {}
    finis = [(nom, n) for nom, n in notes.items() if isinstance(n, dict) and n.get("duree_s") is not None]
    if finis:
        nom, n = max(finis, key=lambda x: x[1].get("fin") or 0)
        quand = ""
        try:
            quand = ", le " + datetime.fromisoformat(n["fin_lisible"]).strftime("%d.%m.%Y")
        except (KeyError, ValueError):
            pass
        faux = (f"{_duree(n['duree_s'])} du « je commence » au test réussi, carte « {nom} », {n.get('passages', '?')} passage"
                f"{'s' if n.get('passages', 1) != 1 else ''} du test{quand} (sur le faux robot ; la carte était déjà écrite "
                f"si la durée est courte)")
    else:
        faux = "non mesuré : lancer « python3 lancer.py brancher-carte CARTE --je-commence », puis « brancher-carte CARTE »"
    return [{"titre": "Brancher un robot inconnu — FAUX ROBOT", "valeur": faux},
            {"titre": "Brancher un robot inconnu — RÉEL", "valeur": REEL}]


def lignes_des_essais(compteur, dernier_tableau) -> list[dict[str, str]]:
    """Deux lignes de la fiche (avenant jury, J01), jamais mélangées : les essais comptés sur le faux robot (le
    dernier tableau de « lancer.py essais », avec sa date), et les essais réels comptés par l'équipe (RÉEL)."""
    import json
    from datetime import datetime
    from pathlib import Path

    dernier_tableau = Path(dernier_tableau)
    try:
        t = json.loads(dernier_tableau.read_text(encoding="utf-8"))
        etapes = {k: v for k, v in t["par_etape"].items() if v.get("construite") and v.get("essais")}
        toujours = sum(1 for v in etapes.values() if v["reussies"] == v["essais"])
        pas_toujours = [f"étape {k} : {v['reussies']} sur {v['essais']}" for k, v in etapes.items() if v["reussies"] != v["essais"]]
        manquent = [k for k, v in t["par_etape"].items() if not v.get("construite")]
        echecs = len(t.get("echecs") or [])
        date = datetime.fromisoformat(t["date"]).strftime("%d.%m.%Y")
        faux = (f"{t.get('etiquette', 'FAUX ROBOT')}, le {date} : {t['essais']} essais ; {toujours} étape{'s' if toujours > 1 else ''} "
                f"sur {len(etapes)} toujours réussie{'s' if toujours > 1 else ''} ; {echecs} échec{'s' if echecs > 1 else ''}"
                + ("".join(" ; " + p for p in pas_toujours))
                + (f" ; pas encore construites : {', '.join(manquent)}" if manquent else "")
                + " (seules les étapes 1, 7 et 8 changent d'un essai à l'autre)")
    except (OSError, ValueError, KeyError, TypeError):
        faux = f"{NON_MESURE} sur cet ordinateur : lancer « python3 lancer.py essais » (vingt essais, environ une minute)"
    return [{"titre": "Essais comptés sur le faux robot", "valeur": faux},
            {"titre": "Essais réels, comptés par l'équipe", "valeur": compteur.resume()["texte"]}]


# Les sept lignes que le cahier demande (5.11). L'étape 13 rate s'il en manque une.
LIGNES_DU_CAHIER = ("Données inventées", "Robots simulés", "Temps accéléré", "Part de l'humain",
                    "Phrases retirées faute de source", "Taux d'erreur de lecture des papiers",
                    "Taux d'erreur de la voix, par langue")


def etape_13():
    """Étape 13 : la fiche de vérité est complète. Elle se calcule pendant la répétition, après les étapes 1 à 12."""
    from . import repetition

    seance = repetition.SEANCE
    if seance is None:
        return repetition.Resultat(False, "SIMULÉ", "la fiche se calcule pendant une répétition, après les étapes 1 à 12")
    fiche = fiche_de_la_repetition(seance)
    a_afficher = [f"{l['titre']} : {l['valeur']}" for l in fiche["lignes"]]
    valeurs = {l["titre"]: str(l.get("valeur") or "").strip() for l in fiche["lignes"]}
    absentes = [titre for titre in LIGNES_DU_CAHIER + LIGNES_EN_PLUS if not valeurs.get(titre)]
    non_mesurees = sum(1 for titre in LIGNES_DU_CAHIER if valeurs.get(titre, "").startswith(NON_MESURE))
    mesurees = len(LIGNES_DU_CAHIER) - len(absentes) - non_mesurees
    if absentes:
        return repetition.Resultat(False, "SIMULÉ", "fiche incomplète : il manque " + ", ".join(absentes),
                                   {"a_afficher": a_afficher})
    if not seance.jouees(range(1, 13)):
        manquent = [n for n in range(1, 13) if seance.issues.get(n) not in ("reussie", "ratee")]
        return repetition.Resultat(False, "SIMULÉ", f"fiche incomplète : étapes {', '.join(str(n) for n in manquent)} "
                                                    f"pas jouées, il manque de quoi calculer", {"a_afficher": a_afficher})
    import os

    if "PYTEST_CURRENT_TEST" not in os.environ:  # seule une vraie répétition (la commande) remplace la fiche gardée
        garder(fiche, reussie=None)
    return repetition.Resultat(True, "SIMULÉ",
                               f"version simple : les 7 lignes du cahier sont là ; {mesurees} lignes mesurées sur 7, "
                               f"{non_mesurees} « non mesuré » avec leur raison ; plus {len(LIGNES_EN_PLUS)} lignes des avenants "
                               f"(les trois chiffres, réussis et constatés, le logiciel administratif) ; rien n'est tapé à la "
                               f"main ; la fiche est gardée dans un fichier et montrée sur /clinique/fiche-de-verite ; elle "
                               f"n'est pas écrite dans la boîte noire",
                               {"a_afficher": a_afficher, "fiche": fiche})
