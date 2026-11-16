"""L'écoute sur l'iMac : le modèle d'écoute, et un essai avec de vraies voix du dépôt (tâche R4).

    python3 lancer.py ecoute-mesure                 12 vraies voix par langue (fr, de, it, en), taux d'erreur par langue
    python3 lancer.py ecoute-mesure --phrases 3     plus court
    from briques.clinique import ecoute ; ecoute.ecouter("phrase.wav", "it")

- Le modèle : `modeles/ggml-small.bin` (whisper « small », 488 Mo, licence MIT, téléchargé avec l'accord de Hiba).
- L'outil : `whisper-cli` (whisper.cpp), déjà sur l'iMac. Rien d'autre n'est installé. Tout tourne sur l'ordinateur.
- Les voix : les enregistrements FLEURS du dépôt (`donnees_voix/fleurs/`, vraies voix humaines, phrases LUES, licence
  CC-BY-4.0). CE NE SONT PAS des phrases de la clinique : personne n'y dit « sonnette, fait ».
- Le taux d'erreur est compté par mot, contre le texte de référence, sans la ponctuation ni les majuscules. Calculé.
Les oreilles de l'ossature (brique 4) ne sont pas branchées sur cet outil : elles attendent d'autres paquets
(`requirements-mac.txt`, jamais installés sur un Mac). Cette pièce mesure ; elle n'écoute pas un micro.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

RACINE = Path(__file__).resolve().parents[2]
MODELE = RACINE / "modeles" / "ggml-small.bin"
VOIX = RACINE / "donnees_voix" / "fleurs"
FICHIER_MESURE = RACINE / "journal" / "clinique" / "ecoute_mesure.json"
LANGUES = ("fr", "de", "it", "en")
OUTIL = "whisper.cpp (whisper-cli), modèle « small »"


class EcouteImpossible(RuntimeError):
    """L'écoute n'a pas pu se faire. Le message dit pourquoi."""


def disponible() -> tuple[bool, str]:
    if shutil.which("whisper-cli") is None:
        return False, "l'outil whisper-cli n'est pas sur cet ordinateur"
    if not MODELE.exists():
        return False, f"le modèle d'écoute manque (modeles/{MODELE.name})"
    return True, ""


def ecouter(son: str | Path, langue: str | None = None) -> dict[str, Any]:
    """Le texte d'un enregistrement. `langue` : fr, de, it, en… ; None : l'outil devine la langue."""
    oui, raison = disponible()
    if not oui:
        raise EcouteImpossible(raison)
    son = Path(son)
    if not son.exists():
        raise EcouteImpossible(f"enregistrement absent : {son.name}")
    debut = time.monotonic()
    fait = subprocess.run(["whisper-cli", "-m", str(MODELE), "-f", str(son), "-l", langue or "auto", "-nt", "-np"],
                          capture_output=True, text=True, timeout=120)
    if fait.returncode != 0:
        raise EcouteImpossible(fait.stderr.strip()[-200:] or f"whisper-cli a rendu le code {fait.returncode}")
    return {"texte": " ".join(fait.stdout.split()), "langue": langue or "devinée", "outil": OUTIL,
            "duree_s": round(time.monotonic() - debut, 2)}


def _mots(texte: str) -> list[str]:
    sans = unicodedata.normalize("NFC", str(texte).lower().replace("’", "'"))
    return re.sub(r"[^\w' ]+", " ", sans).split()


def taux_d_erreur_mots(entendu: str, reference: str) -> float:
    """Le taux d'erreur par mot : mots à changer, ajouter ou enlever pour retrouver la référence, divisé par son nombre
    de mots. Sans la ponctuation ni les majuscules. 0 = parfait. Peut dépasser… non : plafonné à 1."""
    a, b = _mots(entendu), _mots(reference)
    if not b:
        return 0.0 if not a else 1.0
    avant = list(range(len(b) + 1))
    for i, ma in enumerate(a, 1):
        ligne = [i]
        for j, mb in enumerate(b, 1):
            ligne.append(min(avant[j] + 1, ligne[j - 1] + 1, avant[j - 1] + (ma != mb)))
        avant = ligne
    return round(min(1.0, avant[-1] / len(b)), 4)


def phrases(langue: str) -> list[dict[str, str]]:
    """Les enregistrements d'une langue, avec leur texte de référence (donnees_voix/fleurs/LANGUE/textes.json)."""
    dossier = VOIX / langue
    return [{"son": str(dossier / p["fichier"]), "texte": p["texte"]}
            for p in json.loads((dossier / "textes.json").read_text(encoding="utf-8")) if (dossier / p["fichier"]).exists()]


def mesurer(langues=LANGUES, par_langue: int | None = None, noter: Path | None = None,
            ecouter_un: Callable[..., dict[str, Any]] = ecouter) -> dict[str, Any]:
    """Écoute les vraies voix du dépôt et compte les mots faux, par langue."""
    par_langue_bilan: dict[str, Any] = {}
    for langue in langues:
        fautes = mots = 0
        durees, exemples = [], []
        for p in phrases(langue)[:par_langue]:
            entendu = ecouter_un(p["son"], langue)
            taux, n = taux_d_erreur_mots(entendu["texte"], p["texte"]), len(_mots(p["texte"]))
            fautes, mots = fautes + taux * n, mots + n
            durees.append(entendu["duree_s"])
            if taux and len(exemples) < 2:
                exemples.append({"entendu": entendu["texte"], "reference": p["texte"], "taux": taux})
        par_langue_bilan[langue] = {"phrases": len(durees), "mots": mots,
                                    "taux_d_erreur": round(fautes / mots, 4) if mots else None,
                                    "duree_moyenne_s": round(sum(durees) / len(durees), 2) if durees else None,
                                    "exemples_d_erreurs": exemples}
    bilan = {"marque": "voix FLEURS (vraies voix, phrases lues, CC-BY-4.0) — pas des phrases de la clinique",
             "outil": OUTIL, "date": datetime.now().isoformat(timespec="seconds"), "par_langue": par_langue_bilan}
    if noter is not None:
        Path(noter).parent.mkdir(parents=True, exist_ok=True)
        Path(noter).write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    return bilan


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print) -> int:
    p = argparse.ArgumentParser(prog="lancer.py ecoute-mesure", description="La clinique en boîte : mesurer l'écoute sur de vraies voix")
    p.add_argument("--phrases", type=int, help="nombre de phrases par langue (par défaut : toutes, 12)")
    a = p.parse_args(reste or [])
    oui, raison = disponible()
    if not oui:
        ecrire(f"Écoute indisponible : {raison}.")
        return 2
    bilan = mesurer(par_langue=a.phrases, noter=FICHIER_MESURE)
    ecrire(f"L'ÉCOUTE SUR CET ORDINATEUR — {bilan['outil']} — RÉEL : un vrai modèle, de vraies voix enregistrées")
    ecrire("Les voix : FLEURS, des personnes qui LISENT une phrase, micro propre. Pas des phrases de la clinique, pas de bruit de salle.")
    for langue, b in bilan["par_langue"].items():
        ecrire(f"- {langue} : taux d'erreur {b['taux_d_erreur'] * 100:.1f} % des mots, sur {b['phrases']} phrases ({b['mots']} mots), "
               f"{b['duree_moyenne_s']} s par phrase en moyenne")
    return 0
