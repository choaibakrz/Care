"""Télécharger le modèle de MediaPipe pour les yeux, APRÈS un « oui » tapé par une personne.

    .venv/bin/python -m briques.b05_yeux.telecharger_modele              (4,6 Mo, demande « oui »)
    .venv/bin/python -m briques.b05_yeux.telecharger_modele --depuis F   (copier un fichier déjà téléchargé, vérifié)

Modèle : EfficientDet-Lite0 (version 1, compressé « int8 »), publié par Google pour MediaPipe. 80 sortes d'objets
(jeu COCO), dont personne, bouteille, tasse, valise. Licence : Apache-2.0 d'après son origine (dépôt google/automl,
lu le 11.11.2026) ; la fiche du modèle sur le site de MediaPipe n'a pas pu être lue (page bloquée) : À VÉRIFIER.
Empreinte relevée le 11.11.2026 (identique à la version « latest » ce jour-là).
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
URL = "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite"
OCTETS = 4_602_795
SHA256 = "0720bf247bd76e6594ea28fa9c6f7c5242be774818997dbbeffc4da460c723bb"
DESTINATION = RACINE / "modeles" / "mediapipe-efficientdet-lite0" / "efficientdet_lite0.tflite"


def empreinte_ok(chemin: Path) -> bool:
    """Le fichier a-t-il exactement la taille et l'empreinte (sha256) relevées ? Lu aussi au chargement (MediaPipe)."""
    if not chemin.exists() or chemin.stat().st_size != OCTETS:
        return False
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest() == SHA256


def installer(source: Path | None = None) -> Path:
    """Copier `source` (déjà téléchargé) ou télécharger dans un fichier « .partiel », vérifier SON empreinte, et
    seulement alors le mettre à sa place. Un fichier faux est supprimé : l'ancien modèle (s'il y en a un) reste."""
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    partiel = DESTINATION.with_name(DESTINATION.name + ".partiel")
    try:
        if source is not None:
            shutil.copyfile(source, partiel)
        else:
            with urllib.request.urlopen(URL, timeout=60) as r, open(partiel, "wb") as out:
                shutil.copyfileobj(r, out)
        if not empreinte_ok(partiel):
            raise ValueError("Empreinte fausse : fichier supprimé, rien n'est remplacé. Relancer.")
        partiel.replace(DESTINATION)
    finally:
        partiel.unlink(missing_ok=True)
    return DESTINATION


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Modèle de MediaPipe pour les yeux (brique 5).")
    p.add_argument("--depuis", type=Path, help="un fichier déjà téléchargé à copier (l'empreinte est vérifiée)")
    args = p.parse_args(argv)
    if empreinte_ok(DESTINATION):
        print(f"Déjà là et vérifié : {DESTINATION}")
        return 0
    print(f"Modèle EfficientDet-Lite0 pour MediaPipe : {OCTETS / 1e6:.1f} Mo. Licence : Apache-2.0 (à vérifier, voir l'aide).")
    if args.depuis is None:
        print(f"Source : {URL}")
        try:
            if input("Tapez « oui » pour télécharger : ").strip().lower() != "oui":
                print("Rien téléchargé.")
                return 1
        except EOFError:
            print("Rien téléchargé (pas de réponse).")
            return 1
    print(f"Vérifié et rangé : {installer(args.depuis)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
