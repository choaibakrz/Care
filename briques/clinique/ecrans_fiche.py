"""T27 — La fiche de vérité sur un écran.

    /clinique/fiche-de-verite      la fiche calculée par la DERNIÈRE répétition (`python3 lancer.py repetition`)

La page lit le fichier gardé par la répétition (`fiche.garder`). Elle n'invente rien : sans répétition, elle le dit.
Ce n'est pas la séance en cours : c'est écrit en haut, avec la date de la répétition. Aucun nom de patient.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import fiche

PAGE = "/clinique/fiche-de-verite"


def dessiner(lue: dict | None) -> str:
    from .ecrans import _e

    if lue is None:
        return ("<p class='rien'>Aucune répétition n'a encore gardé sa fiche sur cet ordinateur.</p>"
                "<p class='ou'>Pour la calculer : <code>python3 lancer.py repetition</code>. Rien n'est tapé à la main.</p>")
    try:
        quand = datetime.fromisoformat(str(lue.get("quand"))).strftime("le %d.%m.%Y à %H h %M")
    except ValueError:
        quand = "à une date inconnue"
    du_cahier = set(fiche.LIGNES_DU_CAHIER)
    rangs = "".join(f"<tr><td><b>{_e(l.get('titre', ''))}</b>{' <span class=\'ou\'>(cahier)</span>' if l.get('titre') in du_cahier else ''}</td>"
                    f"<td>{_e(l.get('valeur', ''))}</td></tr>" for l in lue["lignes"])
    return (f"<p><b>Fiche calculée par la dernière répétition, {_e(quand)}.</b> Ce n'est pas la séance en cours. "
            "Chaque ligne est comptée par le programme ; « non mesuré » veut dire non mesuré.</p>"
            "<p class='ou'><b>Les étiquettes</b> : RÉEL (un vrai robot, une vraie personne) · FAUX ROBOT (le robot simulé de "
            "l'ossature) · SIMULÉ (dans l'ordinateur) · JOUÉ (fait par une personne qui joue un rôle).</p>"
            f"<table><tr><th>Ligne</th><th>Ce qui a été compté</th></tr>{rangs}</table>")


def brancher_fiche(app: FastAPI, fichier: str | Path | None = None) -> None:
    from .ecrans import _page

    @app.get(PAGE, response_class=HTMLResponse)
    async def page_fiche_de_verite():
        return _page("Clinique — Fiche de vérité", "<h1>Fiche de vérité</h1>", dessiner(fiche.derniere(fichier)))
