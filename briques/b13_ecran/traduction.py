"""Brique 13 — La deuxième langue des sous-titres.

Deux cas très différents :
1. Ce que dit le ROBOT vient de commun/phrases.yaml (5 langues). L'événement `reponse_dite` porte la clé de la phrase
   et ses valeurs (`cle`, `valeurs`) : on redit la même phrase dans l'autre langue (`Chaine.redire`), sans modèle,
   sans Internet. Exact, instantané.
2. Ce que dit la PERSONNE est libre : le traduire demande un modèle de langue. Ici, AUCUN n'est branché :
   l'écran affiche « traduction indisponible hors ligne » (il ne fait pas semblant).

L'endroit où brancher plus tard une traduction par le cerveau (Apertus, sur ce Mac ou sur l'autre) :
écrire une classe qui suit `Traducteur` (ci-dessous), puis, au lancement :
    app.state.jury.traducteur = MonTraducteurApertus(...)
Idée (à vérifier, jamais essayé) : envoyer au serveur Apertus de la cascade une consigne courte
« Traduis en {langue}. Réponds seulement par la traduction. », avec un délai court (3 s) ; en cas d'échec : None.
Une phrase traduite par un modèle doit rester marquée comme telle à l'écran (« traduit par Apertus »).
"""
from __future__ import annotations

INDISPONIBLE = "traduction indisponible hors ligne"


class Traducteur:
    """Traduire un texte libre. `disponible` faux : rien n'est branché, l'écran le dit."""

    nom = "aucun"
    disponible = False

    async def traduire(self, texte: str, de: str | None, vers: str) -> str | None:
        """Rendre la traduction, ou None si impossible (trop lent, éteint, coupé d'Internet…)."""
        return None


class TraducteurAbsent(Traducteur):
    """Aujourd'hui : aucun modèle de traduction branché."""
