"""La clinique en boîte — H10b, le mode interprète sur l'écran de régie (message de Hiba, 12.11.2026).

« 1. Un bouton « Interprète » sur l'écran de régie. Tant qu'il est tenu, la boîte écoute. Quand on le relâche, elle
traduit la phrase en anglais, la dit, et l'affiche en grand. 2. L'écran porte l'étiquette « TRADUCTION AUTOMATIQUE EN
DIRECT ». […] 5. Un deuxième bouton affiche la version anglaise préparée d'une réponse, avec l'étiquette « TRADUCTION
PRÉPARÉE ». […] 6. Rien ne sort de l'ordinateur. »
« Fini » veut dire :
- la page de régie a le bouton à tenir, l'anglais en grand, les deux étiquettes, et les réponses préparées ;
- un son envoyé par le bouton passe par l'écoute, la traduction, les contrôles et la voix ; le délai de chaque phrase est
  noté dans un fichier, et les erreurs sont comptées telles quelles, à l'écran ;
- si le cerveau ne tourne pas, la page le dit et rien n'est dit à voix haute ; les réponses préparées marchent quand même ;
- un son qui n'en est pas un, trop court ou trop gros, est refusé ; d'un autre ordinateur, il faut le code d'équipe ;
- dans un vrai navigateur, avec un faux micro : tenir le bouton, le relâcher, et l'anglais s'affiche en grand.
Ces essais prennent de fausses pièces d'écoute, de traduction et de voix : ni modèle, ni haut-parleur.
"""
from __future__ import annotations

import asyncio
import html
import io
import json
import re
import wave
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import interprete, interprete_ecran
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

CODE = {"X-Code-Equipe": "code-d-essai"}
WAV = {"Content-Type": "audio/wav"}


def _wav(secondes: float = 1.0, hz: int = 16000) -> bytes:
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as son:
        son.setnchannels(1)
        son.setsampwidth(2)
        son.setframerate(hz)
        son.writeframes(b"\x00\x01" * int(hz * secondes))
    return tampon.getvalue()


def _clinique(tmp_path, francais="Le soignant demande une course.", anglais="The caregiver asks for an errand.", pret=True):
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge), code_equipe="code-d-essai")
    dites, recus = [], []

    def ecouter(son, langue):
        recus.append(Path(son).read_bytes())
        return {"texte": francais}

    clinique.interprete = interprete_ecran.Interprete(
        tmp_path, ecouter=ecouter, traduire=lambda fr, mots: anglais, dire=lambda texte, langue, sortie: dites.append((texte, langue)),
        pret=lambda: (pret, "" if pret else "le cerveau ne tourne pas"))
    return TestClient(app), clinique, dites, recus


def test_la_page_de_regie_a_le_bouton_a_tenir_l_anglais_en_grand_et_les_deux_etiquettes(tmp_path):
    client, *_ = _clinique(tmp_path)
    brut = client.get("/clinique/regie")
    page = html.unescape(brut.text)
    assert brut.status_code == 200 and "DONNÉES INVENTÉES" in page
    assert "id='interprete'" in brut.text and "Interprète" in page and "id='anglais'" in brut.text
    assert "TRADUCTION AUTOMATIQUE EN DIRECT" in page and "TRADUCTION PRÉPARÉE" in page
    assert "Tenir le bouton" in page and "interprete_mots.yaml" in page and "interprete_reponses.yaml" in page
    for reponse in interprete.reponses_preparees():
        assert reponse["titre"] in page and f"data-preparee=\"{reponse['id']}\"" in brut.text
    assert re.findall(r"https?://", brut.text) == []  # rien ne sort : la page n'appelle aucune adresse extérieure
    assert "/clinique/regie" in client.get("/clinique").text
    assert "id='erreurs' hidden" in brut.text  # la zone des erreurs ne se montre que s'il y en a (vu dans le navigateur, N01c)


def test_un_son_envoye_par_le_bouton_sort_en_anglais_il_est_dit_et_son_delai_est_note(tmp_path):
    client, clinique, dites, recus = _clinique(tmp_path)
    r = client.post("/api/clinique/interprete/phrase", content=_wav(1.2), headers={**CODE, **WAV})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["etiquette"] == "TRADUCTION AUTOMATIQUE EN DIRECT" and d["numero"] == 1
    assert d["fr"] == "Le soignant demande une course." and d["en"] == "The caregiver asks for an errand." and d["erreurs"] == []
    assert all(isinstance(d[cle], int) for cle in ("ecoute_ms", "traduction_ms", "voix_ms", "total_ms"))
    assert dites == [("The caregiver asks for an errand.", "en")] and recus[0][:4] == b"RIFF"
    lignes = [json.loads(l) for l in clinique.interprete.fichier.read_text(encoding="utf-8").splitlines()]
    assert len(lignes) == 1 and lignes[0]["total_ms"] == d["total_ms"] and lignes[0]["en"] == d["en"] and lignes[0]["quand"]
    page = html.unescape(client.get("/clinique/regie").text)
    assert "The caregiver asks for an errand." in page and "1 phrase, 0 erreur comptée" in page


def test_les_erreurs_sont_comptees_telles_quelles_a_l_ecran(tmp_path):
    client, clinique, dites, _ = _clinique(tmp_path, anglais="The nurse asks for a race.")
    d = client.post("/api/clinique/interprete/phrase", content=_wav(), headers={**CODE, **WAV}).json()
    assert d["en"] == "The nurse asks for a race." and len(d["erreurs"]) == 2  # affichée telle quelle, avec ses erreurs
    client.post("/api/clinique/interprete/phrase", content=_wav(), headers={**CODE, **WAV})
    page = html.unescape(client.get("/clinique/regie").text)
    assert "2 phrases, 4 erreurs comptées" in page and "mot fixé non respecté" in page and "The nurse asks for a race." in page


def test_si_le_cerveau_ne_tourne_pas_la_page_le_dit_et_rien_n_est_dit(tmp_path):
    client, clinique, dites, recus = _clinique(tmp_path, pret=False)
    r = client.post("/api/clinique/interprete/phrase", content=_wav(), headers={**CODE, **WAV})
    assert r.status_code == 503 and "le cerveau ne tourne pas" in r.json()["detail"]
    assert dites == [] and recus == [] and not clinique.interprete.fichier.exists()
    assert "le cerveau ne tourne pas" in html.unescape(client.get("/clinique/regie").text)
    # les réponses préparées marchent quand même
    assert client.get("/api/clinique/interprete/preparee/gardien").status_code == 200


def test_un_son_qui_n_en_est_pas_un_trop_court_ou_trop_gros_est_refuse(tmp_path):
    client, _, dites, _ = _clinique(tmp_path)
    assert client.post("/api/clinique/interprete/phrase", content=b"pas un son", headers={**CODE, **WAV}).status_code == 400
    assert client.post("/api/clinique/interprete/phrase", content=_wav(0.1), headers={**CODE, **WAV}).status_code == 400
    assert client.post("/api/clinique/interprete/phrase", content=_wav(70), headers={**CODE, **WAV}).status_code == 413
    assert dites == []


def test_d_un_autre_ordinateur_il_faut_le_code_d_equipe(tmp_path):
    client, _, dites, _ = _clinique(tmp_path)
    assert client.post("/api/clinique/interprete/phrase", content=_wav(), headers=WAV).status_code == 403
    assert dites == []


def test_le_deuxieme_bouton_rend_la_version_anglaise_preparee_avec_son_etiquette(tmp_path):
    client, *_ = _clinique(tmp_path)
    for reponse in interprete.reponses_preparees():
        d = client.get(f"/api/clinique/interprete/preparee/{reponse['id']}").json()
        assert d["etiquette"] == "TRADUCTION PRÉPARÉE" and d["en"] == reponse["en"] and d["fr"] == reponse["fr"]
    assert client.get("/api/clinique/interprete/preparee/inconnue").status_code == 404


# ---------------------------------------------------------------------------------------------- dans un vrai navigateur
FAUX_MICRO = """
navigator.mediaDevices.getUserMedia = async () => {
  const c = new (window.AudioContext || window.webkitAudioContext)();
  const o = c.createOscillator(), sortie = c.createMediaStreamDestination();
  o.connect(sortie); o.start();
  window.addEventListener('pointerdown', () => c.resume(), true);
  return sortie.stream;
};
"""

def test_dans_chrome_avec_un_faux_micro_tenir_le_bouton_puis_le_relacher_affiche_l_anglais_en_grand(tmp_path):
    """Chrome sans fenêtre, avec un FAUX micro (un son continu fabriqué dans la page) : on tient le bouton une seconde et demie par
    de vrais gestes de souris, on le relâche. Le son arrive au serveur ; l'anglais (rendu ici par de fausses pièces)
    s'affiche en grand, avec l'étiquette. Ce n'est pas une personne qui parle."""
    import socket
    import subprocess
    import threading
    import time

    import httpx
    import uvicorn
    import websockets

    from briques.clinique.tests.test_clic_dans_le_navigateur import CHROME, Pilote

    if not CHROME.exists():
        pytest.skip("Chrome n'est pas sur cet ordinateur : le bouton n'est pas essayé dans un navigateur")

    def port_libre() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    horloge, app = HorlogeDeDemonstration(), FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge, carnet=Carnet(horloge=horloge))
    recus: list[bytes] = []

    def ecouter(son, langue):
        recus.append(Path(son).read_bytes())
        return {"texte": "La boîte marche sans Internet."}

    clinique.interprete = interprete_ecran.Interprete(tmp_path / "sons", ecouter=ecouter, traduire=lambda fr, mots: "The box works without the Internet.",
                                                      dire=lambda *a: None, pret=lambda: (True, ""))
    port, port_chrome = port_libre(), port_libre()
    service = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=service.run, daemon=True)
    fil.start()
    chrome = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--window-size=1200,900",
                               "--autoplay-policy=no-user-gesture-required",
                               f"--remote-debugging-port={port_chrome}", f"--user-data-dir={tmp_path / 'profil'}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        adresse = None
        for _ in range(100):
            try:
                pages = [p for p in httpx.get(f"http://127.0.0.1:{port_chrome}/json", timeout=0.5).json() if p.get("type") == "page"]
                if pages:
                    adresse = pages[0]["webSocketDebuggerUrl"]
                    break
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.1)
        if adresse is None:
            pytest.skip("Chrome ne s'ouvre pas avec sa porte de pilotage sur cet ordinateur")

        async def jouer() -> dict:
            async with websockets.connect(adresse, max_size=None) as ws:
                pilote = Pilote(ws)
                # Chrome sans fenêtre ne répond pas à la demande de micro sur cet ordinateur (essayé : elle reste sans réponse).
                # Le faux micro est donc fabriqué dans la page : un son continu, donné à la place du micro.
                await pilote.ordre("Page.enable")
                await pilote.ordre("Page.addScriptToEvaluateOnNewDocument", source=FAUX_MICRO)
                await pilote.ouvrir(f"http://127.0.0.1:{port}/clinique/regie")
                for _ in range(50):  # la page dit « Micro prêt » quand le navigateur lui a donné le micro
                    if "Micro prêt" in (await pilote.lire("document.getElementById('etat').innerText") or ""):
                        break
                    await asyncio.sleep(0.1)
                point = await pilote.lire("(() => { const r = document.getElementById('interprete').getBoundingClientRect();"
                                          " return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()")
                await pilote.cliquer(point, appui_s=1.5)  # le bouton est TENU une seconde et demie, puis relâché
                for _ in range(100):
                    if "The box works" in (await pilote.lire("document.getElementById('anglais').innerText") or ""):
                        break
                    await asyncio.sleep(0.1)
                return {"anglais": await pilote.lire("document.getElementById('anglais').innerText"),
                        "etiquette": await pilote.lire("document.getElementById('etiquette').innerText"),
                        "etat": await pilote.lire("document.getElementById('etat').innerText"),
                        "taille": await pilote.lire("parseFloat(getComputedStyle(document.getElementById('anglais')).fontSize)")}

        vu = asyncio.run(jouer())
    finally:
        chrome.terminate()
        service.should_exit = True
        fil.join(timeout=5)
    assert vu["anglais"] == "The box works without the Internet.", vu
    assert vu["etiquette"] == "TRADUCTION AUTOMATIQUE EN DIRECT" and vu["taille"] >= 36  # affiché en grand
    assert len(recus) == 1
    with wave.open(io.BytesIO(recus[0])) as son:  # ce que le bouton a envoyé : un vrai son, une seule voie, 16 000 points par seconde
        assert son.getnchannels() == 1 and son.getframerate() == 16000 and son.getsampwidth() == 2
        assert 0.8 <= son.getnframes() / 16000 <= 3.0
