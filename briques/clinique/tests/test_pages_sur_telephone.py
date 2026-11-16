"""La clinique en boîte — N01, les pages en largeur de téléphone, mesurées par un vrai navigateur (message de Hiba du 12.11.2026).

Au premier passage (N01a), le tableau de la page Direction et celui du journal des accès étaient coupés à droite sur un
téléphone. Cette vérification l'aurait vu : elle ouvre les vraies pages dans Chrome (sans fenêtre), chacune dans un cadre
large de 375 points, et compte ce qui dépasse à droite. Aucun texte ne doit être coupé, dans aucune des quatre langues.

Sans Chrome sur l'ordinateur, l'essai est sauté (on n'installe rien pour lui). Ce n'est pas « vu par un humain sur un vrai
téléphone » : c'est une mesure faite par un navigateur, sur cet ordinateur.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from briques.clinique import ecrans
from briques.clinique.carnet import Carnet
from briques.clinique.ecrans import brancher_ecrans
from briques.clinique.horloge import HorlogeDeDemonstration
from briques.clinique.porte import JournalDesAcces, PorteDeLecture

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
LARGEUR = 375
PAGES = ["/clinique", "/clinique/patient?langue=fr", "/clinique/patient?langue=de", "/clinique/patient?langue=it",
         "/clinique/patient?langue=en", "/clinique/soignant?badge=soignant-etage-2&langue=fr",
         "/clinique/soignant?badge=soignant-etage-2&langue=de", "/clinique/medecin?langue=fr", "/clinique/medecin?langue=de",
         "/clinique/accueil", "/clinique/therapeute", "/clinique/direction", "/clinique/hall", "/clinique/flotte", "/clinique/journal",
         # N01b (tour 75) : les pages du médecin et les papiers de l'accueil
         "/clinique/medecin/source?badge=medecin-exemple&patient=p01&ref=sejour",
         "/clinique/medecin/source?badge=medecin-exemple&patient=p01&ref=p01-d1",
         "/clinique/medecin/recherche?badge=medecin-exemple&q=la lettre du médecin de Madame B.",
         "/clinique/medecin/recherche?badge=medecin-exemple&q=le dernier rapport de radiologie de Madame B.",
         "/clinique/medecin/dictee?badge=medecin-exemple&patient=p01", "/clinique/accueil/papiers?badge=accueil",
         # N01c (tour 78) : les pages de travail (le faux logiciel et les moments demandent le code d'équipe ici : mesuré par outils/pages_vues_chrome.py)
         "/clinique/soignant/liste?badge=soignant-etage-2&patient=p01&liste=installation",
         "/clinique/soignant/fin-de-poste?badge=soignant-etage-2", "/clinique/soignant/pauses?badge=soignant-etage-2",
         "/clinique/patient/soir?badge=patient-p01", "/clinique/qui-decide", "/clinique/sources",
         "/clinique/pre-admission?badge=accueil", "/clinique/tirage", "/clinique/aide-humaine",
         "/clinique/essais-reels", "/clinique/protocole-essais-reels", "/clinique/etageres", "/clinique/epreuve-etageres",
         "/clinique/pannes", "/clinique/ce-qu-on-nous-a-dit", "/clinique/regie"]
MESURE = """<script>
addEventListener('load', () => setTimeout(() => {
  const vus = {};
  for (const cadre of document.querySelectorAll('iframe')) {
    const d = cadre.contentDocument, largeur = cadre.contentWindow.innerWidth;
    const depassent = [...d.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > largeur + 1; });
    vus[cadre.dataset.page] = {largeur, page: d.documentElement.scrollWidth, depassent: depassent.length,
                               exemple: depassent.slice(0, 2).map(e => e.tagName + ' ' + (e.textContent || '').trim().slice(0, 30))};
  }
  document.body.setAttribute('data-mesure', JSON.stringify(vus));
}, 300));
</script>"""

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Chrome n'est pas sur cet ordinateur : les pages ne sont pas mesurées (rien à installer)")


def _mesurer(pages: dict[str, str], dossier: Path) -> dict[str, dict]:
    """Ouvre les pages dans Chrome, sans fenêtre, chacune dans un cadre de 375 points. Rend ce qui dépasse, par page."""
    cadres = "".join(f"<iframe data-page=\"{html.escape(nom)}\" width=\"{LARGEUR}\" height=\"812\" srcdoc=\"{html.escape(texte)}\"></iframe>"
                     for nom, texte in pages.items())
    fichier = dossier / "pages.html"
    fichier.write_text(f"<!doctype html><html><body>{cadres}{MESURE}</body></html>", encoding="utf-8")
    sortie = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={dossier / 'profil'}",
                             "--virtual-time-budget=4000", "--dump-dom", fichier.as_uri()], capture_output=True, text=True, timeout=90)
    trouve = re.search(r'data-mesure="([^"]*)"', sortie.stdout)
    assert trouve, sortie.stderr[-400:]
    return json.loads(html.unescape(trouve.group(1)))


@pytest.fixture(scope="module")
def client():
    horloge, app = HorlogeDeDemonstration(), FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge), code_equipe="")
    return TestClient(app)


def test_aucun_texte_ne_depasse_en_largeur_de_telephone_dans_les_quatre_langues(client, tmp_path):
    pages = {}
    for chemin in PAGES:  # le journal des accès est demandé en dernier : il a alors des lignes à montrer
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin
        pages[chemin] = reponse.text
    mesures = _mesurer(pages, tmp_path)
    assert set(mesures) == set(PAGES)
    for chemin, m in mesures.items():
        assert m["largeur"] == LARGEUR, (chemin, m)
        assert m["depassent"] == 0 and m["page"] <= LARGEUR, (chemin, m)


def test_la_mesure_sait_voir_un_tableau_coupe(client, tmp_path, monkeypatch):
    """Sans la règle de style pour les petits écrans (l'état d'avant N01a), le tableau de la Direction dépasse."""
    regle = re.search(r"@media \(max-width:600px\)\{table\{[^}]*\}td,th\{[^}]*\}\}", ecrans.STYLE)
    assert regle, "la règle de style des tableaux sur petit écran a disparu"
    avec = client.get("/clinique/direction").text
    sans = avec.replace(regle.group(0), "")
    assert sans != avec
    mesures = _mesurer({"avec": avec, "sans": sans}, tmp_path)
    assert mesures["avec"]["depassent"] == 0
    assert mesures["sans"]["depassent"] > 0 and "TABLE" in " ".join(mesures["sans"]["exemple"])
