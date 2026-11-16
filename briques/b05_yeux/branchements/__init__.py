"""Les branchements des yeux : un fichier par outil. Chacun dit s'il manque (preparer) et ne fait jamais tomber les autres."""
from __future__ import annotations

from commun.monde import Monde

from ..marqueurs import ListeMarqueurs
from ..prise_yeux import Branchement

CONNUS = ("simule", "aruco", "mediapipe", "rapidocr")


def fabriquer(noms: list[str], monde: Monde, marqueurs: ListeMarqueurs, reglages: dict | None = None) -> list[Branchement]:
    """Les branchements demandés dans reglages.yaml → yeux.branchements. Un nom inconnu : une erreur claire."""
    r = reglages or {}
    inconnus = [n for n in noms if n not in CONNUS]
    if inconnus:
        raise ValueError(f"Branchement des yeux inconnu : {inconnus} (connus : {', '.join(CONNUS)})")
    sortie: list[Branchement] = []
    for nom in noms:
        if nom == "simule":
            from .simule import BranchementSimule

            sortie.append(BranchementSimule(monde))
        elif nom == "aruco":
            from .aruco import BranchementAruco

            sortie.append(BranchementAruco(marqueurs))
        elif nom == "mediapipe":
            from .mediapipe_objets import BranchementMediaPipe

            sortie.append(BranchementMediaPipe(monde, r.get("modele_mediapipe"), float(r.get("confiance_min", 0.4))))
        elif nom == "rapidocr":
            from .rapidocr_textes import BranchementRapidOCR

            sortie.append(BranchementRapidOCR(monde, float(r.get("confiance_min_textes", 0.6))))
    return sortie


def nom_du_monde(etiquette: str, monde: Monde) -> str | None:
    """« bottle » → « bouteille » : l'objet du monde dont un nom (dans n'importe quelle langue) est cette étiquette."""
    e = etiquette.strip().lower()
    for o in monde.objets:
        if any(n.lower() == e for _, n in o.tous_les_noms()) or o.id == e:
            return o.id
    return None
