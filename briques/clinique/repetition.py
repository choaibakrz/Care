"""La grande répétition : le scénario entier, étape par étape (cahier, partie 8).

    python3 lancer.py repetition

Une ligne par étape, avec son étiquette, puis « RÉPÉTITION : RÉUSSIE » ou « RÉPÉTITION : RATÉE — (ce qui manque) ».

Trois garde-fous :
  - jamais « RÉUSSIE » si une étape manque, rate ou est sautée ;
  - une pièce qui n'est pas construite compte comme ratée : c'est normal ;
  - une étape ne réussit que si sa pièce répond un Resultat(True, étiquette connue, détail).

Chaque pièce de la clinique, quand elle est construite, ajoute son contrôle dans CONTROLES (numéro de l'étape →
fonction sans argument qui joue l'étape à travers les vraies pièces, sur le faux robot, et rend un Resultat).
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

ETIQUETTES = ("RÉEL", "FAUX ROBOT", "SIMULÉ", "FAUX ROBOT — SIMULÉ", "JOUÉ")


@dataclass(frozen=True)
class Etape:
    numero: int
    titre: str
    piece: str  # la pièce qui joue cette étape (pour savoir quoi construire quand elle manque)


@dataclass(frozen=True)
class Resultat:
    reussie: bool
    etiquette: str  # une des ETIQUETTES : dit vrai sur ce qui a servi
    detail: str  # ce qui a été vu, en quelques mots
    # facultatif : ce que l'étape a compté (pour la fiche de vérité), et « a_afficher » : des lignes à écrire dessous
    mesures: dict[str, Any] = field(default_factory=dict)


ETAPES = [
    Etape(1, "L'arrivée en italien reçoit une réponse en italien, avec la chambre et le programme.", "l'accueil"),
    Etape(2, "Dans le hall, le robot refuse de parler de santé.", "l'accueil"),
    Etape(3, "L'étage est prévenu.", "l'accueil"),
    Etape(4, "Les trois papiers sont proposés au bon endroit, puis validés.", "les papiers"),
    Etape(5, "La feuille sans nom n'est pas rangée.", "les papiers"),
    Etape(6, "La liste « installation » s'affiche avec les habitudes.", "les listes de soin"),
    Etape(7, "Cinq points cochés, puis « Il reste un point : la sonnette ».", "les listes de soin"),
    Etape(8, "« Il manque un coussin » : question, livraison, point coché.", "la demande au robot"),
    Etape(9, "Le soir : les deux questions de la patiente arrivent chez le médecin.", "les questions du soir"),
    Etape(10, "Le lendemain : le résumé, chaque ligne avec sa source.", "le résumé du médecin"),
    Etape(11, "La dictée devient une tâche pour le thérapeute.", "la dictée du médecin"),
    Etape(12, "Un robot tombe en panne, un autre reprend.", "la flotte"),
    Etape(13, "La fiche de vérité est complète.", "la fiche de vérité"),
    Etape(14, "Pendant tout le scénario, le prototype n'a rien envoyé hors de l'ordinateur.", "tout le scénario"),
]

# Rempli par les pièces au fil des tâches. Vide = rien n'est construit.
CONTROLES: dict[int, Callable[[], Resultat]] = {}


def _etape_7() -> Resultat:
    from .listes import etape_7  # chargé au dernier moment : la pièce a besoin de Resultat, défini plus haut

    return etape_7()


def _etape_6() -> Resultat:
    from .ecrans_listes import etape_6

    return etape_6()


def _etape_8() -> Resultat:
    from .coursier import etape_8

    return etape_8()


def _etape_10() -> Resultat:
    from .ecrans_resume import etape_10

    return etape_10()


def _etape_4() -> Resultat:
    from .ecrans_papiers import etape_4

    return etape_4()


def _etape_5() -> Resultat:
    from .ecrans_papiers import etape_5

    return etape_5()


def _etape_1() -> Resultat:
    from .ecrans_accueil import etape_1

    return etape_1()


def _etape_2() -> Resultat:
    from .ecrans_accueil import etape_2

    return etape_2()


def _etape_3() -> Resultat:
    from .ecrans_accueil import etape_3

    return etape_3()


def _etape_9() -> Resultat:
    from .ecrans_soir import etape_9

    return etape_9()


def _etape_11() -> Resultat:
    from .ecrans_soir import etape_11

    return etape_11()


def _etape_12() -> Resultat:
    from .flotte import etape_12

    return etape_12()


def _etape_13() -> Resultat:
    from .fiche import etape_13

    return etape_13()


def _etape_14() -> Resultat:
    from .rien_dehors import etape_14

    return etape_14()


CONTROLES[1] = _etape_1
CONTROLES[13] = _etape_13
CONTROLES[14] = _etape_14
CONTROLES[12] = _etape_12
CONTROLES[9] = _etape_9
CONTROLES[11] = _etape_11
CONTROLES[2] = _etape_2
CONTROLES[3] = _etape_3
CONTROLES[4] = _etape_4
CONTROLES[5] = _etape_5
CONTROLES[6] = _etape_6
CONTROLES[10] = _etape_10
CONTROLES[8] = _etape_8
CONTROLES[7] = _etape_7


class Seance:
    """Ce qui s'est passé pendant UNE répétition : l'issue de chaque étape, les sauts de l'horloge, le réseau.
    La fiche de vérité (étape 13) et « rien n'est sorti de l'ordinateur » (étape 14) se calculent là-dessus."""

    def __init__(self) -> None:
        self.issues: dict[int, str] = {}  # numéro → « reussie », « ratee » ou « manquante »
        self.resultats: dict[int, Resultat] = {}  # numéro → ce que la pièce a rendu (si elle a rendu un Resultat)
        self.sauts: int | None = None  # sauts de l'horloge du scénario ; None : pas d'horloge (non mesuré)
        self.reseau: Any = None  # la surveillance des connexions vers l'extérieur (rien_dehors.py)
        self.aide: Any = None  # T27 : le compte des aides humaines, des reprises et des constats (aide_humaine.Compte)
        self.admin: dict[str, int] | None = None  # T27 : les messages du faux logiciel lus pendant la séance
        self.par_etape: dict[int, tuple[int, int]] = {}  # numéro → (aides, reprises imprévues) arrivées pendant l'étape
        self._deja = (0, 0)

    def noter(self, numero: int, issue: str, resultat: Any = None) -> None:
        self.issues[numero] = issue
        if self.aide is not None:  # ce qui est arrivé depuis l'étape d'avant appartient à cette étape
            maintenant = (len(self.aide.aides), self.aide.reprises_imprevues)
            self.par_etape[numero] = (maintenant[0] - self._deja[0], maintenant[1] - self._deja[1])
            self._deja = maintenant
        if isinstance(resultat, Resultat):
            self.resultats[numero] = resultat

    def jouees(self, numeros: range) -> bool:
        """Toutes ces étapes ont été jouées par leur pièce (réussies ou ratées, mais pas manquantes)."""
        return all(self.issues.get(n) in ("reussie", "ratee") for n in numeros)


SEANCE: Seance | None = None  # la répétition en cours, s'il y en a une

# Les petits changements d'un essai compté (essais.py) : la langue d'arrivée, le point oublié, l'objet demandé.
# None : le scénario du cahier, tel quel (italien, la sonnette, un coussin).
VARIATION: dict[str, Any] | None = None


@contextmanager
def variation(changements: dict[str, Any]) -> Iterator[None]:
    """Le temps d'un essai : les étapes 1, 7 et 8 lisent ces changements. Après, tout redevient comme le cahier."""
    global VARIATION
    VARIATION = dict(changements)
    try:
        yield
    finally:
        VARIATION = None


def changement(cle: str, sinon: Any = None) -> Any:
    return sinon if VARIATION is None or VARIATION.get(cle) is None else VARIATION[cle]


@contextmanager
def seance() -> Iterator[Seance]:
    """Le temps d'une répétition : on note tout, et on surveille (et bloque) toute connexion vers l'extérieur."""
    global SEANCE
    from .rien_dehors import Surveillance

    en_cours = Seance()
    en_cours.reseau = Surveillance()
    SEANCE = en_cours
    from . import aide_humaine, traducteur

    try:
        with en_cours.reseau, aide_humaine.compter() as aide, traducteur.compter() as admin:
            en_cours.aide, en_cours.admin = aide, admin
            yield en_cours
    finally:
        SEANCE = None


def _noter(numero: int, issue: str, resultat: Any = None) -> str:
    if SEANCE is not None:
        SEANCE.noter(numero, issue, resultat)
    return issue


def jouer_etape(etape: Etape, controles: dict[int, Callable[[], Resultat]], ecrire: Callable[[str], None]) -> str:
    """Joue une étape et écrit sa ligne. Rend « reussie », « manquante » ou « ratee »."""
    controle = controles.get(etape.numero)
    if controle is None:
        ecrire(f"{etape.numero:>2}. [—] pas encore construite ({etape.piece}) — {etape.titre}")
        return _noter(etape.numero, "manquante")
    try:
        resultat = controle()
    except Exception as erreur:  # une pièce cassée ne doit jamais arrêter la répétition ni passer pour un succès
        ecrire(f"{etape.numero:>2}. [—] RATÉE — {etape.titre} ({type(erreur).__name__} : {erreur})")
        return _noter(etape.numero, "ratee")
    issue = "ratee"
    if not isinstance(resultat, Resultat):
        ecrire(f"{etape.numero:>2}. [—] RATÉE — {etape.titre} (étape sautée : la pièce n'a pas rendu de résultat)")
    elif resultat.etiquette not in ETIQUETTES:
        ecrire(f"{etape.numero:>2}. [—] RATÉE — {etape.titre} (étiquette absente ou inconnue : « {resultat.etiquette} »)")
    elif resultat.reussie is not True:
        ecrire(f"{etape.numero:>2}. [{resultat.etiquette}] RATÉE — {etape.titre} ({resultat.detail})")
    else:
        ecrire(f"{etape.numero:>2}. [{resultat.etiquette}] réussie — {etape.titre} ({resultat.detail})")
        issue = "reussie"
    if isinstance(resultat, Resultat):
        for ligne in resultat.mesures.get("a_afficher") or ():  # la fiche de vérité s'écrit sous son étape, réussie ou non
            ecrire(f"    · {ligne}")
    return _noter(etape.numero, issue, resultat)


def conclure(manquantes: list[int], ratees: list[int], ecrire: Callable[[str], None]) -> int:
    """Écrit la dernière ligne. Rend 0 seulement si aucune étape ne manque et aucune n'a raté."""
    if not manquantes and not ratees:
        ecrire("RÉPÉTITION : RÉUSSIE")
        return 0
    morceaux = []
    if manquantes:
        morceaux.append(f"{len(manquantes)} étape{'s' if len(manquantes) > 1 else ''} "
                        f"manquante{'s' if len(manquantes) > 1 else ''}")
    if ratees:
        morceaux.append(f"étape{'s' if len(ratees) > 1 else ''} ratée{'s' if len(ratees) > 1 else ''} : "
                        + ", ".join(str(n) for n in ratees))
    ecrire("RÉPÉTITION : RATÉE — " + " ; ".join(morceaux))
    return 1


def jouer(controles: dict[int, Callable[[], Resultat]] | None = None, ecrire: Callable[[str], None] = print) -> int:
    """Joue les quatorze étapes, sans les scènes. Rend 0 si tout a réussi, 1 sinon.

    La commande « python3 lancer.py repetition » passe par le scénario (chef_clinique.py) : les mêmes étapes,
    rangées en sept scènes, à l'heure du scénario, avec le plan B de chaque scène.
    """
    controles = CONTROLES if controles is None else controles
    ecrire("LA GRANDE RÉPÉTITION — la clinique en boîte — DONNÉES INVENTÉES")
    manquantes: list[int] = []
    ratees: list[int] = []
    with seance():
        for etape in ETAPES:
            issue = jouer_etape(etape, controles, ecrire)
            if issue == "manquante":
                manquantes.append(etape.numero)
            elif issue != "reussie":
                ratees.append(etape.numero)
    return conclure(manquantes, ratees, ecrire)


def main(reste: list[str] | None = None) -> int:
    from .chef_clinique import jouer as jouer_le_scenario  # les sept scènes, chacune avec son plan B

    return jouer_le_scenario()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
