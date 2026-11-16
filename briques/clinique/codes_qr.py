"""H19 — Les codes QR des écrans (réponse de Hiba à Q29 : A ; « oui, installe » à Q30, le 12.11.2026).

Un code QR est un petit carré de points qu'un téléphone lit avec son appareil photo : il ouvre l'adresse écrite dedans.
L'outil : « segno » 1.6.6 (écrit en Python seul, licence BSD à 3 clauses, lue dans son fichier LICENSE le 13.11.2026 ;
voir LICENCES.md). Il est installé dans `.venv`. S'il manque (une autre machine), rien ne plante : `disponible()` dit
non, et la page garde les adresses écrites en gros.
Vérifié par le Mac lui-même : `outils/lire_code_qr.swift` relit chaque code (essai `test_codes_qr.py`).
Pas essayé avec un vrai téléphone.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

CORRECTION = "m"  # environ 15 % du code peut être abîmé (un écran sale, un reflet) et il se lit encore


def _segno() -> Any | None:
    try:
        import segno
    except ImportError:
        return None
    return segno


def disponible() -> bool:
    return _segno() is not None


def fabriquer(adresse: str) -> Any:
    """Le code QR d'une adresse (un objet segno). Le même texte donne toujours le même code."""
    segno = _segno()
    if segno is None:
        raise RuntimeError("segno n'est pas installé : pas de code QR")
    # make_qr, pas make : pour un texte court, make ferait un « micro code QR », que beaucoup de téléphones ne lisent pas
    # (le Mac ne le relit pas non plus : vu au tour 109).
    return segno.make_qr(str(adresse), error=CORRECTION, boost_error=False)


def dessin_svg(adresse: str, echelle: int = 5) -> str | None:
    """Le code en SVG (un dessin écrit dans la page, sans fichier ni réseau), avec un texte pour les lecteurs d'écran.
    None si segno manque."""
    if not disponible():
        return None
    svg = fabriquer(adresse).svg_inline(scale=echelle, dark="#000", light="#fff", omitsize=False)
    etiquette = html.escape(f"Code QR : {adresse}", quote=True)
    return svg.replace("<svg ", f"<svg role='img' aria-label=\"{etiquette}\" ", 1)


def enregistrer_png(adresse: str, fichier: str | Path, echelle: int = 8) -> Path:
    """Le même code en image PNG (pour le relire avec le Mac, ou l'imprimer)."""
    fichier = Path(fichier)
    fabriquer(adresse).save(str(fichier), kind="png", scale=echelle)
    return fichier
