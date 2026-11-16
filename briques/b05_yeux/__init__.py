"""Brique 5 — Les yeux : ce que la caméra voit (personnes, objets, marqueurs ArUco, textes).

Les yeux ne commandent JAMAIS le robot : ils donnent des informations au gardien (personnes vues, et la zone vue)
et au cerveau (objets vus). Tout ordre passe toujours par cerveau → gardien (ticket) → prise → adaptateur.
Ce fichier reste léger (aucun calcul d'image) : le système le lit même quand les yeux sont éteints.
"""
from __future__ import annotations


class ReglageRefuse(ValueError):
    """Un réglage des yeux qui ne doit pas servir tant qu'il n'est pas relu : le programme ne démarre pas."""


def verifier_reglages(reglages_yeux: dict | None) -> None:
    """Refuser de démarrer avec `yeux.gardien_vrai_robot` autre que false (décision de la relecture sécurité du lot D)."""
    valeur = (reglages_yeux or {}).get("gardien_vrai_robot")
    if valeur not in (None, False):
        raise ReglageRefuse(
            f"reglages.yaml → yeux.gardien_vrai_robot: {valeur!r} est REFUSÉ pour l'instant. Avec un vrai robot, la "
            "caméra ne voit que devant elle, et ce choix n'a pas encore été relu par le relecteur sécurité ni décidé "
            "par Hiba. Remettre « gardien_vrai_robot: false » : le gardien demandera un humain avant chaque mouvement.")
