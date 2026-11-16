"""La clinique en boîte — N01b, le clic sur « Source » dans un vrai navigateur (priorité de Hiba, 12.11.2026).

« Dans le navigateur, un clic doit ouvrir le document, comme pour une personne. Corrige-le, avec une vérification qui
clique vraiment. »
Cette vérification lance le vrai serveur de pages sur cet ordinateur, ouvre Chrome (sans fenêtre), et envoie de VRAIS
gestes de souris par la porte de pilotage de Chrome : le bouton descend sur le lien, puis remonte. Ce n'est pas un
« click() » appelé par un programme dans la page.
- Un clic court sur « Source : Fiche du séjour » ouvre la source.
- Un clic LENT (le doigt reste appuyé plus de deux secondes, le temps que la page se rafraîchisse toute seule) ouvre
  aussi la source. C'est ce cas qui ratait : la page remplaçait le lien sous le doigt, et le clic se perdait.
- Pendant ce temps, la page continue de se mettre à jour (son âge revient à zéro).
Sans Chrome sur l'ordinateur, l'essai est sauté : on n'installe rien pour lui. Ce n'est pas « vu par un humain ».
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur : le clic n'est pas essayé (rien à installer)")


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def serveur():
    """Le vrai serveur de pages de la clinique, sur cet ordinateur seulement, le temps de l'essai."""
    import uvicorn
    from fastapi import FastAPI

    from briques.clinique.carnet import Carnet
    from briques.clinique.ecrans import brancher_ecrans
    from briques.clinique.horloge import HorlogeDeDemonstration
    from briques.clinique.porte import JournalDesAcces, PorteDeLecture

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge, carnet=Carnet(horloge=horloge))
    port = _port_libre()
    service = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=service.run, daemon=True)
    fil.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/clinique", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    service.should_exit = True
    fil.join(timeout=5)


@pytest.fixture(scope="module")
def chrome(tmp_path_factory):
    """Chrome sans fenêtre, avec sa porte de pilotage ouverte sur cet ordinateur seulement."""
    port = _port_libre()
    proc = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1200,900",
                             f"--remote-debugging-port={port}", f"--user-data-dir={tmp_path_factory.mktemp('profil')}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    adresse = None
    for _ in range(100):
        try:
            pages = [p for p in httpx.get(f"http://127.0.0.1:{port}/json", timeout=0.5).json() if p.get("type") == "page"]
            if pages:
                adresse = pages[0]["webSocketDebuggerUrl"]
                break
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.1)
    if adresse is None:
        proc.terminate()
        pytest.skip("Chrome ne s'ouvre pas avec sa porte de pilotage sur cet ordinateur")
    yield adresse
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


class Pilote:
    def __init__(self, ws) -> None:
        self.ws, self.n = ws, 0

    async def ordre(self, methode: str, **parametres):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": methode, "params": parametres}))
        while True:
            reponse = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=20))
            if reponse.get("id") == self.n:
                assert "error" not in reponse, reponse
                return reponse.get("result", {})

    async def lire(self, expression: str):
        rendu = await self.ordre("Runtime.evaluate", expression=expression, returnByValue=True)
        return rendu["result"].get("value")

    async def ouvrir(self, adresse: str) -> None:
        await self.ordre("Page.enable")
        await self.ordre("Page.navigate", url=adresse)
        for _ in range(100):
            if await self.lire("document.readyState") == "complete" and await self.lire("location.href") == adresse:
                return
            await asyncio.sleep(0.1)
        raise AssertionError(f"la page ne s'ouvre pas : {adresse}")

    async def milieu_du_lien(self, texte: str) -> dict:
        trouve = await self.lire(
            "(() => { const a = [...document.querySelectorAll('a')].find(a => a.textContent.trim() === " + json.dumps(texte) + ");"
            " if (!a) return null; a.scrollIntoView({block: 'center'}); const r = a.getBoundingClientRect();"
            " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()")
        assert trouve, f"le lien « {texte} » n'est pas sur la page"
        return trouve

    async def cliquer(self, point: dict, appui_s: float) -> None:
        """Un vrai geste de souris : aller sur le lien, appuyer, attendre, relâcher."""
        commun = {"x": point["x"], "y": point["y"], "button": "left", "clickCount": 1}
        await self.ordre("Input.dispatchMouseEvent", type="mouseMoved", x=point["x"], y=point["y"])
        await self.ordre("Input.dispatchMouseEvent", type="mousePressed", **commun)
        await asyncio.sleep(appui_s)
        await self.ordre("Input.dispatchMouseEvent", type="mouseReleased", **commun)


async def _clic_sur_source(adresse_de_chrome: str, serveur: str, appui_s: float, attente_s: float = 2.6) -> dict:
    import websockets

    async with websockets.connect(adresse_de_chrome, max_size=None) as ws:
        pilote = Pilote(ws)
        await pilote.ouvrir(f"{serveur}/clinique/medecin?badge=medecin-exemple")
        await asyncio.sleep(attente_s)  # par défaut : la page s'est déjà rafraîchie une fois toute seule
        point = await pilote.milieu_du_lien("Source : Fiche du séjour")
        await pilote.cliquer(point, appui_s)
        for _ in range(50):
            if "/clinique/medecin/source" in (await pilote.lire("location.href")):
                break
            await asyncio.sleep(0.1)
        return {"adresse": await pilote.lire("location.href"), "texte": await pilote.lire("document.body.innerText")}


def test_un_clic_court_sur_source_ouvre_le_document(serveur, chrome):
    vu = asyncio.run(_clic_sur_source(chrome, serveur, appui_s=0.08))
    assert "/clinique/medecin/source" in vu["adresse"] and "ref=sejour" in vu["adresse"], vu["adresse"]
    assert "Fiche du séjour" in vu["texte"] and "Madame Giulia B." in vu["texte"] and "DONNÉES INVENTÉES" in vu["texte"]


def test_un_clic_lent_pendant_que_la_page_se_rafraichit_ouvre_aussi_le_document(serveur, chrome):
    """Le doigt reste appuyé 2,4 secondes : la page se rafraîchit au moins une fois pendant ce temps."""
    vu = asyncio.run(_clic_sur_source(chrome, serveur, appui_s=2.4))
    assert "/clinique/medecin/source" in vu["adresse"], f"le clic s'est perdu : la page est restée sur {vu['adresse']}"


def test_un_clic_lent_des_l_ouverture_de_la_page_ouvre_aussi_le_document(serveur, chrome):
    """Le doigt appuie une demi-seconde après l'ouverture et reste 2,4 secondes : le tout premier rafraîchissement tombe dedans."""
    vu = asyncio.run(_clic_sur_source(chrome, serveur, appui_s=2.4, attente_s=0.5))
    assert "/clinique/medecin/source" in vu["adresse"], f"le clic s'est perdu : la page est restée sur {vu['adresse']}"


def test_la_page_continue_de_se_mettre_a_jour_toute_seule(serveur, chrome):
    import websockets

    async def regarder() -> list[str]:
        async with websockets.connect(chrome, max_size=None) as ws:
            pilote = Pilote(ws)
            await pilote.ouvrir(f"{serveur}/clinique/medecin?badge=medecin-exemple")
            ages = []
            for _ in range(8):
                await asyncio.sleep(0.6)
                ages.append(await pilote.lire("document.getElementById('age').textContent"))
            return ages

    ages = asyncio.run(regarder())
    assert any("il y a 0 seconde" in a or "il y a 1 seconde" in a for a in ages[3:]), ages  # elle se rafraîchit encore
    assert not any("vieille" in a for a in ages), ages


def test_quand_le_contenu_change_la_page_le_montre_encore(serveur, chrome):
    """La correction ne fige pas la page : une demande faite ailleurs apparaît sur l'écran du soignant sans rien toucher."""
    import websockets

    async def regarder() -> tuple[str, str]:
        async with websockets.connect(chrome, max_size=None) as ws:
            pilote = Pilote(ws)
            await pilote.ouvrir(f"{serveur}/clinique/soignant?badge=soignant-etage-2")
            await asyncio.sleep(2.5)
            avant = await pilote.lire("document.getElementById('contenu').innerText")
            reponse = httpx.post(f"{serveur}/api/clinique/demande", headers={"origin": serveur},
                                 json={"badge": "soignant-etage-2", "patient": "p01", "texte": "la couverture"})
            assert reponse.status_code == 200, reponse.text
            for _ in range(50):
                apres = await pilote.lire("document.getElementById('contenu').innerText")
                if "Demandes (1)" in apres:
                    break
                await asyncio.sleep(0.1)
            return avant, apres

    avant, apres = asyncio.run(regarder())
    assert "Demandes (1)" not in avant and "Demandes (1)" in apres and "couverture → Chambre 12" in apres.split("Demandes (1)")[1][:200]

