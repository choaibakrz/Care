"""Brique 12 — Rejouer une session après coup, à partir de la boîte noire.

En ligne de commande :
    python -m briques.b12_boite_noire.rejeu                 # le dernier journal
    python -m briques.b12_boite_noire.rejeu journal/X.jsonl # un journal précis

Le rejeu ne touche JAMAIS un robot : il republie les événements sur un bus séparé
(pour l'écran ou l'analyse), et rien d'autre.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from commun.bus import Bus
from commun.evenements import Evenement

from .fiche import calculer
from .journal import dernier_journal, lire


async def rejouer(evenements: list[Evenement], bus: Bus, vitesse: float | None = None) -> None:
    """vitesse=None : tout d'un coup ; vitesse=1 : au rythme réel ; 10 : dix fois plus vite."""
    precedent = None
    for ev in sorted(evenements, key=lambda e: (e.t, e.numero)):
        if vitesse and precedent is not None:
            await asyncio.sleep(max(0.0, (ev.t - precedent) / vitesse))
        precedent = ev.t
        await bus.publier(ev)


def recit(evenements: list[Evenement]) -> list[str]:
    """Une ligne lisible par événement important."""
    lignes = []
    t0 = evenements[0].t if evenements else 0
    for e in sorted(evenements, key=lambda e: (e.t, e.numero)):
        d = e.donnees
        if e.type in ("action_progression",):
            continue
        quoi = {
            "parole_entendue": lambda: f"🗣  [{d.get('langue') or '?'}] « {d.get('texte')} »",
            "demande_comprise": lambda: f"🧠 {d.get('genre')} {(d.get('action') or {}).get('nom', '')} (confiance {d.get('confiance')})",
            "gardien_decision": lambda: f"🛡  gardien : {d.get('verdict')} {[r['code'] for r in d.get('raisons', [])]}",
            "action_demarree": lambda: f"🤖 démarre {(d.get('action') or {}).get('nom')}",
            "action_terminee": lambda: f"🤖 fin : {d.get('statut')} {d.get('message') or ''}",
            "action_refusee": lambda: f"⛔ prise refuse : {[r['code'] for r in d.get('raisons', [])]}",
            "reponse_dite": lambda: f"💬 [{d.get('langue')}] {d.get('texte')}",
            "question_posee": lambda: f"❓ {d.get('question')}",
            "arret_urgence": lambda: f"🛑 ARRÊT D'URGENCE ({d.get('raison')})",
        }.get(e.type, lambda: f"·  {e.type} {json.dumps(d, ensure_ascii=False, default=str)[:80]}")()
        lignes.append(f"{e.t - t0:8.2f}s  {quoi}")
    return lignes


def main(argv: list[str]) -> int:
    chemin = Path(argv[0]) if argv else dernier_journal()
    if not chemin or not chemin.exists():
        print("Aucun journal trouvé.")
        return 1
    evs = lire(chemin)
    print(f"Journal : {chemin}  ({len(evs)} événements)\n")
    print("\n".join(recit(evs)))
    print("\nFiche de vérité :")
    print(calculer(evs).model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
