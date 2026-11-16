"""Brique 13 — Ouvrir /jury dans le navigateur Chromium DÉJÀ installé (Playwright pour Node), sans Internet.

    python -m briques.b13_ecran.capture        refait briques/b13_ecran/capture_jury.png (testé sur faux robot)

Sert aussi au test du navigateur (briques/b13_ecran/tests/test_navigateur.py). N'installe rien, ne télécharge rien.
Le serveur tourne sur 127.0.0.1 (cet ordinateur) ; le navigateur refuse toute adresse qui n'est pas locale.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ICI = Path(__file__).resolve().parent
SCRIPT = ICI / "navigateur_jury.js"
CAPTURE = ICI / "capture_jury.png"


def _port_libre() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextmanager
def serveur_en_fond(app, delai_s: float = 20.0) -> Iterator[str]:
    """Lance l'écran (uvicorn) dans un fil à part, sur 127.0.0.1 ; rend son adresse ; l'arrête à la fin."""
    import uvicorn

    port = _port_libre()
    serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio",
                                            lifespan="on"))
    fil = threading.Thread(target=serveur.run, name="ecran_en_fond", daemon=True)
    fil.start()
    fin = time.monotonic() + delai_s
    while not serveur.started:
        if not fil.is_alive() or time.monotonic() > fin:
            raise RuntimeError("le serveur de l'écran ne démarre pas")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        serveur.should_exit = True
        fil.join(15)


def pourquoi_pas_de_navigateur() -> str | None:
    """None si Node et Playwright (Node) sont là ; sinon la raison (le test saute proprement)."""
    node = shutil.which("node")
    if not node:
        return "Node absent : test du navigateur sauté"
    r = subprocess.run([node, "-e", "require.resolve('playwright')"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return "Playwright pour Node absent : test du navigateur sauté (ne pas l'installer sans « oui » de Hiba)"
    return None


def lancer_navigateur(url: str, *args: str, delai_s: float = 240.0) -> dict:
    """Lance navigateur_jury.js ; rend sa dernière ligne JSON (ou {"saute": raison})."""
    r = subprocess.run([shutil.which("node") or "node", str(SCRIPT), url, *args], capture_output=True, text=True,
                       timeout=delai_s, cwd=ICI)
    lignes = [ligne for ligne in r.stdout.splitlines() if ligne.startswith("{")]
    if not lignes:
        return {"ok": False, "erreurs": [f"aucune réponse du script (code {r.returncode})", r.stderr[-2000:]]}
    resultat = json.loads(lignes[-1])
    if r.returncode not in (0, 3):
        resultat.setdefault("erreurs", []).append(r.stderr[-2000:])
    return resultat


def main() -> int:
    raison = pourquoi_pas_de_navigateur()
    if raison:
        print(raison)
        return 1
    sys.path.insert(0, str(ICI.parents[1]))
    from briques.b13_ecran.serveur import creer_app
    from commun.systeme import Systeme, charger_reglages

    r = charger_reglages()
    r["cerveau"]["choix"] = "regles"  # capture : cerveau à règles (toujours le même résultat)
    r["robot"]["adaptateur"] = "faux_robot"
    systeme = Systeme(r, dossier_journal=Path(tempfile.mkdtemp(prefix="capture_jury_")), acceleration=20)
    with serveur_en_fond(creer_app(systeme)) as url:
        res = lancer_navigateur(url, "capture", str(CAPTURE))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
