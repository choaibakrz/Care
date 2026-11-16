"""Brique 12 — La boîte noire : chaque événement, avec l'heure, dans un fichier qui ne s'efface pas.

Format : une ligne JSON par événement (« JSON Lines »). Lisible par un humain, par un tableur,
et par n'importe quel outil plus tard. Chaque ligne est écrite tout de suite : une panne de courant
ne perd que la dernière ligne au pire.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from commun.bus import Bus
from commun.evenements import Evenement

DOSSIER_DEFAUT = Path(__file__).resolve().parents[2] / "journal"


class BoiteNoire:
    def __init__(self, bus: Bus, dossier: str | Path = DOSSIER_DEFAUT, nom: str | None = None) -> None:
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        nom = nom or datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.fichier = self.dossier / f"{nom}.jsonl"
        self._f = open(self.fichier, "a", encoding="utf-8")
        self.nb = 0
        bus.abonner(self.noter)

    def noter(self, ev: Evenement) -> None:
        self._f.write(json.dumps(ev.model_dump(), ensure_ascii=False, default=str) + "\n")
        self._f.flush()
        self.nb += 1

    def fermer(self) -> None:
        if not self._f.closed:
            self._f.close()


def lire(fichier: str | Path) -> list[Evenement]:
    evenements = []
    with open(fichier, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                try:
                    evenements.append(Evenement.model_validate(json.loads(ligne)))
                except Exception:
                    continue  # une ligne abîmée (coupure de courant) ne bloque pas la lecture
    return evenements


def dernier_journal(dossier: str | Path = DOSSIER_DEFAUT) -> Path | None:
    fichiers = sorted(Path(dossier).glob("*.jsonl"))
    return fichiers[-1] if fichiers else None
