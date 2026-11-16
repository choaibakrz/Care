"""Brique 7 — Idée 9 : le vote du public change une règle du gardien.

Les questions et les choix sont écrits à l'avance dans regles.yaml (section `votes`). Quelqu'un de l'équipe compte
les voix (mains levées, papiers, application) et les donne au robot (écran, bouton protégé par le code d'équipe).
Le choix qui a le plus de voix gagne. Égalité, ou aucune voix : rien ne change.
Un vote ne peut jamais dépasser les limites de reglages.yaml (securite) : le gardien le refuse.
"""
from __future__ import annotations

from typing import Any


def depouiller(resultats: dict[str, int]) -> str | None:
    """Le choix gagnant, ou None (égalité, ou aucune voix)."""
    if not resultats:
        return None
    meilleur = max(resultats.values())
    gagnants = [c for c, n in resultats.items() if n == meilleur]
    return gagnants[0] if meilleur > 0 and len(gagnants) == 1 else None


async def appliquer_vote(gardien, vote_id: str, resultats: dict[str, int], qui: str = "vote du public") -> dict[str, Any]:
    """Appliquer le résultat d'un vote. Rend {"gagnant", "change", "phrase"}. Lève ValueError (en français)."""
    vote = gardien.regles.vote(vote_id)
    if vote is None:
        raise ValueError(f"vote inconnu « {vote_id} » (voir regles.yaml → votes)")
    inconnus = set(resultats) - set(vote.choix)
    if inconnus:
        raise ValueError(f"choix inconnus {sorted(inconnus)} ; choix possibles : {sorted(vote.choix)}")
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in resultats.values()):
        raise ValueError("le nombre de voix doit être un nombre entier, zéro ou plus")
    gagnant = depouiller(resultats)
    regle = gardien.regles.regle(vote.regle)
    if gagnant is None:
        await gardien.bus.emettre("note", "vote", texte=f"vote « {vote.question} » : égalité, rien ne change",
                                  vote=vote.id, resultats=dict(resultats))
        return {"gagnant": None, "change": False, "phrase": regle.phrase if regle else ""}
    choix = vote.choix[gagnant]
    nouvelle = await gardien.changer_regle(
        vote.regle, active=choix.active, valeurs=choix.valeurs or None, qui=qui, comment="vote du public",
        vote={"id": vote.id, "question": vote.question, "resultats": dict(resultats), "gagnant": gagnant,
              "texte": choix.texte})
    return {"gagnant": gagnant, "change": True, "phrase": nouvelle.phrase, "active": nouvelle.active}
