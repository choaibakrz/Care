#!/usr/bin/env python3
"""Mesurer chaque cerveau Apertus, UN À LA FOIS (sur 16 Go, deux modèles ensemble ne tiennent pas avec le reste).

    python3 outils/banc_cerveaux_mac.py

Pour chaque modèle téléchargé : on le lance (llama.cpp, puce graphique), on passe le banc d'essai du cerveau
(30 demandes × 6 langues), on l'arrête. Aussi, si mlx-lm est installé et la version MLX téléchargée : Apertus 8B
avec MLX (formulaire VÉRIFIÉ après coup, car mlx-lm ne sait pas l'imposer).
Résultats : mesures/cerveau_*.md (un fichier par passage). NON TESTÉ sur Mac.
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))


def banc(nom: str, url: str, formulaire: str = "force") -> None:
    cmd = [sys.executable, str(RACINE / "lancer.py"), "banc-cerveau", "--cerveaux", nom, "--url", f"{nom}={url}"]
    if formulaire != "force":
        cmd += ["--formulaire", f"{nom}={formulaire}"]
    subprocess.run(cmd, check=False)


def attendre(url: str, delai_s: float = 240) -> bool:
    fin = time.time() + delai_s
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url + "/v1/models", timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    from commun.systeme import charger_reglages, creer_serveurs

    serveurs = creer_serveurs(charger_reglages())
    for nom in ("apertus_8b", "apertus_4b"):
        s = serveurs.get(nom)
        if not s or not s.modele.exists():
            print(f"  {nom} : modèle non téléchargé, sauté.")
            continue
        if s.en_marche():
            print(f"  {nom} : le port {s.port} est déjà occupé (programme principal ou « lancer.py cerveau » ?). "
                  "Arrêtez-le d'abord : sinon deux modèles seraient en mémoire, ou le mauvais serait mesuré.")
            continue
        print(f"\n== {nom} (llama.cpp) : chargement…", flush=True)
        s.lancer()
        if s.attendre(240):
            banc(f"{nom}_llamacpp", s.url)
        else:
            print(f"  {nom} : le serveur ne démarre pas.")
        s.eteindre()
        time.sleep(3)
    mlx = RACINE / "modeles" / "apertus-8b-mlx"
    if sys.platform == "darwin" and mlx.exists():
        print("\n== apertus_8b (MLX) : chargement…", flush=True)
        proc = subprocess.Popen([sys.executable, "-m", "mlx_lm.server", "--model", str(mlx), "--port", "8092"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if attendre("http://127.0.0.1:8092"):
                banc("apertus_8b_mlx", "http://127.0.0.1:8092", formulaire="verifie")
        finally:
            proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
