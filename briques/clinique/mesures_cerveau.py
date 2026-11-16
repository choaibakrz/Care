"""T21 — Les mesures du vrai cerveau, gardées pour la fiche de vérité (cahier 5.11 : temps de réponse, taux d'erreur).

Chaque commande de mesure (`apertus-essai`, `resume-apertus`, `papiers-apertus`, `tirage-apertus`, `chaine-mesure`)
garde son dernier résultat dans un fichier : `journal/clinique/mesures_cerveau/NOM.json`. Ce dossier ne part pas vers
GitHub. La fiche de vérité lit ces fichiers et en tire cinq lignes. RIEN N'EST TAPÉ À LA MAIN :
- pas de fichier, fichier abîmé, mesure impossible → « non mesuré sur cet ordinateur », avec la commande à lancer ;
- un essai fait avec un cerveau de test n'est jamais gardé ici : ce dossier ne contient que le vrai cerveau.
Ces lignes disent la DERNIÈRE mesure, sur cet ordinateur, avec des données inventées. Elles ne promettent rien.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DOSSIER = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "mesures_cerveau"
NON_MESURE = "non mesuré"
TITRES = {"apertus_essai": "Cerveau — comprendre un ordre", "resume": "Cerveau — le résumé du médecin",
          "papiers": "Cerveau — le rangement des papiers", "tirage": "Cerveau — le tirage de trente demandes",
          "chaine": "La chaîne entière : écoute, cerveau, voix"}
COMMANDES = {"apertus_essai": "apertus-essai", "resume": "resume-apertus", "papiers": "papiers-apertus",
             "tirage": "tirage-apertus 1", "chaine": "chaine-mesure"}


def noter(nom: str, mesure: dict[str, Any], dossier: str | Path | None = None) -> Path | None:
    """Garde la dernière mesure. Rend None (et n'écrit rien) si ce n'est pas le vrai cerveau."""
    if nom not in TITRES:
        raise ValueError(f"mesure inconnue : {nom}")
    qui = str(mesure.get("cerveau") or mesure.get("pieces") or mesure.get("modele") or "")
    if mesure.get("possible", True) and "Apertus" not in qui:
        return None  # un cerveau de test : jamais gardé comme une mesure du vrai cerveau
    dossier = Path(dossier) if dossier else DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    garde = {"quand": mesure.get("quand") or datetime.now().astimezone().isoformat(timespec="seconds"), **mesure}
    fichier = dossier / f"{nom}.json"
    fichier.write_text(json.dumps(garde, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    return fichier


def _lentes(n: int, quoi: str = "réponse") -> str:
    if n == 0:
        return f"aucune {quoi} de plus de 5 secondes"
    return f"{n} {quoi}{'s' if n > 1 else ''} de plus de 5 secondes"


def _valeur(nom: str, m: dict[str, Any]) -> str:
    jour = datetime.fromisoformat(m["quand"]).strftime("%d.%m.%Y")
    fin = f"cerveau RÉEL (Apertus 8B), dernière mesure le {jour}, sur cet ordinateur, données inventées"
    if nom == "apertus_essai":
        return (f"{m['bonnes']} bonnes réponses sur {m['demandes']} ; médian {m['temps_median_ms']} ms, le plus long "
                f"{m['temps_max_ms']} ms ; {_lentes(len(m['plus_de_5_s']))} ; FAUX ROBOT ; {fin}")
    if nom == "resume":
        return (f"{m['ecrites']} ligne{'s' if m['ecrites'] > 1 else ''} gardée{'s' if m['ecrites'] > 1 else ''} sur {m['demandees']} "
                f"après contrôle (les autres : version simple, par des règles) ; médian {m['ligne_mediane_ms']} ms par ligne, "
                f"le plus long {m['ligne_max_ms']} ms ; {m['lignes_lentes']} de plus de 5 secondes ; aucun robot ; {fin}")
    if nom == "papiers":
        return (f"{m['bien_ranges_surs']} bien rangés et sûrs sur {m['papiers']} (les règles simples seules : "
                f"{m['regles_seules_bien_ranges_surs']} sur {m['papiers']}) ; {m['mal_ranges_dits_surs']} mal rangé dit sûr ; "
                f"médian {m['temps_median_ms']} ms, le plus long {m['temps_max_ms']} ms ; {_lentes(len(m['plus_de_5_s']))} ; "
                f"textes tapés, pas des images ; aucun robot ; {fin}")
    if nom == "tirage":
        return (f"compris {m['compris']} sur {m['demandes']} ; bonnes réponses du système {m['bonnes']} sur {m['demandes']} ; "
                f"gestes interdits exécutés : {m['interdits_executes']} ; gestes partis à tort : {m['partis_a_tort']} ; "
                f"médian {m['temps_median_ms']} ms, le plus long {m['temps_max_ms']} ms ; {_lentes(len(m['plus_de_5_s']))} ; "
                f"tirage n° {m['numero']} ; FAUX ROBOT ; {fin}")
    memoire = m["memoire"]
    faites = len(m["phrases"]) - m["sans_reponse"]
    return (f"de la fin de la phrase au début de la réponse : médian {m['total_median_ms']} ms, le plus long {m['total_max_ms']} ms, "
            f"sur {faites} phrases dites par une voix de synthèse (pas de micro, pas de bruit) ; {_lentes(len(m['plus_de_5_s']))} ; "
            f"mémoire : {memoire['moins_de_libre_go']} Go libres au plus bas, {memoire['echange_en_plus_go']} Go d'échange en plus — "
            + ("LA MÉMOIRE MANQUE" if memoire["manque"] else "la mémoire n'a pas manqué") + f" ; aucun robot ; {fin}")


def lignes_de_la_fiche(dossier: str | Path | None = None) -> list[dict[str, str]]:
    dossier = Path(dossier) if dossier else DOSSIER
    lignes = []
    for nom, titre in TITRES.items():
        try:
            mesure = json.loads((dossier / f"{nom}.json").read_text(encoding="utf-8"))
            if not mesure.get("possible", True):
                raise ValueError("mesure impossible")
            valeur = _valeur(nom, mesure)
        except (OSError, ValueError, KeyError, TypeError):
            valeur = (f"{NON_MESURE} sur cet ordinateur : lancer « python3 lancer.py {COMMANDES[nom]} » "
                      f"(il faut le modèle Apertus et son serveur, déjà sur l'iMac)")
        lignes.append({"titre": titre, "valeur": valeur})
    return lignes
