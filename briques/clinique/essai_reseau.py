"""L'essai du réseau local (tâche T05) : les écrans répondent-ils à l'adresse qu'un téléphone utiliserait ?

    python3 -m briques.clinique.essai_reseau

Il lance les écrans sur un port libre, visibles du réseau local, puis demande chaque page à l'adresse que cet
ordinateur a sur le réseau local. Rien ne sort de l'ordinateur : il se parle à lui-même, par son adresse du Wi-Fi.
Ce que cet essai ne prouve pas : qu'un vrai téléphone y arrive (le Wi-Fi du lieu peut l'empêcher). Voir NON_TESTE.md.
"""
from __future__ import annotations

import sys

from fastapi import FastAPI

from .ecrans import BANDEAU, ECRANS, adresse_du_reseau_local, brancher_ecrans
from .horloge import HorlogeDeDemonstration
from .porte import JournalDesAcces, PorteDeLecture


def essai_reseau() -> int:
    """Lance les écrans sur un port libre, visibles du réseau local, et demande chaque page à l'adresse du réseau
    local. Rend 0 si tout répond, 1 si une page manque, 3 si cet ordinateur n'a pas d'adresse sur un réseau local."""
    import threading
    import time
    import urllib.request

    import uvicorn

    adresse = adresse_du_reseau_local()
    if adresse is None:
        print("ESSAI RÉSEAU : pas d'adresse sur un réseau local (Wi-Fi coupé ?). Rien n'a été essayé.")
        return 3
    app = FastAPI()
    horloge = HorlogeDeDemonstration()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge)
    serveur = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=0, log_level="error"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    fin = time.monotonic() + 15
    while not serveur.started and time.monotonic() < fin:
        time.sleep(0.05)
    if not serveur.started:
        print("ESSAI RÉSEAU : le serveur n'a pas démarré.")
        return 1
    port = serveur.servers[0].sockets[0].getsockname()[1]
    chemins = ["/clinique", *(f"/clinique/{ecran}" for ecran in ECRANS), "/clinique/journal"]
    sans_relais = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # tout droit, sans passer par un relais
    bonnes = 0
    for chemin in chemins:
        url = f"http://{adresse}:{port}{chemin}"
        try:
            with sans_relais.open(url, timeout=5) as reponse:
                ok = reponse.status == 200 and BANDEAU in reponse.read().decode("utf-8")
        except OSError as erreur:
            ok = False
            print(f"  {url} : {erreur}")
        bonnes += ok
        print(f"  {'répond' if ok else 'NE RÉPOND PAS'} : {url}")
    serveur.should_exit = True
    fil.join(timeout=5)
    print(f"ESSAI RÉSEAU : {bonnes} pages sur {len(chemins)} répondent à l'adresse du réseau local {adresse}, avec le bandeau.")
    return 0 if bonnes == len(chemins) else 1


if __name__ == "__main__":
    sys.exit(essai_reseau())
