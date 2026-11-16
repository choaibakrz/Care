"""Le passage des pages dans un vrai navigateur, fait par un programme (tâches N01 et N02, message de Hiba du 12.11.2026).

    .venv/bin/python outils/pages_vues_chrome.py DOSSIER_DES_IMAGES [--sans-boutons]

Il lance le serveur d'essai (`outils/serveur_pages_vues.py` : cet ordinateur seulement, faux robot, fichiers provisoires),
ouvre Chrome sans fenêtre, et pour chaque page de la liste :
1. l'ouvre en grand écran (1440 points) : la page répond-elle, le bandeau « DONNÉES INVENTÉES » est-il là, le navigateur
   signale-t-il une erreur ; une image est gardée ;
2. l'ouvre en largeur de téléphone (375 points) : quelque chose dépasse-t-il à droite ;
3. appuie une fois sur chaque bouton, par un vrai geste de souris, et note ce que la page dit ensuite, et si le navigateur
   signale une erreur. Tout s'écrit dans des fichiers provisoires : jamais dans les vrais fichiers de l'équipe.
Pour l'écran de l'ossature : regarder seulement, aucun bouton.
Ce n'est pas « vu par un humain sur un vrai téléphone » : c'est un programme qui pilote Chrome sur cet ordinateur.
Rien n'est installé : Chrome et le paquet `websockets` sont déjà là. Sans Chrome : le programme le dit et s'arrête.
"""
from __future__ import annotations

import asyncio
import base64
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

RACINE = Path(__file__).resolve().parents[1]
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
BANDEAU = "DONNÉES INVENTÉES"
# nom court → adresse. « @lien:TEXTE » : suivre, depuis la page d'avant, le premier lien dont l'adresse contient TEXTE.
PAGES = [
    ("liste_de_soin", "/clinique/soignant/liste?badge=soignant-etage-2&patient=p01&liste=installation"),
    ("fin_de_poste", "/clinique/soignant/fin-de-poste?badge=soignant-etage-2"),
    ("pauses", "/clinique/soignant/pauses?badge=soignant-etage-2"),
    ("soir_du_patient", "/clinique/patient/soir?badge=patient-p01"),
    ("qui_decide", "/clinique/qui-decide"),
    ("sources", "/clinique/sources"),
    ("pre_admission", "/clinique/pre-admission?badge=accueil"),
    ("faux_logiciel", "/faux-logiciel"),
    ("faux_logiciel_fiche", "@lien:/faux-logiciel/fiche"),
    ("tirage", "/clinique/tirage"),
    ("aide_humaine", "/clinique/aide-humaine"),
    ("essais_reels", "/clinique/essais-reels"),
    ("protocole_essais_reels", "/clinique/protocole-essais-reels"),
    ("etageres", "/clinique/etageres"),
    ("epreuve_etageres", "/clinique/epreuve-etageres"),
    ("pannes", "/clinique/pannes"),
    ("moments", "/clinique/moments"),
    ("ce_qu_on_nous_a_dit", "/clinique/ce-qu-on-nous-a-dit"),
    ("regie", "/clinique/regie"),
    ("pourquoi", "@lien:/clinique/pourquoi"),
    ("ossature", "/"),
]
# N02 (dernier passage) : les dix écrans principaux de N01a, les pages de N01c, et celles faites après N01 (tours 80 à 99).
PAGES_N02 = [
    ("liste_des_ecrans", "/clinique"), ("patient_fr", "/clinique/patient?langue=fr"), ("patient_de", "/clinique/patient?langue=de"),
    ("patient_it", "/clinique/patient?langue=it"), ("patient_en", "/clinique/patient?langue=en"),
    ("soignant", "/clinique/soignant?badge=soignant-etage-2"), ("medecin", "/clinique/medecin?badge=medecin-exemple"),
    ("medecin_source", "@lien:/clinique/medecin/source"), ("accueil", "/clinique/accueil"), ("accueil_papiers", "/clinique/accueil/papiers?badge=accueil"),
    ("therapeute", "/clinique/therapeute"), ("direction", "/clinique/direction"), ("hall", "/clinique/hall"),
    ("flotte", "/clinique/flotte"), ("journal", "/clinique/journal"),
] + PAGES + [
    ("tableau_de_flotte", "/clinique/tableau-de-flotte"), ("fiche_de_verite", "/clinique/fiche-de-verite"),
    ("invite", "/clinique/invite"), ("telephones", "/clinique/telephones"), ("preuves", "/clinique/preuves"),
    ("preuves_essais", "/clinique/preuves/essais"), ("preuves_brancher", "/clinique/preuves/brancher"),
    ("ou_tourne_quoi", "/clinique/ou-tourne-quoi"), ("capacites", "/clinique/capacites"), ("concours", "/clinique/concours"),
    ("avis", "/clinique/avis"), ("avis_donner", "/clinique/avis/donner"),
]
SANS_BOUTONS = {"ossature"}  # regarder, noter, ne rien toucher
BOUTONS_LAISSES = {"interprete"}  # le bouton du micro : pas de micro dans Chrome sans fenêtre
PLUS_DE_BOUTONS = 8


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Pilote:
    """La porte de pilotage de Chrome : des ordres, et les erreurs que le navigateur signale pendant ce temps."""

    def __init__(self, ws) -> None:
        self.ws, self.n, self.erreurs, self.fenetres = ws, 0, [], []

    def _noter(self, message: dict) -> None:
        if message.get("method") == "Runtime.exceptionThrown":
            d = message["params"]["exceptionDetails"]
            self.erreurs.append("erreur du programme de la page : " + str(d.get("exception", {}).get("description") or d.get("text"))[:160])
        elif message.get("method") == "Log.entryAdded" and message["params"]["entry"].get("level") == "error":
            e = message["params"]["entry"]
            self.erreurs.append(f"{e.get('text', '')[:120]} ({e.get('url', '')[-60:]})")

    async def ordre(self, methode: str, **parametres):
        self.n += 1
        attendu = self.n
        await self.ws.send(json.dumps({"id": attendu, "method": methode, "params": parametres}))
        while True:
            message = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=30))
            if message.get("id") == attendu:
                if "error" in message:
                    raise RuntimeError(f"{methode} : {message['error']}")
                return message.get("result", {})
            await self._fenetre(message)
            self._noter(message)

    async def _fenetre(self, message: dict) -> None:
        """Une fenêtre de question du navigateur (« Êtes-vous sûr ? ») bloque tout : on répond oui, et on le note."""
        if message.get("method") == "Page.javascriptDialogOpening":
            self.fenetres.append(f"{message['params'].get('type')} : {message['params'].get('message', '')[:120]}")
            self.n += 1
            await self.ws.send(json.dumps({"id": self.n, "method": "Page.handleJavaScriptDialog", "params": {"accept": True}}))

    async def lire(self, expression: str):
        rendu = await self.ordre("Runtime.evaluate", expression=expression, returnByValue=True)
        return rendu["result"].get("value")

    async def attendre(self, secondes: float) -> None:
        """Attendre, en gardant les erreurs que le navigateur signale pendant ce temps."""
        fin = time.monotonic() + secondes
        while time.monotonic() < fin:
            try:
                message = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=max(0.05, fin - time.monotonic())))
            except asyncio.TimeoutError:
                return
            await self._fenetre(message)
            self._noter(message)

    async def taille(self, largeur: int, hauteur: int, telephone: bool) -> None:
        await self.ordre("Emulation.setDeviceMetricsOverride", width=largeur, height=hauteur, deviceScaleFactor=1, mobile=telephone)

    async def ouvrir(self, adresse: str) -> None:
        await self.ordre("Page.navigate", url=adresse)
        for _ in range(80):
            if await self.lire("document.readyState") == "complete":
                break
            await self.attendre(0.1)
        await self.attendre(0.9)

    async def image(self, fichier: Path) -> None:
        rendu = await self.ordre("Page.captureScreenshot", format="png")
        fichier.write_bytes(base64.b64decode(rendu["data"]))

    async def cliquer(self, x: float, y: float) -> None:
        commun = {"x": x, "y": y, "button": "left", "clickCount": 1}
        await self.ordre("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        await self.ordre("Input.dispatchMouseEvent", type="mousePressed", **commun)
        await self.attendre(0.08)
        await self.ordre("Input.dispatchMouseEvent", type="mouseReleased", **commun)


DEPASSE = """(() => { const l = innerWidth; const d = [...document.querySelectorAll('body *')].filter(e => {
  const r = e.getBoundingClientRect(); return r.width > 0 && r.right > l + 1; });
  return {largeur: l, page: document.documentElement.scrollWidth, depassent: d.length,
          exemple: d.slice(0, 2).map(e => e.tagName + ' ' + (e.textContent || '').trim().slice(0, 40))}; })()"""
BOUTONS = """(() => [...document.querySelectorAll('button')].map((b, i) => { const r = b.getBoundingClientRect();
  return {i, id: b.id, texte: (b.textContent || '').trim().slice(0, 40), visible: r.width > 0 && r.height > 0 && !b.disabled}; }))()"""
CE_QUE_LA_PAGE_DIT = """(() => { const z = document.querySelector('#dit, #etat, [role=status]');
  return {adresse: location.pathname + location.search, dit: z ? (z.textContent || '').trim().slice(0, 140) : null,
          texte: document.body.innerText.length}; })()"""


async def passer(base: str, adresse_de_chrome: str, dossier: Path, avec_boutons: bool, pages: list | None = None) -> list[dict]:
    import websockets

    vues = []
    async with websockets.connect(adresse_de_chrome, max_size=None) as ws:
        p = Pilote(ws)
        for domaine in ("Page", "Runtime", "Log"):
            await p.ordre(f"{domaine}.enable")
        precedente = base + "/clinique"
        for nom, chemin in (pages or PAGES):
            vue: dict = {"nom": nom, "boutons": []}
            await p.taille(1440, 1000, False)
            if chemin.startswith("@lien:"):
                await p.ouvrir(precedente)
                cible = await p.lire("(() => { const a = [...document.querySelectorAll('a')].find(a => a.getAttribute('href') && "
                                     f"a.getAttribute('href').includes({json.dumps(chemin[6:])})); return a ? a.href : null; }})()")
                if not cible:
                    vues.append({**vue, "adresse": chemin, "ouverte": False, "note": "aucun lien vers cette page depuis la page d'avant"})
                    continue
                adresse = cible
            else:
                adresse = base + chemin
            p.erreurs = []
            await p.ouvrir(adresse)
            vue.update(adresse=adresse.replace(base, ""), ouverte=True, titre=await p.lire("document.title"),
                       bandeau=BANDEAU in (await p.lire("document.body.innerText") or ""),
                       refus="Accès refusé" in (await p.lire("document.body.innerText") or ""))
            await p.image(dossier / f"{nom}_grand_ecran_1440.png")
            vue["erreurs"] = list(dict.fromkeys(p.erreurs))
            await p.taille(375, 812, True)
            await p.ouvrir(adresse)
            vue["telephone"] = await p.lire(DEPASSE)
            await p.image(dossier / f"{nom}_telephone_375.png")
            await p.taille(1440, 1000, False)
            if avec_boutons and nom not in SANS_BOUTONS:
                await p.ouvrir(adresse)
                boutons = [b for b in (await p.lire(BOUTONS) or []) if b["visible"] and b["id"] not in BOUTONS_LAISSES]
                vue["boutons_en_tout"] = len(boutons)
                for b in boutons[:PLUS_DE_BOUTONS]:
                    await p.ouvrir(adresse)  # chaque bouton est pressé sur une page fraîche
                    p.erreurs, p.fenetres = [], []
                    point = await p.lire(f"(() => {{ const b = document.querySelectorAll('button')[{b['i']}]; if (!b) return null; "
                                         "b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect(); "
                                         "return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()")
                    if not point:
                        vue["boutons"].append({"texte": b["texte"], "note": "le bouton n'est plus là"})
                        continue
                    try:
                        await p.cliquer(point["x"], point["y"])
                        await p.attendre(1.2)
                        apres = await p.lire(CE_QUE_LA_PAGE_DIT) or {}
                    except (TimeoutError, asyncio.TimeoutError, RuntimeError) as bloque:
                        vue["boutons"].append({"texte": b["texte"], "note": f"le navigateur n'a pas répondu ({type(bloque).__name__})"})
                        continue
                    vue["boutons"].append({"texte": b["texte"], "dit": apres.get("dit"), "adresse": apres.get("adresse"),
                                           "erreurs": list(dict.fromkeys(p.erreurs)), "fenetres": list(p.fenetres)})
            if not chemin.startswith("@lien:"):
                precedente = adresse
            vues.append(vue)
            print(f"  {nom} : {'ouverte' if vue['ouverte'] else 'PAS OUVERTE'} ; bandeau {'oui' if vue.get('bandeau') else 'NON'} ; "
                  f"dépasse en 375 : {vue['telephone']['depassent']} ; boutons pressés : {len(vue['boutons'])} ; "
                  f"erreurs : {len(vue['erreurs']) + sum(len(b.get('erreurs', [])) for b in vue['boutons'])}", flush=True)
    return vues


def main() -> int:
    if not CHROME.exists():
        print("Chrome n'est pas sur cet ordinateur : rien n'est passé (rien à installer).")
        return 2
    n02 = "--n02" in sys.argv
    dossier = (Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--")
               else RACINE / "pages_vues" / ("n02" if n02 else "passage"))
    dossier.mkdir(parents=True, exist_ok=True)
    port, port_chrome = port_libre(), port_libre()
    serveur = subprocess.Popen([sys.executable, str(RACINE / "outils" / "serveur_pages_vues.py"), str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=RACINE)
    chrome = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                               f"--remote-debugging-port={port_chrome}", f"--user-data-dir={tempfile.mkdtemp(prefix='chrome-pages-')}",
                               "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base, adresse = f"http://127.0.0.1:{port}", None
        for _ in range(150):
            try:
                if httpx.get(base + "/clinique", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        for _ in range(100):
            try:
                pages = [x for x in httpx.get(f"http://127.0.0.1:{port_chrome}/json", timeout=0.5).json() if x.get("type") == "page"]
                if pages:
                    adresse = pages[0]["webSocketDebuggerUrl"]
                    break
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.1)
        if adresse is None:
            print("Chrome ne s'ouvre pas avec sa porte de pilotage : rien n'est passé.")
            return 2
        vues = asyncio.run(passer(base, adresse, dossier, "--sans-boutons" not in sys.argv, PAGES_N02 if n02 else None))
    finally:
        chrome.terminate()
        serveur.terminate()
    (dossier / "passage.json").write_text(json.dumps(vues, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(vues)} pages passées ; le détail : {dossier / 'passage.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
