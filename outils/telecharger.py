#!/usr/bin/env python3
"""Télécharger les modèles du catalogue, APRÈS un « oui » tapé par une personne.

    python3 outils/telecharger.py --liste                 voir la liste et les tailles, sans rien télécharger
    python3 outils/telecharger.py                         demander groupe par groupe (leger, secours, mesure)
    python3 outils/telecharger.py --seulement voix-fr     un seul élément (demande quand même)

- Reprend un téléchargement coupé là où il s'était arrêté.
- Vérifie l'empreinte (sha256 ou md5) de chaque fichier : un fichier abîmé est refusé.
- Vérifie la place libre sur le disque avant de commencer.
- N'accepte aucune condition d'utilisation : si un dépôt en demande, il s'arrête et le dit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[1]
CATALOGUE = Path(__file__).with_name("catalogue.yaml")
DOSSIER = RACINE / "modeles"
HF = "https://huggingface.co"


def go(octets: float) -> str:
    return f"{octets / 1e9:.2f} Go" if octets >= 1e8 else f"{octets / 1e6:.0f} Mo"


def fichiers_de(entree: dict) -> list[dict]:
    """La liste des fichiers d'une entrée (pour un dépôt entier, on la demande à Hugging Face)."""
    if "fichiers" in entree:
        return entree["fichiers"]
    url = f"{HF}/api/models/{entree['depot']}/revision/{entree['revision']}?blobs=true"
    with urllib.request.urlopen(url, timeout=30) as r:
        info = json.load(r)
    if info.get("gated"):
        raise PermissionError(f"{entree['depot']} demande d'accepter des conditions : à faire par une personne, pas par ce script.")
    liste = []
    for s in info.get("siblings", []):
        if s["rfilename"] in (".gitattributes",):
            continue
        lfs = s.get("lfs") or {}
        liste.append({"nom": s["rfilename"], "octets": s.get("size") or 0, "sha256": lfs.get("sha256")})
    return liste


def taille(entree: dict) -> int:
    if "fichiers" in entree:
        return sum(f.get("octets", 0) for f in entree["fichiers"])
    return int(entree.get("octets_total", 0))


def empreinte_ok(chemin: Path, f: dict) -> bool:
    if not chemin.exists() or (f.get("octets") and chemin.stat().st_size != f["octets"]):
        return False
    if f.get("sha256"):
        h, attendu = hashlib.sha256(), f["sha256"]
    elif f.get("md5"):
        h, attendu = hashlib.md5(), f["md5"]
    else:
        return True  # petit fichier sans empreinte publiée : on se fie à la taille
    with open(chemin, "rb") as fh:
        for bloc in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest() == attendu


def telecharger_fichier(entree: dict, f: dict) -> Path:
    destination = DOSSIER / entree["id"] / f["nom"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if empreinte_ok(destination, f):
        print(f"    déjà là et vérifié : {f['nom']}")
        return destination
    partiel = destination.with_name(destination.name + ".partiel")
    deja = partiel.stat().st_size if partiel.exists() else 0
    url = f"{HF}/{entree['depot']}/resolve/{entree['revision']}/{f['nom']}"
    req = urllib.request.Request(url, headers={"Range": f"bytes={deja}-"} if deja else {})
    try:
        r = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise PermissionError(f"{entree['depot']} refuse l'accès ({e.code}) : il faut peut-être accepter des conditions. "
                                  "À faire par une personne, avec son compte.") from e
        raise
    mode = "ab" if deja and r.status == 206 else "wb"
    total = f.get("octets") or 0
    recu = deja if mode == "ab" else 0
    with r, open(partiel, mode) as out:
        while True:
            bloc = r.read(1 << 20)
            if not bloc:
                break
            out.write(bloc)
            recu += len(bloc)
            if total:
                print(f"\r    {f['nom'][-40:]:40} {100 * recu / total:5.1f} %  ({go(recu)} / {go(total)})", end="", flush=True)
    print()
    partiel.rename(destination)
    if not empreinte_ok(destination, f):
        destination.unlink()
        raise ValueError(f"Empreinte fausse pour {f['nom']} : fichier supprimé. Relancer le script.")
    print(f"    vérifié : {f['nom']}")
    return destination


def demander(question: str) -> bool:
    try:
        return input(f"{question} Tapez « oui » pour accepter : ").strip().lower() == "oui"
    except EOFError:
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--liste", action="store_true")
    p.add_argument("--seulement", help="identifiant d'un élément du catalogue")
    p.add_argument("--groupes", default="leger,secours,mesure")
    args = p.parse_args()

    entrees = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))["modeles"]
    print("\nCatalogue (rien n'est téléchargé sans votre « oui ») :")
    for e in entrees:
        print(f"  {e['id']:20} {e['groupe']:8} {go(taille(e)):>9}  {e['role']:32} {e['licence'][:60]}")
    if args.liste:
        return 0

    choix = [e for e in entrees if (args.seulement and e["id"] == args.seulement)
             or (not args.seulement and e["groupe"] in args.groupes.split(","))]
    groupes: dict[str, list[dict]] = {}
    for e in choix:
        groupes.setdefault(e["groupe"], []).append(e)

    DOSSIER.mkdir(exist_ok=True)
    erreurs = 0
    for groupe, liste in groupes.items():
        total = sum(taille(e) for e in liste)
        libre = shutil.disk_usage(DOSSIER).free
        print(f"\nGroupe « {groupe} » : {len(liste)} élément(s), {go(total)}. Place libre : {go(libre)}.")
        if total > 500e6:
            print("  Attention : plus de 500 Mo.")
        if total > libre * 0.9:
            print("  Pas assez de place sur le disque. Groupe sauté.")
            continue
        if not demander(f"  Télécharger le groupe « {groupe} » ?"):
            print("  Sauté.")
            continue
        for e in liste:
            print(f"  → {e['id']} ({e['depot']})")
            try:
                for f in fichiers_de(e):
                    telecharger_fichier(e, f)
            except Exception as ex:  # on continue avec les autres, et on le dit
                erreurs += 1
                print(f"  ✘ {e['id']} : {ex}")
    print("\nTerminé." if not erreurs else f"\nTerminé avec {erreurs} erreur(s) (voir plus haut).")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
