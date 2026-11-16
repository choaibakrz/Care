"""K07b — La taille du texte des écrans Invité et Patient, mesurée dans un vrai navigateur (avenant 2, K07).

« Lisible par une personne âgée : de gros caractères, un fort contraste, une idée par ligne. Une vérification mesure la
plus petite taille de texte de ces deux écrans, et la compare à un seuil écrit dans les réglages. »
La mesure : Chrome ouvre la page, et pour chaque texte visible on lit la taille que le navigateur a calculée.
Ce n'est pas un avis de lisibilité : le contraste et « une idée par ligne » ne sont pas mesurés ici.
"""
from __future__ import annotations

import json
from typing import Any

ECRANS = {"Invité": "/clinique/invite", "Patient": "/clinique/patient?badge=patient-p01"}

MESURE_JS = """(() => { const vus = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
 while (w.nextNode()) { const n = w.currentNode; const t = n.textContent.trim(); if (!t) continue; const e = n.parentElement;
  if (!e || ['SCRIPT', 'STYLE'].includes(e.tagName)) continue;
  const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') continue;
  const r = e.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
  vus.push([parseFloat(s.fontSize), e.tagName.toLowerCase() + (e.className ? '.' + e.className : ''), t.slice(0, 40)]); }
 vus.sort((a, b) => a[0] - b[0]); return {textes: vus.length, petits: vus.slice(0, 5)}; })()"""


def seuil_px() -> float:
    """Le seuil, lu dans les réglages (ecran.taille_texte_min_px). Absent de reglages.yaml : celui de reglages.exemple.yaml."""
    from commun.systeme import REGLAGES_EXEMPLE, charger_reglages

    valeur = (charger_reglages().get("ecran") or {}).get("taille_texte_min_px")
    if valeur is None:
        valeur = charger_reglages(REGLAGES_EXEMPLE)["ecran"]["taille_texte_min_px"]
    return float(valeur)


async def mesurer(adresse_de_chrome: str, url: str) -> dict[str, Any]:
    """Ouvre `url` dans Chrome (par sa porte de pilotage) et rend la plus petite taille de texte visible, en px."""
    import asyncio

    import websockets

    async with websockets.connect(adresse_de_chrome, max_size=None) as ws:
        n = 0

        async def ordre(methode: str, **parametres):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": methode, "params": parametres}))
            while True:
                reponse = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                if reponse.get("id") == n:
                    return reponse.get("result", {})

        await ordre("Page.enable")
        await ordre("Page.navigate", url=url)
        for _ in range(100):
            etat = await ordre("Runtime.evaluate", expression="document.readyState + '|' + location.href", returnByValue=True)
            if etat["result"].get("value") == f"complete|{url}":
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.6)  # le premier rafraîchissement de la page
        lu = (await ordre("Runtime.evaluate", expression=MESURE_JS, returnByValue=True))["result"]["value"]
    petits = lu["petits"]
    return {"url": url, "textes": lu["textes"], "plus_petite_px": petits[0][0] if petits else None, "les_plus_petits": petits}
