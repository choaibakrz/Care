"""Le carnet : tout ce que le prototype crée (cahier 5.1). Le faux dossier, lui, ne change jamais.

    carnet = Carnet(horloge=horloge)
    carnet.ecrire(badge, "point de liste", {"patient": "p01", "liste": "installation", "numero": 3, "etat": "fait"},
                  valide_par_un_humain=True)

- Chaque ligne dit : qui l'a créée, quand (l'heure de la démonstration et l'heure réelle), et si un humain l'a validée.
- On ajoute des lignes, on n'en efface jamais et on n'en change jamais. L'état d'une chose est sa dernière ligne.
- Une ligne JSON par écriture, dans un fichier si on en donne un (comme le journal des accès).
Iront ici, au fil des tâches : les coches, les propositions de rangement, les brouillons, les tâches, les questions.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MARQUE = "données inventées"
DOSSIER_CARNET = Path(__file__).resolve().parents[2] / "journal" / "clinique"


class Carnet:
    def __init__(self, horloge=None, fichier: str | Path | None = None) -> None:
        self.horloge = horloge
        self.fichier = Path(fichier) if fichier else None
        self._lignes: list[dict[str, Any]] = []
        if self.fichier:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def de_la_seance(cls, horloge=None) -> "Carnet":
        """Un carnet neuf pour cette séance, écrit dans journal/clinique/ (un fichier par lancement)."""
        return cls(horloge, DOSSIER_CARNET / datetime.now().strftime("carnet_%Y-%m-%d_%H%M%S.jsonl"))

    def _quand(self) -> dict[str, Any]:
        reel = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        if self.horloge is None:
            return {"jour": None, "heure": None, "temps_accelere": False, "reel": reel}
        etat = self.horloge.etat()
        return {"jour": etat["jour"], "heure": etat["heure"], "temps_accelere": etat["temps_accelere"], "reel": reel}

    def ecrire(self, badge, genre: str, donnees: dict[str, Any], valide_par_un_humain: bool) -> dict[str, Any]:
        """Ajoute une ligne. `badge` : celui qui crée la ligne. Rend une copie de la ligne écrite."""
        ligne = {"numero": len(self._lignes) + 1, "quand": self._quand(), "qui": badge.id, "role": badge.role,
                 "genre": genre, "donnees": copy.deepcopy(donnees), "valide_par_un_humain": bool(valide_par_un_humain),
                 "marque": MARQUE}
        self._lignes.append(ligne)
        if self.fichier:
            with open(self.fichier, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        return copy.deepcopy(ligne)

    def lignes(self, genre: str | None = None) -> list[dict[str, Any]]:
        """Des copies : les modifier ne change pas le carnet."""
        return [copy.deepcopy(l) for l in self._lignes if genre is None or l["genre"] == genre]
