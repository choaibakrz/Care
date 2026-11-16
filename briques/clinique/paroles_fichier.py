"""J06b — Le fichier des paroles de soignants (réponse de Hiba à Q7 : oui, aux conditions écrites).

Le fichier : `journal/clinique/PAROLES_DES_SOIGNANTS.md`. Ce dossier ne part jamais vers GitHub, et `.gitignore` refuse
ce nom partout. SEULE UNE PERSONNE DE L'ÉQUIPE L'ÉCRIT, À LA MAIN, à partir du modèle `PAROLES_DES_SOIGNANTS.modele.md`.
Ce programme ne fait que LIRE : il n'a aucune fonction pour écrire une parole. Un agent d'IA n'écrit jamais ce qu'un
soignant a dit, ni ce qu'il « dirait ».

Une parole, sur une ligne :
    - « la phrase, telle que la personne l'a dite » — métier : soignante — date : 14.11.2026 — accord : oui
Gardée seulement si elle est complète : une phrase entre guillemets, un métier, une date, « accord : oui ».
Mise de côté, sans jamais rendre son texte : une ligne qui nomme une personne (Madame, Monsieur, Dr…), qui parle d'un
patient ou d'une chambre, ou dont le « métier » contient autre chose qu'un métier. C'est un filet, pas une garantie :
un prénom seul dans la phrase passerait. La relecture par une personne de l'équipe reste nécessaire.

La page « Ce qu'on nous a dit » lit ce fichier par cette pièce (J06b-b, réponse de Hiba à Q26 : A).
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

FICHIER = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "PAROLES_DES_SOIGNANTS.md"
ETIQUETTE = "DIT PAR UN SOIGNANT"
AUCUNE = "Aucune parole recueillie pour l'instant. Ce que nous disons du travail des soignants est une hypothèse."
LIGNE = re.compile(r"^- «\s*(?P<phrase>.+?)\s*»(?P<suite>.*)$")
PERSONNE = re.compile(r"\b(madame|monsieur|mme|mlle|m\.|dr|docteur|docteure|patient|patiente|patients|chambre|lit \d)\b", re.IGNORECASE)
METIER = re.compile(r"^[a-zàâçéèêëîïôûùüÿœ' -]{3,40}$", re.IGNORECASE)
A_REMPLIR = ("(écrire ici", "(à remplir)")


def _champ(suite: str, nom: str) -> str | None:
    trouve = re.search(rf"—\s*{nom}\s*:\s*([^—]+)", suite)
    return trouve.group(1).strip() if trouve else None


def lire_le_texte(texte: str) -> dict[str, Any]:
    paroles, de_cote, incompletes = [], 0, 0
    for brute in texte.splitlines():
        trouve = LIGNE.match(brute.strip())
        if not trouve:
            if brute.strip().startswith("- ") and "accord" in brute:
                incompletes += 1  # une ligne de parole mal formée (pas de guillemets)
            continue
        phrase, suite = trouve.group("phrase"), trouve.group("suite")
        metier, date, accord = _champ(suite, "métier"), _champ(suite, "date"), _champ(suite, "accord")
        if any(marque in brute for marque in A_REMPLIR) or not (metier and date) or (accord or "").lower() != "oui":
            incompletes += 1
            continue
        if PERSONNE.search(phrase) or not METIER.match(metier) or "," in metier:
            de_cote += 1  # son texte n'est jamais rendu
            continue
        paroles.append({"phrase": phrase, "metier": metier, "date": date})
    return {"paroles": paroles, "mises_de_cote": de_cote, "incompletes": incompletes}


def lire(fichier: str | Path | None = None) -> dict[str, Any]:
    """Les paroles du fichier de l'équipe. Pas de fichier : aucune parole (c'est le cas tant que l'équipe n'a rien écrit)."""
    fichier = Path(fichier) if fichier else FICHIER
    if not fichier.exists():
        return {"paroles": [], "mises_de_cote": 0, "incompletes": 0, "fichier": False}
    return {**lire_le_texte(fichier.read_text(encoding="utf-8")), "fichier": True}


def dessiner(lu: dict[str, Any]) -> str:
    """Le morceau de page : les paroles gardées, chacune avec l'étiquette, le métier et la date. Jamais un nom."""
    e = lambda t: html.escape(str(t), quote=True)  # noqa: E731
    if not lu["paroles"]:
        corps = f"<p class='dit'>{e(AUCUNE)}</p>"
    else:
        corps = "<ul>" + "".join(f"<li><b>{ETIQUETTE}</b> — « {e(p['phrase'])} » <small>({e(p['metier'])}, {e(p['date'])})</small></li>"
                                 for p in lu["paroles"]) + "</ul>"
    notes = []
    if lu["mises_de_cote"]:
        n = lu["mises_de_cote"]
        notes.append(f"{n} ligne{'s' if n > 1 else ''} mise{'s' if n > 1 else ''} de côté : elle{'s' if n > 1 else ''} "
                     f"nomme{'nt' if n > 1 else ''} une personne ou parle{'nt' if n > 1 else ''} d'un patient. À corriger dans le fichier.")
    if lu["incompletes"]:
        n = lu["incompletes"]
        notes.append(f"{n} ligne{'s' if n > 1 else ''} incomplète{'s' if n > 1 else ''} (il faut la phrase, le métier, la date et « accord : oui »).")
    return corps + "".join(f"<p class='ou'>{e(note)}</p>" for note in notes)
