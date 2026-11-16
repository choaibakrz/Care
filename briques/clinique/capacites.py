"""K05 — Le tableau des capacités, et ce qui n'est pas résolu (avenant 2, K05 ; avenant 3, M02).

    /clinique/capacites     « Ce que le système sait faire, et comment on le sait », puis « Ce que nous n'avons pas résolu »
    /clinique/concours      la page « Concours » (avenant 2, partie 6) : des liens pour le chef de démonstration

Une ligne par capacité (la liste est dans `capacites.yaml` : elle dit où regarder, jamais un résultat). Quatre colonnes :
PROUVÉ SUR UN VRAI ROBOT · PROUVÉ SUR LE FAUX ROBOT · VÉRIFIÉ PAR DES TESTS SEULEMENT · PAS FAIT.
Chaque ligne va dans la colonne la plus forte que ses résultats permettent :
- un essai RÉEL réussi, compté par l'équipe (compteur d'essais réels) → la première colonne. Jamais sans essai réel.
- sinon un essai réussi sur le faux robot (essais comptés, tirage, branchements, rejeux) → la deuxième ;
- sinon un fichier de vérification → la troisième ; sinon, ou si une de ses tâches est BLOQUÉ → PAS FAIT.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

RACINE = Path(__file__).resolve().parents[2]
LISTE = Path(__file__).with_name("capacites.yaml")
DOSSIER_DES_TESTS = Path(__file__).with_name("tests")
PAS_RESOLU = RACINE / "docs/projet/PAS_RESOLU.md"
SUIVI = RACINE / "docs/projet/SUIVI_CLINIQUE.md"
REEL, FAUX, TESTS, PAS_FAIT = ("PROUVÉ SUR UN VRAI ROBOT", "PROUVÉ SUR LE FAUX ROBOT", "VÉRIFIÉ PAR DES TESTS SEULEMENT",
                                      "PAS FAIT")
VIDE = "—"


def _jour(texte: Any) -> str:
    try:
        return datetime.fromisoformat(str(texte)).strftime("%d.%m.%Y")
    except ValueError:
        return "date inconnue"


def _json(fichier: Path) -> Any:
    try:
        return json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def statuts_du_suivi(texte: str | None = None) -> dict[str, str]:
    """La colonne « état » de chaque tâche du suivi (FAIT, À FAIRE, BLOQUÉ…)."""
    if texte is None:
        try:
            texte = SUIVI.read_text(encoding="utf-8")
        except OSError:
            texte = ""
    statuts = {}
    for ligne in texte.splitlines():
        cases = [c.strip() for c in ligne.split("|")]
        if len(cases) > 4 and re.fullmatch(r"[A-Z]+\d+[a-z]?(-[a-z])?", cases[1] or ""):
            statuts[cases[1]] = cases[4]
    return statuts


def _faux_robot(cap: dict[str, Any], essais: Any, mesures: Path, branchements: Path, rejeux: Path) -> tuple[int, str]:
    """(réussis, texte) sur le faux robot et les robots simulés, lus dans les résultats gardés."""
    morceaux, reussis = [], 0
    etapes = [str(n) for n in cap.get("etapes") or []]
    if etapes and isinstance(essais, dict):
        par = essais.get("par_etape") or {}
        vues = [par[n] for n in etapes if n in par]
        if vues:
            r, n = sum(v.get("reussies", 0) for v in vues), sum(v.get("essais", 0) for v in vues)
            etiquettes = sorted({e for v in vues for e in v.get("etiquettes") or []})
            quelle = f"étape {etapes[0]}" if len(etapes) == 1 else "étapes " + " et ".join(etapes)
            morceaux.append(f"{r} réussis sur {n} ({quelle}, essais comptés du {_jour(essais.get('date'))} ; {', '.join(etiquettes)})")
            reussis += r
    source = cap.get("source")
    if source == "tirage":
        t = _json(mesures / "tirage.json")
        if isinstance(t, dict) and "demandes" in t:
            morceaux.append(f"{t['demandes']} demandes tirées au hasard, gestes interdits exécutés : {t.get('interdits_executes', '?')} "
                            f"({t.get('etiquette', 'FAUX ROBOT')}, {_jour(t.get('quand'))})")
            reussis += int(t.get("interdits_executes", 1) == 0)
    elif source == "branchements":
        b = _json(branchements)
        if isinstance(b, dict):
            finies = {nom: v for nom, v in b.items() if isinstance(v, dict) and v.get("fin")}
            if finies:
                morceaux.append(f"{len(finies)} carte{'s' if len(finies) > 1 else ''} branchée{'s' if len(finies) > 1 else ''}, tous les "
                                f"contrôles réussis ({', '.join(sorted(finies))} ; FAUX ROBOT)")
                reussis += len(finies)
    elif source == "rejeux":
        faits = [d for d in Path(rejeux).glob("*/index.html")] if Path(rejeux).exists() else []
        if faits:
            morceaux.append(f"{len(faits)} rejeu{'x' if len(faits) > 1 else ''} fabriqué{'s' if len(faits) > 1 else ''} après une répétition")
            reussis += len(faits)
    return reussis, " ; ".join(morceaux) or VIDE


def _reel(cap: dict[str, Any], lignes: list[dict[str, Any]]) -> tuple[int, str]:
    if cap.get("source") == "etageres":
        les_siennes = [l for l in lignes if l.get("epreuve")]
    else:
        mots = [m.lower() for m in cap.get("mots") or []]
        les_siennes = [l for l in lignes if not l.get("epreuve") and any(m in str(l.get("geste", "")).lower() for m in mots)]
    if not les_siennes:
        return 0, VIDE
    reussis = sum(1 for l in les_siennes if l.get("resultat") == "réussi")
    derniere = max(str(l.get("quand", "")) for l in les_siennes)
    return reussis, f"{reussis} réussi{'s' if reussis > 1 else ''} sur {len(les_siennes)} (RÉEL, dernier le {_jour(derniere)})"


def tableau(essais: str | Path | None = None, reels: str | Path | None = None, branchements: str | Path | None = None,
            mesures: str | Path | None = None, rejeux: str | Path | None = None, suivi: str | None = None,
            liste: str | Path = LISTE) -> list[dict[str, str]]:
    from briques.b12_boite_noire.journal import DOSSIER_DEFAUT

    from . import brancher, essais_reels
    from .mesures_cerveau import DOSSIER as DOSSIER_MESURES
    from .rejeu_autonome import DOSSIER_DEFAUT as DOSSIER_REJEUX

    essais = _json(Path(essais) if essais else DOSSIER_DEFAUT / "essais_dernier.json")
    lignes_reelles = essais_reels.CompteurReel(reels).lignes() if reels is None or Path(reels).exists() else []
    branchements = Path(branchements) if branchements else brancher.DOSSIER / brancher.FICHIER
    mesures = Path(mesures) if mesures else DOSSIER_MESURES
    rejeux = Path(rejeux) if rejeux else DOSSIER_REJEUX
    statuts = statuts_du_suivi(suivi)
    rendu = []
    for cap in yaml.safe_load(Path(liste).read_text(encoding="utf-8"))["capacites"]:
        r_reel, reel = _reel(cap, lignes_reelles)
        r_faux, faux = _faux_robot(cap, essais, mesures, branchements, rejeux)
        tests = [t for t in cap.get("tests") or [] if (DOSSIER_DES_TESTS / t).exists()]
        bloquees = [t for t in cap.get("taches") or [] if statuts.get(t, "").startswith("BLOQUÉ")]
        if bloquees:
            niveau, pas_fait = PAS_FAIT, "PAS FAIT : BLOQUÉ (" + ", ".join(bloquees) + ")"
        elif r_reel:
            niveau, pas_fait = REEL, VIDE
        elif r_faux:
            niveau, pas_fait = FAUX, VIDE
        elif tests:
            niveau, pas_fait = TESTS, VIDE
        else:
            niveau, pas_fait = PAS_FAIT, "PAS FAIT : aucun essai ni vérification"
        rendu.append({"titre": cap["titre"], "niveau": niveau, "reel": reel, "faux": faux,
                      "tests": ("oui : " + ", ".join(tests)) if tests else VIDE, "pas_fait": pas_fait, "note": cap.get("note", "")})
    return rendu


# ---------------------------------------------------------------------- les pages
def dessiner(lignes: list[dict[str, str]], pas_resolu: str) -> str:
    from .ecrans import _e

    def case(texte: str, marque: bool) -> str:
        return f"<td{' style=background:#e8f5e9' if marque else ''}>{'<b>' if marque else ''}{_e(texte)}{'</b>' if marque else ''}</td>"

    rangs = "".join(
        f"<tr><td><b>{_e(l['titre'])}</b>{('<br><span class=ou>' + _e(l['note']) + '</span>') if l['note'] else ''}</td>"
        + case(l["reel"], l["niveau"] == REEL) + case(l["faux"], l["niveau"] == FAUX)
        + case(l["tests"], l["niveau"] == TESTS) + case(l["pas_fait"], l["niveau"] == PAS_FAIT) + "</tr>"
        for l in lignes)
    comptes = {n: sum(1 for l in lignes if l["niveau"] == n) for n in (REEL, FAUX, TESTS, PAS_FAIT)}
    elements = [l[2:] for l in pas_resolu.splitlines() if l.startswith("- ")]
    return ("<p>Ce tableau est fabriqué à partir des résultats : les essais comptés, le compteur d'essais réels, les branchements, "
            "les mesures, les rejeux, et les fichiers de vérification. Il n'est pas écrit à la main. Une capacité sans essai réel "
            "ne peut pas être dans la première colonne. La case en vert est la colonne de la ligne.</p>"
            f"<p>{' · '.join(f'{_e(n)} : {c}' for n, c in comptes.items())}</p>"
            f"<table><tr><th>Capacité</th><th>{_e(REEL)}</th><th>{_e(FAUX)}</th><th>{_e(TESTS)}</th><th>{_e(PAS_FAIT)}</th></tr>"
            f"{rangs}</table>"
            "<article><h2>Ce que nous n'avons pas résolu</h2>"
            + ("<ul>" + "".join(f"<li>{_e(e)}</li>" for e in elements) + "</ul>" if elements else "<p class='rien'>docs/projet/PAS_RESOLU.md est vide.</p>")
            + "<p class='ou'>Le fichier docs/projet/PAS_RESOLU.md, à la racine du projet. L'équipe le complète.</p></article>")


LIENS_DU_CONCOURS = (
    ("Le tirage : des demandes au hasard, et « gestes interdits exécutés »", "/clinique/tirage"),
    ("Les trois chiffres : réussis du premier coup, aide humaine, durée sans arrêt", "/clinique/fiche-de-verite"),
    ("L'aide humaine : le bouton « J'ai aidé »", "/clinique/aide-humaine"),
    ("Le tableau des capacités, et ce qui n'est pas résolu", "/clinique/capacites"),
    ("L'écran Invité : un juré aux commandes", "/clinique/invite"),
    ("Les avis des personnes (anonymes)", "/clinique/avis"),
    ("L'épreuve des étagères", "/clinique/etageres"),
)


def brancher_capacites(app: FastAPI) -> None:
    from .ecrans import _e, _page

    @app.get("/clinique/capacites", response_class=HTMLResponse)
    async def page_capacites():
        try:
            pas_resolu = PAS_RESOLU.read_text(encoding="utf-8")
        except OSError:
            pas_resolu = ""
        return _page("Clinique — Ce que le système sait faire", "<h1>Ce que le système sait faire, et comment on le sait</h1>",
                     dessiner(tableau(), pas_resolu))

    @app.get("/clinique/concours", response_class=HTMLResponse)
    async def page_concours():
        liens = "".join(f"<a href=\"{_e(l)}\">{_e(t)}</a>" for t, l in LIENS_DU_CONCOURS)
        milieu = (f"<p>Pour le chef de démonstration. Chaque tâche de l'avenant « concours » ajoute ici son lien.</p><nav>{liens}</nav>"
                  "<p class='ou'>La commande du concours (les sept contrôles, sur le faux robot) : <code>python3 lancer.py concours</code>.</p>")
        return _page("Clinique — Concours", "<h1>Concours</h1>", milieu)
