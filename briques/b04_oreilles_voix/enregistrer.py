"""Enregistrer des ordres dits par l'équipe, pour le banc d'essai (surtout le suisse allemand). NON TESTÉ (micro Mac).

    python3 lancer.py enregistrer gsw --prenom Hiba

Les enregistrements restent sur cet ordinateur (donnees_voix/equipe/, hors du dépôt). On demande l'accord avant.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np

from .banc_voix import ORDRES
from .fin_de_parole import DetecteurParole

RACINE = Path(__file__).resolve().parents[2]
ORDRES_SUISSE_ALLEMAND = [
    ("Gang i d'Chuchi.", "se_deplacer", "cuisine"), ("Lueg dr Tisch a.", "regarder", "table"), ("Stopp!", "arreter", None),
    ("Gang zum Igang.", "se_deplacer", "entree"), ("Nimm d'Fläsche.", "saisir", "bouteille"), ("Chum uf d'Bühni.", "se_deplacer", "scene"),
]


def main(langue: str, prenom: str = "equipe") -> int:
    from .audio import ecrire
    from .peripheriques import MicroMac

    ordres = ORDRES_SUISSE_ALLEMAND if langue == "gsw" else ORDRES.get(langue)
    if not ordres:
        print(f"Pas de phrases prévues pour « {langue} ». Langues : gsw, {', '.join(ORDRES)}")
        return 1
    print("Votre voix sera enregistrée et gardée SUR CET ORDINATEUR seulement (dossier donnees_voix/equipe/),")
    print("pour mesurer l'écoute du robot. Elle n'est pas envoyée dans le dépôt. On peut l'effacer à tout moment.")
    if input("Tapez « oui » pour accepter : ").strip().lower() != "oui":
        return 0
    dossier = RACINE / "donnees_voix" / "equipe" / langue
    dossier.mkdir(parents=True, exist_ok=True)
    meta_chemin = dossier / "textes.json"
    meta = json.loads(meta_chemin.read_text(encoding="utf-8")) if meta_chemin.exists() else []

    async def une_phrase() -> np.ndarray | None:
        micro, det = MicroMac(), DetecteurParole(silence_fin_ms=800)
        try:
            async for m in micro.morceaux():
                finies = det.ajouter(m)
                if finies:
                    return finies[0].son
        finally:
            micro.fermer()
        return None

    for texte, action, cible in ordres:
        input(f"\nPhrase : « {texte} »\nAppuyez sur Entrée, puis dites-la (le micro s'arrête tout seul après un silence).")
        son = asyncio.run(asyncio.wait_for(une_phrase(), 10))
        if son is None:
            print("Rien entendu, phrase sautée.")
            continue
        nom = f"{prenom}_{len(meta):03d}.wav"
        ecrire(dossier / nom, son)
        meta.append({"fichier": nom, "texte": texte, "action": action, "cible": cible, "prenom": prenom})
        meta_chemin.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Gardé : {nom} ({len(son) / 16000:.1f} s)")
    print(f"\nFini. Lancer le banc : python3 lancer.py banc-voix")
    return 0
