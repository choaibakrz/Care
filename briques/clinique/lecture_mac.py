"""Lire une image sur l'iMac avec la lecture de texte déjà présente dans le Mac (tâche R3, autorisation B de Hiba).

    from briques.clinique import lecture_mac
    lecture_mac.lire_image("papier.png")        → {"texte", "lignes": [{"texte", "confiance"}…], "outil", "duree_s"}
    (la confiance d'une ligne est celle d'une seconde lecture, sans correction automatique : elle est plus franche)
    python3 -m briques.clinique.lecture_mac IMAGE.png      lire une image
    python3 -m briques.clinique.lecture_mac --essai        fabriquer une image d'essai, la lire, mesurer l'erreur

- L'outil : le cadre « Vision » de macOS, par un petit programme Swift (outils/lecture_mac.swift), construit une fois
  avec le compilateur déjà sur le Mac (Xcode). RIEN N'EST INSTALLÉ, rien n'est téléchargé.
- La lecture se fait sur l'ordinateur (c'est ce que dit Apple pour cette fonction ; nous ne l'avons pas vérifié en
  écoutant le réseau : à vérifier).
- Ce module ne range rien : il lit. Le rangement d'un papier lu depuis une image, et la mesure du taux d'erreur sur les
  documents du faux dossier, viennent avec la tâche T15.
- Sur une machine qui n'est pas un Mac, ou sans compilateur Swift : `disponible()` dit pourquoi, rien ne casse.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[2]
SOURCE = RACINE / "outils" / "lecture_mac.swift"
BINAIRE = RACINE / "outils" / "bin" / "lecture_mac"
OUTIL = "lecture de texte du Mac (Vision, macOS)"


class LectureImpossible(RuntimeError):
    """L'image n'a pas pu être lue. Le message dit pourquoi."""


def disponible() -> tuple[bool, str]:
    """La lecture du Mac peut-elle servir ici ? Rend (oui/non, la raison si c'est non)."""
    if sys.platform != "darwin":
        return False, "cet ordinateur n'est pas un Mac"
    if not SOURCE.exists():
        return False, f"le programme {SOURCE.name} manque"
    if not BINAIRE.exists() and shutil.which("swiftc") is None:
        return False, "le compilateur Swift (Xcode) n'est pas sur ce Mac"
    return True, ""


def _binaire() -> Path:
    """Le petit programme, construit une fois (quelques secondes), et refait si sa source a changé."""
    oui, raison = disponible()
    if not oui:
        raise LectureImpossible(raison)
    if not BINAIRE.exists() or BINAIRE.stat().st_mtime < SOURCE.stat().st_mtime:
        BINAIRE.parent.mkdir(parents=True, exist_ok=True)
        fait = subprocess.run(["swiftc", "-O", str(SOURCE), "-o", str(BINAIRE)], capture_output=True, text=True, timeout=300)
        if fait.returncode != 0:
            raise LectureImpossible("le programme de lecture ne se construit pas : " + fait.stderr.strip()[-300:])
    return BINAIRE


def lire_image(chemin: str | Path) -> dict[str, Any]:
    """Le texte d'une image, ligne par ligne, de haut en bas, avec la confiance de chaque ligne (de 0 à 1)."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise LectureImpossible(f"image absente : {chemin.name}")
    debut = time.monotonic()
    fait = subprocess.run([str(_binaire()), "lire", str(chemin)], capture_output=True, text=True, timeout=60)
    if fait.returncode != 0:
        raise LectureImpossible(fait.stderr.strip() or f"le programme de lecture a rendu le code {fait.returncode}")
    try:
        reponse = json.loads(fait.stdout)
        brutes = reponse.get("sans_correction") or []
        lignes = []
        for l in reponse["lignes"]:
            # La confiance franche : celle de la passe SANS correction, pour la ligne à la même hauteur dans l'image.
            # (Avec la correction, la lecture du Mac annonce presque toujours 1, même quand elle se trompe.)
            proches = [b for b in brutes if abs(float(b["y"]) - float(l["y"])) <= max(0.012, float(l.get("hauteur", 0)) / 2)]
            brute = min(proches, key=lambda b: abs(float(b["y"]) - float(l["y"])), default=None)
            lignes.append({"texte": str(l["texte"]),
                           "confiance": round(float(brute["confiance"]), 3) if brute else 0.0,
                           "confiance_annoncee": round(float(l["confiance"]), 3),
                           "sans_correction": str(brute["texte"]) if brute else None})
    except (ValueError, KeyError, TypeError) as erreur:
        raise LectureImpossible(f"réponse illisible du programme de lecture ({type(erreur).__name__})")
    return {"texte": "\n".join(l["texte"] for l in lignes), "lignes": lignes, "outil": OUTIL,
            "confiance_min": min((l["confiance"] for l in lignes), default=None),
            "duree_s": round(time.monotonic() - debut, 2)}


def dessiner_texte(texte: str, sortie: str | Path, police: str = "Helvetica", taille: int = 30, travers: str = "") -> Path:
    """Fabrique une image d'essai : le texte, noir sur blanc. Pour les essais et pour T15 (jamais un vrai papier).
    `police` : une police du Mac (une police d'écriture imite un papier rempli à la main) ; `travers` : un mot écrit
    en travers, en gris (« INVENTÉ »)."""
    sortie = Path(sortie)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(texte)
    try:
        fait = subprocess.run([str(_binaire()), "dessiner", f.name, str(sortie), police, str(taille), travers],
                              capture_output=True, text=True, timeout=60)
    finally:
        Path(f.name).unlink(missing_ok=True)
    if fait.returncode != 0 or not sortie.exists():
        raise LectureImpossible("l'image d'essai n'a pas pu être fabriquée : " + fait.stderr.strip()[-200:])
    return sortie


def _propre(texte: str) -> str:
    return " ".join(str(texte).split())


def taux_d_erreur(lu: str, reference: str) -> float:
    """Le taux d'erreur de lecture, par caractère : combien de caractères à changer, ajouter ou enlever pour retrouver
    le texte de référence, divisé par sa longueur (espaces et retours à la ligne comptés une fois). 0 = parfait."""
    a, b = _propre(lu), _propre(reference)
    if not b:
        return 0.0 if not a else 1.0
    avant = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        ligne = [i]
        for j, cb in enumerate(b, 1):
            ligne.append(min(avant[j] + 1, ligne[j - 1] + 1, avant[j - 1] + (ca != cb)))
        avant = ligne
    return round(min(1.0, avant[-1] / len(b)), 4)


def essai(texte: str | None = None, dossier: str | Path | None = None) -> dict[str, Any]:
    """Fabrique une image d'un texte inventé, la lit, et mesure le taux d'erreur. Rien n'est tapé à la main."""
    texte = texte or ("INVENTÉ — Studio medico Exemple, Dott. Exemple.\nLettera per la signora Giulia B.\n"
                      "Carte d'assurée : Assurance Exemple, numéro inventé EX-0000-0012.\n"
                      "Rappel : apporter des chaussures fermées pour la séance.")
    with tempfile.TemporaryDirectory() as temporaire:
        image = dessiner_texte(texte, Path(dossier or temporaire) / "essai_lecture.png")
        lu = lire_image(image)
    return {**lu, "reference": texte, "taux_d_erreur": taux_d_erreur(lu["texte"], texte)}


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    oui, raison = disponible()
    if not oui:
        print(f"Lecture du Mac indisponible : {raison}.")
        return 2
    try:
        if arguments == ["--essai"]:
            r = essai()
            print(f"ESSAI DE LECTURE — {r['outil']} — image fabriquée par le programme, texte inventé, tapé (pas écrit à la main)")
            print(r["texte"])
            print(f"taux d'erreur de lecture : {r['taux_d_erreur'] * 100:.1f} % ({len(r['lignes'])} lignes, {r['duree_s']} s, "
                  f"confiance la plus basse : {r['confiance_min']})")
            return 0
        if len(arguments) != 1:
            print("usage : python3 -m briques.clinique.lecture_mac IMAGE.png | --essai")
            return 2
        r = lire_image(arguments[0])
    except LectureImpossible as erreur:
        print(f"Lecture impossible : {erreur}")
        return 1
    print(r["texte"])
    print(f"— {r['outil']} ; {len(r['lignes'])} lignes ; {r['duree_s']} s ; confiance la plus basse : {r['confiance_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
