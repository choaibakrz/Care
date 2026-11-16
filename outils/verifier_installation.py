#!/usr/bin/env python3
"""Vérifier l'installation du projet sur cet ordinateur (tâche R1 de la clinique en boîte). Rien n'est modifié.

    python3 outils/verifier_installation.py            les paquets, puis toutes les vérifications de l'ossature
    python3 outils/verifier_installation.py --paquets  les paquets seulement (quelques secondes)

« Fini » veut dire :
  1. l'espace à part `.venv` existe dans le dossier du projet (rien n'est installé dans tout l'ordinateur) ;
  2. chaque paquet de `requirements.txt` y est installé, à la version écrite ;
  3. `python3 lancer.py tests` va jusqu'au bout : aucune ratée, aucun fichier illisible.
Les vérifications « sautées » (un modèle absent, par exemple) sont comptées et montrées, pas cachées.
Code de sortie : 0 si tout est bon, 1 sinon.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
VENV_PY = RACINE / ".venv" / "bin" / "python"


def _nom(n: str) -> str:
    return re.sub(r"[-_.]+", "-", n).lower()


# Sur Mac, ces paquets de requirements.txt ne sont PAS installés, et c'est voulu (DECISIONS.md, LICENCES.md) :
# faster-whisper tire PyAV, qui contient des bibliothèques sous GPL. L'écoute sur Mac passe par whisper.cpp ou MLX.
ECARTES_SUR_MAC = {"faster-whisper": "tire PyAV (GPL) ; écarté des Mac par décision"}
# Paquets que faster-whisper amenait et dont l'ossature a besoin quand même (fin de phrase, voix) : version de LICENCES.md.
EN_PLUS_SUR_MAC = {"onnxruntime": "1.31.1"}


def paquets_demandes() -> dict[str, str]:
    demandes = dict(EN_PLUS_SUR_MAC) if sys.platform == "darwin" else {}
    for ligne in (RACINE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#")[0].strip()
        if "==" in ligne:
            nom, version = ligne.split("==")
            demandes[_nom(nom.split("[")[0])] = version.strip()
    if sys.platform == "darwin":
        for nom in ECARTES_SUR_MAC:
            demandes.pop(nom, None)
    return demandes


def verifier_paquets() -> list[str]:
    if not VENV_PY.exists():
        return ["l'espace à part .venv n'existe pas (attendu : .venv/bin/python)"]
    sortie = subprocess.run([str(VENV_PY), "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                            capture_output=True, text=True)
    if sortie.returncode != 0:
        return [f"pip ne répond pas dans .venv : {sortie.stderr.strip()[:200]}"]
    installes = {_nom(p["name"]): p["version"] for p in json.loads(sortie.stdout)}
    manques = []
    for nom, version in paquets_demandes().items():
        if nom not in installes:
            manques.append(f"{nom} {version} : absent de .venv")
        elif installes[nom] != version:
            manques.append(f"{nom} : version {installes[nom]} dans .venv, {version} demandée")
    if sys.platform == "darwin":
        for nom, raison in ECARTES_SUR_MAC.items():
            if nom in installes:
                manques.append(f"{nom} est installé alors qu'il doit rester absent sur Mac ({raison})")
            else:
                print(f"   absent, et c'est voulu : {nom} ({raison})")
    return manques


def verifier_ossature() -> list[str]:
    sortie = subprocess.run([sys.executable, str(RACINE / "lancer.py"), "tests"], cwd=RACINE,
                            capture_output=True, text=True)
    lignes = [l for l in sortie.stdout.splitlines() if l.strip()]
    bilan = lignes[-1] if lignes else "(aucune sortie)"
    print(f"   sortie de « python3 lancer.py tests » : {bilan}")
    manques = []
    if sortie.returncode != 0:
        manques.append(f"« python3 lancer.py tests » sort avec le code {sortie.returncode}")
    if re.search(r"\d+ (failed|errors?)", bilan):
        manques.append("il reste des ratées ou des fichiers illisibles")
    if not re.search(r"\d+ passed", bilan):
        manques.append("aucune vérification réussie dans le bilan")
    return manques


def main() -> int:
    print("1. Les paquets dans .venv")
    manques = verifier_paquets()
    for m in manques:
        print(f"   manque : {m}")
    if not manques:
        print(f"   ok : {len(paquets_demandes())} paquets de requirements.txt, aux bonnes versions")
    if "--paquets" not in sys.argv and not manques:
        print("2. Toutes les vérifications de l'ossature (2 à 3 minutes)")
        suite = verifier_ossature()
        for m in suite:
            print(f"   manque : {m}")
        manques += suite
    print("RÉSULTAT :", "tout est bon" if not manques else f"{len(manques)} manque(s)")
    return 0 if not manques else 1


if __name__ == "__main__":
    sys.exit(main())
