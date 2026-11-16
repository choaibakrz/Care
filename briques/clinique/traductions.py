"""H03 — Les phrases traduites des écrans, lues dans UN seul fichier : `traductions_ecrans.yaml` (réponse de Hiba à Q19).

    traduire(html_du_milieu_de_l_ecran, "de", "soignant")

- Les textes fixes des écrans du soignant et du médecin : en allemand (section « ecrans_de » du fichier).
- Les données du faux dossier affichées au patient, au soignant et au médecin : les lignes du programme, le genre des
  documents, le premier mot d'un lieu, le titre d'une liste de soin — par une table (section « donnees »).
- RIEN N'EST INVENTÉ : ce qui n'est pas dans le fichier reste en français. Les habitudes, les phrases du résumé du
  médecin, les demandes, les questions de la patiente ne sont pas traduites.
- La traduction ne touche que le TEXTE affiché, entre les balises : jamais une adresse, un bouton, un identifiant.
- TOUT CE FICHIER DE PHRASES EST ÉCRIT PAR UN AGENT, PAS RELU par une personne qui parle la langue (voir NON_TESTE.md).
Le faux dossier n'est pas changé : la table est à côté.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

FICHIER = Path(__file__).resolve().parent / "traductions_ecrans.yaml"
ECRANS_EN_ALLEMAND = ("soignant", "medecin")
# La table du programme du patient est ALLUMÉE sur son écran (réponse de Hiba à Q25 : A, le 12.11.2026 ; tâche H03b).
# Les trois lignes d'essai qui demandaient le français sont adaptées, avec son accord (voir DECISIONS.md).
PATIENT_TRADUIT = True
LANGUES = ("de", "it", "en")
ENTRE_LES_BALISES = re.compile(r">([^<]+)<")


@lru_cache(maxsize=1)
def charger() -> dict[str, Any]:
    return yaml.safe_load(FICHIER.read_text(encoding="utf-8"))


def _donnee(texte: str, langue: str, tables: dict[str, Any], allemand_du_metier: bool) -> str:
    """Un texte venu des données : une ligne de programme (« physiothérapie — Salle 2 »), un document (« genre : titre »),
    le titre d'une liste de soin. Traduit seulement s'il COMMENCE par une valeur connue de la table."""
    for francais, par_langue in tables["programme"].items():
        if texte == francais or texte.startswith(francais + " — "):
            lieu = texte[len(francais) + 3:]
            mot, _, reste = lieu.partition(" ")
            if mot in tables["lieux"]:  # le lieu : son premier mot ; un lieu inconnu reste tel quel
                lieu = tables["lieux"][mot][langue] + (" " + reste if reste else "")
            return par_langue[langue] + (" — " + lieu if lieu else "")
    for francais, par_langue in tables["genres_de_documents"].items():
        if texte == francais or texte.startswith(francais + " : "):
            return par_langue[langue] + texte[len(francais):]  # le titre du document reste tel qu'il est écrit
    if allemand_du_metier and texte in tables["listes_de_soin"]:
        return tables["listes_de_soin"][texte]
    return texte


def traduire(page: str, langue: str | None, ecran: str, patient: bool | None = None) -> str:
    """Le milieu d'un écran, avec ses textes traduits. Français, langue inconnue, écran sans traduction : inchangé.
    `patient` : traduire aussi l'écran du patient (par défaut : PATIENT_TRADUIT, allumé depuis la réponse à Q25)."""
    if langue not in LANGUES or ecran not in ("patient", *ECRANS_EN_ALLEMAND):
        return page
    if ecran == "patient" and not (PATIENT_TRADUIT if patient is None else patient):
        return page
    fichier = charger()
    du_metier = ecran in ECRANS_EN_ALLEMAND and langue == "de"
    if ecran != "patient" and not du_metier:
        return page
    entiers = fichier["ecrans_de"]["entiers"] if du_metier else {}
    morceaux = sorted((fichier["ecrans_de"]["morceaux"] if du_metier else {}).items(), key=lambda paire: -len(paire[0]))

    def un_texte(trouve: re.Match) -> str:
        brut = trouve.group(1)
        texte = html.unescape(brut)
        nu = texte.strip()
        if not nu:
            return trouve.group(0)
        rendu = entiers.get(nu) or _donnee(nu, langue, fichier["donnees"], du_metier)
        if rendu == nu and not nu.startswith(":"):  # pas un texte entier connu : des morceaux fixes, peut-être.
            # Un texte qui commence par « : » est une phrase du résumé ou une donnée : jamais traduite à moitié.
            for francais, allemand in morceaux:
                rendu = rendu.replace(francais.strip() if nu == francais.strip() else francais, allemand)
        if rendu == nu:
            return trouve.group(0)
        avant, apres = texte[:len(texte) - len(texte.lstrip())], texte[len(texte.rstrip()):]
        return ">" + html.escape(avant + rendu + apres, quote=True).replace("&#x27;", "&#x27;") + "<"

    return ENTRE_LES_BALISES.sub(un_texte, page)
