"""T30 — Le réseau local : une page d'entrée pour les téléphones du même Wi-Fi.

    /clinique/telephones        chaque écran, avec son adresse complète sur le Wi-Fi, écrite en gros

Le cahier demande aussi un code QR pour chaque écran. Aucun outil pour dessiner ces codes n'est sur cet ordinateur :
c'est un feu orange (question Q29 à Hiba). En attendant, les adresses sont écrites en gros.

L'adresse du Wi-Fi : on demande au système quelle adresse il utiliserait pour parler au réseau local (une « prise »
UDP ouverte vers une adresse privée : rien n'est envoyé). Seule une adresse du réseau local est donnée ; sinon la page
dit qu'elle n'en a pas trouvé, et n'invente rien.
Si le serveur n'écoute que cet ordinateur (réglage ecran.hote = 127.0.0.1), la page dit que les téléphones ne pourront
pas ouvrir ces adresses.
"""
from __future__ import annotations

import ipaddress
import socket

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

PAGE = "/clinique/telephones"
AUTRES = {"invite": "Invité", "tableau-de-flotte": "Tableau de flotte", "fiche-de-verite": "Fiche de vérité",
          "avis/donner": "Votre avis"}
RESEAUX_LOCAUX = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10",
                                                    "169.254.0.0/16")]


def est_locale(adresse: str) -> bool:
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    return any(ip in reseau for reseau in RESEAUX_LOCAUX)


def adresse_du_wifi() -> str | None:
    """L'adresse de cet ordinateur sur le réseau local, ou None.
    1. On demande au système quelle adresse il prendrait pour le réseau local : une prise UDP « orientée », rien n'est envoyé.
    2. Si c'est refusé (les essais coupent tout réseau), on demande à macOS l'adresse de ses cartes réseau (`ipconfig`)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.255.254", 9))
            adresse = s.getsockname()[0]
        if est_locale(adresse):
            return adresse
    except OSError:
        pass
    import shutil
    import subprocess

    if shutil.which("ipconfig") is None:
        return None
    for carte in ("en0", "en1", "en2"):
        try:
            sortie = subprocess.run(["ipconfig", "getifaddr", carte], capture_output=True, text=True, timeout=2).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if est_locale(sortie):
            return sortie
    return None


def ecrans() -> list[tuple[str, str]]:
    """(chemin, titre) de chaque écran à ouvrir sur un téléphone."""
    from .ecrans import ECRANS

    return [(f"clinique/{e}", titre) for e, (titre, _, _) in ECRANS.items()] + [(f"clinique/{e}", t) for e, t in AUTRES.items()]


def titre_attendu(chemin: str) -> str:
    """Le titre de la page que cette adresse doit ouvrir (pour vérifier qu'elle mène au bon écran)."""
    return "Clinique — " + dict(ecrans())[chemin.split("?", 1)[0]]


def dessiner(ip: str | None, port: int, ecoute: str | None = None) -> str:
    from .ecrans import _e

    gros = "font-size:1.6rem;font-family:ui-monospace,Menlo,monospace;overflow-wrap:anywhere;margin:.2rem 0 1rem"
    if ip is None:
        liste = ("<p><b>Aucune adresse du Wi-Fi trouvée.</b> Cet ordinateur n'est peut-être sur aucun réseau. Branchez-le au "
                 "Wi-Fi, puis rechargez cette page.</p>")
    else:
        liste = "".join(f"<p style='margin:.6rem 0 0'><b>{_e(titre)}</b></p><p style='{gros}'>http://{_e(ip)}:{int(port)}/{_e(chemin)}</p>"
                        for chemin, titre in ecrans())
    avertissement = ""
    if ecoute is not None and ecoute not in ("0.0.0.0", "::", "") and not est_locale(str(ecoute)):
        avertissement = (f"<p class='rate' style='font-weight:700'>Le serveur n'écoute que cet ordinateur (réglage ecran.hote = "
                         f"{_e(ecoute)}) : les téléphones ne pourront pas ouvrir ces adresses. Mettre 0.0.0.0 dans reglages.yaml, "
                         "puis relancer le serveur.</p>")
    return ("<p>Pour un téléphone ou une tablette branché sur le <b>même Wi-Fi</b> que cet ordinateur : tapez l'adresse de "
            "l'écran dans le navigateur. Ensuite, choisissez votre badge sur l'écran.</p>" + avertissement + liste
            + "<p class='ou'>Codes QR : pas encore. Il faut un outil pour les dessiner, et rien n'est installé sans l'accord "
              "de Hiba (question Q29).</p>"
              "<p class='ou'>Rien ne sort du réseau local : ces adresses ne marchent que sur ce Wi-Fi. Données inventées.</p>")


def essayer_par_le_wifi(ecrire=print) -> int:
    """Hors des essais automatiques (qui coupent tout réseau sauf cet ordinateur) : le serveur écoute sur toutes les
    adresses, et chaque adresse de la page est ouverte par l'adresse du Wi-Fi, comme un téléphone le ferait.
    Rien ne sort du réseau local."""
    import threading
    import time

    import httpx
    import uvicorn

    from .ecrans import brancher_ecrans

    ip = adresse_du_wifi()
    ecrire("LE RÉSEAU LOCAL — les écrans par l'adresse du Wi-Fi — DONNÉES INVENTÉES")
    if ip is None:
        ecrire("Aucune adresse du Wi-Fi trouvée : cet ordinateur n'est sur aucun réseau local. Rien n'est essayé.")
        return 2
    with socket.socket() as s:
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
    app = FastAPI()
    brancher_ecrans(app)
    service = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error"))
    fil = threading.Thread(target=service.run, daemon=True)
    fil.start()
    ratees = []
    try:
        for _ in range(100):
            try:
                if httpx.get(f"http://{ip}:{port}{PAGE}", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        import re

        page = httpx.get(f"http://{ip}:{port}{PAGE}", timeout=5).text
        adresses = re.findall(r"http://[0-9.]+:\d+/clinique/[^\s<\"']*", page)
        ecrire(f"page d'entrée : http://{ip}:{port}{PAGE} — {len(adresses)} adresses")
        for adresse in adresses:
            r = httpx.get(adresse, timeout=5)
            titre = re.search(r"<title>(.*?)</title>", r.text)
            attendu = titre_attendu(adresse.split(":", 2)[2].split("/", 1)[1])
            bon = r.status_code == 200 and titre is not None and attendu in titre.group(1)
            ratees += [] if bon else [adresse]
            ecrire(f"  {adresse} → {r.status_code}, {titre.group(1) if titre else 'pas de titre'} — {'bon écran' if bon else 'RATÉ'}")
    finally:
        service.should_exit = True
        fil.join(timeout=5)
    ecrire("Essayé depuis cet ordinateur, par son adresse du Wi-Fi ; pas depuis un vrai téléphone.")
    ecrire("RÉSEAU LOCAL : RÉUSSI" if adresses and not ratees else f"RÉSEAU LOCAL : RATÉ ({len(ratees)} adresses)")
    return 0 if adresses and not ratees else 1


def main(reste=None) -> int:
    return essayer_par_le_wifi()


def brancher_reseau_local(app: FastAPI, ecoute: str | None = None, port_des_reglages: int | None = None) -> None:
    from .ecrans import _page

    @app.get(PAGE, response_class=HTMLResponse)
    async def page_telephones(request: Request):
        port = request.url.port or port_des_reglages or 8000
        return _page("Clinique — Téléphones", "<h1>Les écrans sur un téléphone</h1>",
                     dessiner(adresse_du_wifi(), port, ecoute), lisible=True)
