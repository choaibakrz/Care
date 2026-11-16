"""Branchement « simule » : la vérité du dessin de la caméra SIMULÉE, à la place d'un vrai détecteur.

La caméra simulée sait ce qu'elle a dessiné et où (une boîte dans l'image). Ce branchement rend exactement ça, comme
le ferait un détecteur parfait : seulement une boîte et un nom, JAMAIS la position dans le monde (elle est
recalculée par la calibration, comme avec une vraie caméra). Avec une vraie caméra, il ne sert à rien (« sans_objet »).
Tout résultat qui en vient est « testé sur caméra simulée », jamais « vu par une vraie caméra ».
"""
from __future__ import annotations

from commun.monde import Monde

from ..prise_yeux import Boite, Branchement, BranchementInutile, ImageCamera, Objet, Personne, Trouvailles


class BranchementSimule(Branchement):
    nom = "simule"
    voit_les_personnes = True
    voit_les_objets = True

    def __init__(self, monde: Monde) -> None:
        self.monde = monde

    def analyser(self, image: ImageCamera) -> Trouvailles:
        if image.verite is None:
            raise BranchementInutile("pas une image de la caméra simulée (vraie caméra : ce branchement ne sert pas)")
        t = Trouvailles()
        for v in image.verite:
            x, y, lg, ht = v["boite"]
            boite = Boite(x=x, y=y, largeur=lg, hauteur=ht)
            if v["sorte"] == "personne":
                t.personnes.append(Personne(boite=boite, confiance=1.0, source="camera_simulee"))
            elif v["sorte"] == "objet":
                t.objets.append(Objet(etiquette=v.get("etiquette") or v["id"], nom=v["id"], boite=boite, confiance=1.0,
                                      source="camera_simulee"))
        return t
