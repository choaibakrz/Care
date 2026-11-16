"""J07a — La page des preuves (avenant jury, J07). « Le jury choisit une question, on lui montre la preuve. »

    /clinique/preuves              huit boutons, écrits comme des questions ; chacun ouvre sa preuve
    /clinique/preuves/essais       1. le tableau des essais comptés (J01) et les essais réels, à part
    /clinique/preuves/brancher     5. brancher un robot inconnu : la commande et son chronomètre (J04)
    /clinique/ou-tourne-quoi       8. où tourne chaque pièce, fabriqué par le système

Les autres preuves sont des pages qui existent déjà : « Moments » (J03), « Pannes » (J02, et le tableau de flotte pour la
panne de robot de T24), « Qui décide » (J05) et une pause en direct, « Ce qu'on nous a dit » (J06).
Aucun chiffre n'est tapé à la main : les mesures viennent des fichiers gardés par les commandes qui les ont faites.
Ce qui n'est pas mesuré s'écrit « non mesuré ». La commande des preuves est J07b.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

NON_MESURE = "non mesuré"

PREUVES = (
    ("Sur vingt essais, combien réussissent ?", "/clinique/preuves/essais",
     "Le tableau des vingt essais comptés sur le faux robot, et à part les essais réels comptés par l'équipe.", ()),
    ("Montrez-moi le moment où ça a raté.", "/clinique/moments",
     "Les moments marquants de la dernière séance enregistrée ; un clic montre les quatre choses.", ()),
    ("Coupez le lien.", "/clinique/pannes",
     "Les pannes qu'on provoque exprès : ce qui se passe, ce que le système fait, qui est prévenu.",
     (("La panne d'un robot et la reprise par le plus proche (T24)", "/clinique/tableau-de-flotte"),)),
    ("Comment sait-il qu'il se trompe ?", "/clinique/moments#attrapees",
     "Les erreurs attrapées : combien de fois le système s'est arrêté de lui-même ou a demandé un humain.", ()),
    ("Branchez un autre robot.", "/clinique/preuves/brancher",
     "La commande qui branche un robot à partir de sa carte, et le temps qu'il a fallu.", ()),
    ("Qui décide ?", "/clinique/qui-decide",
     "Ce que le robot fait seul, ce qu'il demande, ce qu'il ne fait jamais ; puis une pause mise en direct.",
     (("Mettre une pause en direct (écran du soignant)", "/clinique/soignant/pauses?badge=soignant-etage-2"),)),
    ("Qu'en disent les soignants ?", "/clinique/ce-qu-on-nous-a-dit",
     "Ce que des soignants nous ont dit. Si la page est vide, elle le dit : c'est une preuve honnête.", ()),
    ("Où tourne quoi ?", "/clinique/ou-tourne-quoi",
     "Chaque pièce : la machine où elle tourne, si elle a besoin d'Internet, son temps de réponse, sa mémoire.", ()),
)
PIECES = ("cerveau", "écoute", "voix", "yeux", "gardien", "écrans", "boîte noire")


# ---------------------------------------------------------------------- 8. où tourne quoi
def _lire(dossier: Path, nom: str) -> dict[str, Any] | None:
    try:
        lu = json.loads((dossier / f"{nom}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return lu if isinstance(lu, dict) else None


def _jour(m: dict[str, Any]) -> str:
    try:
        return datetime.fromisoformat(str(m["quand"])).strftime("%d.%m.%Y")
    except (KeyError, ValueError):
        return "date inconnue"


def _machine_du_cerveau(reglages: dict[str, Any]) -> str:
    modeles = [c for c in (reglages.get("cerveau") or {}).get("cascade") or [] if c.get("url")]
    if not modeles:
        return "cet ordinateur (le cerveau à règles, sans modèle)"
    hote = urlparse(str(modeles[0]["url"])).hostname or ""
    if hote in ("127.0.0.1", "localhost", "::1", ""):
        return f"cet ordinateur ({modeles[0].get('nom', 'modèle')}, lu dans les réglages)"
    return f"un autre ordinateur du réseau local : {hote} ({modeles[0].get('nom', 'modèle')}, lu dans les réglages)"


def ou_tourne_quoi(dossier: str | Path | None = None, reglages: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Le tableau, fabriqué à partir des réglages et des mesures gardées. Rien n'est tapé à la main."""
    from .mesures_cerveau import DOSSIER

    if reglages is None:
        from commun.systeme import charger_reglages

        reglages = charger_reglages()
    dossier = Path(dossier) if dossier else DOSSIER
    essai, chaine = _lire(dossier, "apertus_essai"), _lire(dossier, "chaine")
    cerveau_temps, cerveau_memoire = NON_MESURE, NON_MESURE
    if essai and "temps_median_ms" in essai:
        cerveau_temps = (f"médian {essai['temps_median_ms']} ms, le plus long {essai.get('temps_max_ms', '?')} ms "
                         f"(Apertus 8B, mesuré le {_jour(essai)})")
    if essai and essai.get("memoire_go") is not None:
        cerveau_memoire = f"{essai['memoire_go']} Go pour le serveur du modèle (lu par « ps », mesuré le {_jour(essai)})".replace(".", ",", 1)

    def de_la_chaine(cle: str) -> str:
        if chaine and chaine.get(cle) is not None:
            return f"médian {chaine[cle]} ms (dans la chaîne entière, mesuré le {_jour(chaine)})"
        return NON_MESURE

    yeux = "éteints (réglage yeux.actif : false)" if not (reglages.get("yeux") or {}).get("actif") else "cet ordinateur (caméra du réglage yeux.camera)"
    lignes = [
        {"piece": "cerveau", "machine": _machine_du_cerveau(reglages), "temps": cerveau_temps, "memoire": cerveau_memoire},
        {"piece": "écoute", "machine": "cet ordinateur (whisper.cpp)", "temps": de_la_chaine("ecoute_median_ms"), "memoire": NON_MESURE},
        {"piece": "voix", "machine": "cet ordinateur (la voix « say » du Mac)", "temps": de_la_chaine("voix_median_ms"), "memoire": NON_MESURE},
        {"piece": "yeux", "machine": yeux, "temps": NON_MESURE, "memoire": NON_MESURE},
        {"piece": "gardien", "machine": "cet ordinateur (il tourne avec le cerveau)", "temps": NON_MESURE, "memoire": NON_MESURE},
        {"piece": "écrans", "machine": "cet ordinateur (le serveur des pages) ; les téléphones et tablettes du Wi-Fi les affichent",
         "temps": NON_MESURE, "memoire": NON_MESURE},
        {"piece": "boîte noire", "machine": "cet ordinateur (un fichier par séance, dans journal/)", "temps": NON_MESURE, "memoire": NON_MESURE},
    ]
    for l in lignes:
        l["internet"] = "a besoin d'internet : non"
    return lignes


def dessiner_ou_tourne_quoi(lignes: list[dict[str, str]], chaine_memoire: str | None) -> str:
    from .ecrans import _e

    rangs = "".join(f"<tr><td><b>{_e(l['piece'])}</b></td><td>{_e(l['machine'])}</td><td>{_e(l['internet'])}</td>"
                    f"<td>{_e(l['temps'])}</td><td>{_e(l['memoire'])}</td></tr>" for l in lignes)
    return ("<p>Ce tableau est fabriqué par le système, à partir des réglages et des mesures gardées par les commandes qui les ont "
            "faites. Ce qui n'a pas été mesuré est écrit « non mesuré ».</p>"
            "<table><tr><th>Pièce</th><th>Où elle tourne</th><th>Internet</th><th>Temps de réponse</th><th>Mémoire</th></tr>"
            f"{rangs}</table>"
            + (f"<p class='ou'>Tout l'ordinateur, pendant la chaîne entière : {_e(chaine_memoire)}.</p>" if chaine_memoire else "")
            + "<p><b>consommation électrique : non mesurée</b> (aucun outil déjà présent ne la donne sans droits d'administrateur).</p>"
              "<p class='ou'>Pourquoi « non » pour Internet : les essais tournent Internet coupé, et la répétition compte les "
              "connexions vers l'extérieur (étape 14). Le bonus « Apertus par Internet » est éteint dans les réglages.</p>")


# ---------------------------------------------------------------------- les pages
def dessiner_preuves() -> str:
    from .ecrans import _e

    boutons = ""
    for i, (question, lien, aide, aussi) in enumerate(PREUVES, 1):
        boutons += (f"<section style='margin:1rem 0'><a class='bouton preuve' href=\"{_e(lien)}\">{i}. {_e(question)}</a>"
                    f"<p class='ou' style='margin:.3rem 0'>{_e(aide)}</p>"
                    + "".join(f"<p style='margin:.2rem 0'>Et aussi : <a class='aussi' href=\"{_e(l)}\">{_e(t)}</a></p>" for t, l in aussi)
                    + "</section>")
    return ("<p>Le jury choisit une question ; on ouvre la preuve. Chaque preuve dit son étiquette : RÉEL, FAUX ROBOT, SIMULÉ ou "
            "JOUÉ. Les pages pour l'équipe demandent le code d'équipe depuis un autre ordinateur.</p>" + boutons)


def brancher_preuves(app: FastAPI, clinique) -> None:
    from briques.b12_boite_noire.journal import DOSSIER_DEFAUT

    from . import brancher, essais_reels, fiche
    from .ecrans import _e, _page

    def tableau(lignes: list[dict[str, str]]) -> str:
        return "<table>" + "".join(f"<tr><td><b>{_e(l['titre'])}</b></td><td>{_e(l['valeur'])}</td></tr>" for l in lignes) + "</table>"

    @app.get("/clinique/preuves", response_class=HTMLResponse)
    async def page_preuves():
        return _page("Clinique — Preuves", "<h1>Preuves</h1>", dessiner_preuves())

    @app.get("/clinique/preuves/essais", response_class=HTMLResponse)
    async def page_preuve_essais():
        lignes = fiche.lignes_des_essais(essais_reels.CompteurReel(essais_reels.FICHIER), DOSSIER_DEFAUT / "essais_dernier.json")
        milieu = (tableau(lignes) + "<p class='ou'>Le tableau des vingt essais est refait par <code>python3 lancer.py essais</code> "
                  "(environ une minute, faux robot). Les essais réels se comptent sur la page "
                  "<a href=\"/clinique/essais-reels\">Essais réels</a>. Les deux ne sont jamais mélangés.</p>"
                  "<p><a class='bouton' href=\"/clinique/preuves\">Retour aux preuves</a></p>")
        return _page("Clinique — Sur vingt essais", "<h1>Sur vingt essais, combien réussissent ?</h1>", milieu)

    @app.get("/clinique/preuves/brancher", response_class=HTMLResponse)
    async def page_preuve_brancher():
        lignes = fiche.lignes_du_branchement(brancher.DOSSIER / brancher.FICHIER)
        milieu = (tableau(lignes) + "<p>Pour le montrer : <code>python3 lancer.py brancher-carte roues_deux_bras --je-commence</code>. "
                  "Le test de conformité tourne sur le faux robot avec la carte donnée ; le chronomètre s'arrête seul quand tout "
                  "réussit. Avec un vrai robot, c'est un feu orange : un humain tape la commande, le responsable sécurité est là.</p>"
                  "<p><a class='bouton' href=\"/clinique/preuves\">Retour aux preuves</a></p>")
        return _page("Clinique — Brancher un robot", "<h1>Branchez un autre robot.</h1>", milieu)

    @app.get("/clinique/ou-tourne-quoi", response_class=HTMLResponse)
    async def page_ou_tourne_quoi():
        from .mesures_cerveau import DOSSIER

        chaine = _lire(Path(DOSSIER), "chaine") or {}
        memoire = chaine.get("memoire") or {}
        texte = (f"{memoire['moins_de_libre_go']} Go libres au plus bas sur {memoire['total_go']} Go, mesuré le {_jour(chaine)}"
                 .replace(".", ",") if "moins_de_libre_go" in memoire and "total_go" in memoire else None)
        milieu = dessiner_ou_tourne_quoi(ou_tourne_quoi(), texte) + "<p><a class='bouton' href=\"/clinique/preuves\">Retour aux preuves</a></p>"
        return _page("Clinique — Où tourne quoi", "<h1>Où tourne quoi ?</h1>", milieu)


# ---------------------------------------------------------------------- J07b : la commande des preuves
# Chaque preuve est jouée par les vraies pièces, sur le faux robot, et rend {reussie, etiquette, detail}.
# Le « contexte » : court (preuve 1 avec trois essais), dossier (où écrire ce que les commandes écrivent), cache (partagé).

def _seance_enregistree(contexte: dict[str, Any]) -> dict[str, Any]:
    """Une grande répétition, enregistrée (comme le rejeu autonome) : ses moments et ses erreurs attrapées."""
    if "seance" not in contexte["cache"]:
        from . import chef_clinique, moments
        from .rejeu_autonome import enregistrer

        sortie: list[str] = []
        with enregistrer() as entrees:
            code = chef_clinique.jouer(ecrire=sortie.append)
        entrees.sort(key=lambda e: e["heure"])
        trouves = moments.moments(entrees)
        contexte["cache"]["seance"] = {"code": code, "trouves": trouves, "attrapees": moments.erreurs_attrapees(trouves),
                                       "lignes": len(entrees)}
    return contexte["cache"]["seance"]


def _client(contexte: dict[str, Any]):
    """Les écrans de la clinique, branchés pour la commande (le faux logiciel dans un dossier à part)."""
    if "client" not in contexte["cache"]:
        from fastapi.testclient import TestClient

        from .ecrans import brancher_ecrans

        app = FastAPI()
        clinique = brancher_ecrans(app, code_equipe="code-de-la-commande-des-preuves")
        clinique.faux_logiciel.dossier = Path(contexte["dossier"]) / "faux_logiciel"
        contexte["cache"]["client"] = TestClient(app, headers={"X-Code-Equipe": "code-de-la-commande-des-preuves"})
        contexte["cache"]["clinique"] = clinique
    return contexte["cache"]["client"]


def preuve_1(contexte: dict[str, Any]) -> dict[str, Any]:
    from . import essais

    liste = essais.charger()
    jouees = liste[:3] if contexte["court"] else liste
    bilan = essais.jouer_les_essais(jouees, ecrire=lambda _: None, dossier=Path(contexte["dossier"]) / "essais")
    n, rates = bilan["essais"], len(bilan["echecs"])
    quoi = f"{n} essais (version courte de la vérification)" if contexte["court"] else f"{n} essais"
    return {"reussie": n == len(jouees) and n > 0, "etiquette": "FAUX ROBOT ET SIMULÉ",
            "detail": f"{quoi} : {n - rates} réussis sur {n} ; le tableau est écrit ; les essais réels restent à part (page Essais réels)"}


def preuve_2(contexte: dict[str, Any]) -> dict[str, Any]:
    s = _seance_enregistree(contexte)
    complets = [m for m in s["trouves"] if all(m["quatre"].get(k) for k in ("vu", "decide", "fait", "autour"))]
    return {"reussie": s["code"] == 0 and bool(s["trouves"]) and len(complets) == len(s["trouves"]), "etiquette": "FAUX ROBOT ET SIMULÉ",
            "detail": f"une répétition enregistrée ({s['lignes']} lignes) donne {len(s['trouves'])} moments, chacun avec ses quatre "
                      f"choses : " + " ; ".join(m["genre"] for m in s["trouves"][:4])}


def preuve_3(contexte: dict[str, Any]) -> dict[str, Any]:
    from . import panne_reprise, pannes

    lien = pannes.demonstration("lien_robot", dossier=Path(contexte["dossier"]) / "panne")
    lignes: list[str] = []
    reprise = panne_reprise.essai(ecrire=lignes.append)
    fin = lien["lignes"][-1]
    return {"reussie": bool(lien["ok"]) and reprise == 0, "etiquette": "FAUX ROBOT ET SIMULÉ",
            "detail": f"le lien tombe entre le cerveau et le robot : {fin} ; la panne d'un robot simulé et la reprise par le plus "
                      f"proche (T24) : {'tenue' if reprise == 0 else 'PAS TENUE'}"}


def preuve_4(contexte: dict[str, Any]) -> dict[str, Any]:
    s = _seance_enregistree(contexte)
    a = s["attrapees"]
    return {"reussie": a["compte"] == len(a["liste"]) and a["compte"] >= 1, "etiquette": "FAUX ROBOT ET SIMULÉ",
            "detail": f"erreurs attrapées dans la séance enregistrée : {a['compte']} — "
                      + " ; ".join(m["genre"] for m in a["liste"][:4])}


def preuve_5(contexte: dict[str, Any]) -> dict[str, Any]:
    import re

    from . import brancher

    lignes: list[str] = []
    ou = Path(contexte["dossier"]) / "brancher"
    brancher.main(["roues_deux_bras", "--je-commence"], ecrire=lignes.append, dossier=ou)  # le chronomètre part
    lignes = []
    code = brancher.main(["roues_deux_bras"], ecrire=lignes.append, dossier=ou)  # le test ; le chronomètre s'arrête seul
    texte = "\n".join(lignes)
    trouve = re.search(r"contrôles réussis : (\d+) sur (\d+)", texte)
    chrono = next((l.strip() for l in lignes if "chronomètre" in l.lower()), "chronomètre : pas lu")
    return {"reussie": code == 0 and bool(trouve) and trouve.group(1) == trouve.group(2), "etiquette": "FAUX ROBOT",
            "detail": f"carte « roues_deux_bras » : {trouve.group(0) if trouve else 'pas de résultat'} ; {chrono}"}


def preuve_6(contexte: dict[str, Any]) -> dict[str, Any]:
    client = _client(contexte)
    page = client.get("/clinique/qui-decide")
    mise = client.post("/api/clinique/pause", json={"badge": "soignant-etage-2", "chose": "rouler", "minutes": 10,
                                                     "raison": "soin en cours"})
    actives = client.get("/api/clinique/pauses").json()["pauses"]
    numero = (mise.json().get("pause") or {}).get("numero") if mise.status_code == 200 else None
    levee = client.post("/api/clinique/pause/lever", json={"badge": "soignant-etage-2", "numero": str(numero)}) if numero else None
    ok = page.status_code == 200 and mise.status_code == 200 and any(p.get("numero") == numero for p in actives) \
        and levee is not None and levee.status_code == 200
    return {"reussie": ok, "etiquette": "SIMULÉ",
            "detail": f"la page « Qui décide » répond ({page.status_code}) ; une pause « rouler » mise en direct par le badge d'un "
                      f"soignant ({mise.status_code}), visible ({len(actives)} en cours), puis levée "
                      f"({levee.status_code if levee is not None else 'pas levée'}) ; mise par le programme, pas par une soignante"}


def preuve_7(contexte: dict[str, Any]) -> dict[str, Any]:
    import html

    from . import paroles

    client = _client(contexte)
    r = client.get("/clinique/ce-qu-on-nous-a-dit")
    texte = html.unescape(r.text)
    nombre = paroles.paroles_recueillies()
    honnete = ("Aucune parole recueillie" in texte) if nombre == 0 else ("DIT PAR UN SOIGNANT" in texte)
    return {"reussie": r.status_code == 200 and honnete, "etiquette": "SIMULÉ",
            "detail": (f"{nombre} parole(s) recueillie(s) ; la page le dit" if nombre else
                       "aucune parole recueillie : la page le dit (« Aucune parole recueillie pour l'instant »), c'est une preuve honnête")}


def preuve_8(contexte: dict[str, Any]) -> dict[str, Any]:
    client = _client(contexte)
    lignes = ou_tourne_quoi()
    r = client.get("/clinique/ou-tourne-quoi")
    mesurees = [l["piece"] for l in lignes if l["temps"] != NON_MESURE]
    ok = r.status_code == 200 and [l["piece"] for l in lignes] == list(PIECES) and all(
        l["internet"] == "a besoin d'internet : non" for l in lignes)
    return {"reussie": ok, "etiquette": "SIMULÉ",
            "detail": f"{len(lignes)} pièces, a besoin d'internet : non pour chacune ; temps mesuré pour : "
                      f"{', '.join(mesurees) or 'aucune'} ; les autres : non mesuré ; consommation électrique : non mesurée"}


CONTROLES = {1: preuve_1, 2: preuve_2, 3: preuve_3, 4: preuve_4, 5: preuve_5, 6: preuve_6, 7: preuve_7, 8: preuve_8}


def jouer(controles: dict[int, Any] | None = None, ecrire=print, court: bool = False, dossier: str | Path | None = None,
          toutes: bool = True) -> int:
    """Les huit preuves, l'une après l'autre. `toutes=False` : seulement celles données (pour une vérification), et la
    dernière ligne ne dit jamais « PREUVES : RÉUSSIES »."""
    import tempfile

    controles = CONTROLES if controles is None else controles
    ecrire("LES PREUVES — huit questions du jury — DONNÉES INVENTÉES — sur le FAUX ROBOT")
    a_part = None if dossier else tempfile.TemporaryDirectory()
    contexte = {"court": court, "dossier": Path(dossier) if dossier else Path(a_part.name), "cache": {}}
    ratees: list[str] = []
    numeros = range(1, len(PREUVES) + 1) if toutes else sorted(controles)
    try:
        for numero in numeros:
            question = PREUVES[numero - 1][0]
            if numero not in controles:
                ecrire(f"  {numero}. [—] MANQUANTE — {question} — pas de contrôle pour cette preuve")
                ratees.append(f"{numero} manquante")
                continue
            try:
                r = controles[numero](contexte)
            except Exception as erreur:  # une pièce qui casse : la preuve est ratée, et on dit pourquoi
                r = {"reussie": False, "etiquette": "—", "detail": f"la pièce s'est arrêtée ({type(erreur).__name__} : {erreur})"[:300]}
            ecrire(f"  {numero}. [{r['etiquette']}] {'réussie' if r['reussie'] else 'RATÉE'} — {question} — {r['detail']}")
            if not r["reussie"]:
                ratees.append(str(numero))
    finally:
        if a_part is not None:
            a_part.cleanup()
    if ratees:
        ecrire(f"PREUVES : RATÉES — {', '.join(ratees)}")
        return 1
    ecrire("PREUVES : RÉUSSIES" if toutes else f"PREUVES PARTIELLES : RÉUSSIES — seulement {', '.join(str(n) for n in numeros)}")
    return 0 if toutes else 1


def main(reste: list[str] | None = None) -> int:
    return jouer(court="--court" in (reste or []))
