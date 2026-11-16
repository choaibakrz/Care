"""Lire les papiers depuis une image (cahier 5.8 et 6.4, tâche T15).

    python3 lancer.py papiers-images               lit les sept images, range, mesure et affiche le taux d'erreur
    python3 lancer.py papiers-images --fabriquer   refait les images à partir des textes de référence (sur un Mac)

La chaîne : une image du papier → le texte lu → une proposition de rangement → la validation par un humain.
- Les sept images sont dans images_papiers/ : les six documents du cahier et la feuille volante. Elles sont FABRIQUÉES
  par le programme à partir des textes inventés du faux dossier, avec « INVENTÉ » écrit en travers. Ce ne sont pas des
  photos. Le formulaire « rempli à la main » est écrit avec une police d'écriture du Mac, difficile à lire : c'est une
  écriture IMITÉE, pas la main d'une personne.
- La lecture : la lecture de texte du Mac (lecture_mac.py). Deux passes ; la confiance d'une ligne est celle de la
  passe sans correction automatique.
- « Je ne suis pas sûr » : dès qu'une ligne du papier est lue avec une confiance sous le seuil, l'écriture est notée
  « lecture peu sûre », et le rangement n'est jamais « sûr » : l'humain choisit.
- Le mot en travers n'est pas le texte du papier : une ligne qui n'est qu'un morceau de ce mot est écartée.
- Le taux d'erreur de lecture est mesuré contre le texte de référence, par caractère, et affiché. Jamais tapé à la main.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import lecture_mac
from .papiers import proposer

DOSSIER_IMAGES = Path(__file__).resolve().parent / "images_papiers"
FICHIER_MESURE = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "lecture_papiers.json"
TRAVERS = "INVENTÉ"
SEUIL = 0.9  # sous ce seuil, une ligne est « peu sûre » (texte tapé net : 1,0 ; écriture difficile : 0,3 à 0,5 ; mesuré le 12.11.2026)
ECRITURE_SURE, ECRITURE_PEU_SURE = "tapée", "lecture peu sûre"
POLICE_TAPEE, POLICE_A_LA_MAIN = ("Helvetica", 30), ("Zapfino", 22)
# Les six documents du cahier (6.4) et la feuille volante : identifiant du papier → identifiant du patient (ou None).
PAPIERS: dict[str, str | None] = {"p01-d1": "p01", "p01-d2": "p01", "p01-d3": "p01", "p02-d1": "p02", "p03-d1": "p03",
                                  "p04-d1": "p04", "f-01": None}


def _lettres(texte: str) -> str:
    sans = unicodedata.normalize("NFD", texte.upper())
    return "".join(c for c in sans if c.isalpha() and unicodedata.category(c) != "Mn")


def est_le_mot_en_travers(ligne: str) -> bool:
    """Une ligne qui n'est qu'un morceau du mot écrit en travers (« NVENTE », « IVENTÉ »…) : pas du texte du papier."""
    mot, lettres = _lettres(TRAVERS), _lettres(ligne)
    if not 3 <= len(lettres) <= len(mot) + 1 or len(re.sub(r"[\W\d_]", "", ligne)) + 2 < len(ligne.strip()):
        return False
    return lettres in mot or lecture_mac.taux_d_erreur(lettres, mot) <= 0.3


def reference(journal=None) -> dict[str, dict[str, Any]]:
    """Les textes de référence des sept papiers (données inventées), lus PAR LA PORTE (H09, cahier 5.2) : les documents
    avec le badge du soignant de l'étage (il voit ces patients), la feuille sans nom avec le badge de l'accueil."""
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges

    porte, badges = PorteDeLecture(journal=journal or JournalDesAcces()), charger_badges()
    papiers: dict[str, dict[str, Any]] = {}
    for ident, patient in PAPIERS.items():
        if patient is None:
            pour_l_accueil = badges["assistant"].travaille_pour(badges["accueil"])  # H01 : le texte, pour la pièce qui range
            feuille = next(f for f in porte.papiers_a_ranger(pour_l_accueil) if f["id"] == ident)
            papiers[ident] = {"texte": feuille["texte"], "ecriture": feuille.get("ecriture", "tapée"), "patient": None}
        else:
            vue = porte.patient(badges["soignant-etage-2"], patient)
            doc = next(x for x in vue["documents"] if x["id"] == ident)
            papiers[ident] = {"texte": doc["texte"], "ecriture": doc.get("ecriture", "tapée"), "patient": patient,
                              "nom": vue["nom"]}
    return papiers


def fabriquer(dossier: Path = DOSSIER_IMAGES) -> list[Path]:
    """Refait les sept images à partir des textes de référence. Un papier « à la main » est écrit avec une police
    d'écriture difficile. « INVENTÉ » est écrit en travers de chaque image."""
    Path(dossier).mkdir(parents=True, exist_ok=True)
    images = []
    for ident, papier in reference().items():
        police, taille = POLICE_A_LA_MAIN if "main" in papier["ecriture"] else POLICE_TAPEE
        images.append(lecture_mac.dessiner_texte(papier["texte"], Path(dossier) / f"{ident}.png", police, taille, TRAVERS))
    return images


def lire_papier(image: str | Path) -> dict[str, Any]:
    """Le texte d'un papier, lu depuis son image : sans le mot en travers, avec ce que la lecture vaut."""
    lu = lecture_mac.lire_image(image)
    lignes = [l for l in lu["lignes"] if not est_le_mot_en_travers(l["texte"])]
    peu_sures = [l for l in lignes if l["confiance"] < SEUIL]
    return {"texte": "\n".join(l["texte"] for l in lignes), "lignes": lignes,
            "ecriture": ECRITURE_PEU_SURE if peu_sures or not lignes else ECRITURE_SURE,
            "confiance_min": min((l["confiance"] for l in lignes), default=0.0), "lignes_peu_sures": len(peu_sures),
            "lignes_ecartees": len(lu["lignes"]) - len(lignes), "outil": lu["outil"], "duree_s": lu["duree_s"]}


def lecteur(dossier: Path = DOSSIER_IMAGES) -> Callable[[str], dict[str, Any] | None]:
    """Pour la pièce des papiers : identifiant d'un papier → ce que la lecture de son image a donné (None sans image)."""
    def lire(ident: str) -> dict[str, Any] | None:
        image = Path(dossier) / f"{ident}.png"
        return lire_papier(image) if image.exists() else None
    return lire


def mesurer(dossier: Path = DOSSIER_IMAGES, noter: Path | None = None) -> dict[str, Any]:
    """Lit les sept images, propose le rangement (règles de T09, comme avec le texte de référence) et mesure l'erreur."""
    papiers = reference()
    patients = [{"id": p["patient"], "nom": p["nom"]} for p in papiers.values() if p["patient"]]
    patients = list({p["id"]: p for p in patients}.values())
    lignes, erreurs, caracteres = [], 0.0, 0
    for ident, papier in papiers.items():
        lu = lire_papier(Path(dossier) / f"{ident}.png")
        depuis_image = proposer(lu["texte"], lu["ecriture"], patients)
        depuis_texte = proposer(papier["texte"], "tapée", patients)
        taux = lecture_mac.taux_d_erreur(lu["texte"], papier["texte"])
        longueur = len(" ".join(papier["texte"].split()))
        erreurs, caracteres = erreurs + taux * longueur, caracteres + longueur
        lignes.append({"papier": ident, "a_la_main": "main" in papier["ecriture"], "taux_d_erreur": taux,
                       "ecriture_lue": lu["ecriture"], "confiance_min": lu["confiance_min"],
                       "type": depuis_image["type"], "patient": depuis_image["patient"], "endroit": depuis_image["endroit"],
                       "confiance": depuis_image["confiance"], "dit": depuis_image["dit"],
                       "comme_le_texte": all(depuis_image[c] == depuis_texte[c] for c in ("type", "patient", "endroit")),
                       "attendu": {c: depuis_texte[c] for c in ("type", "patient", "endroit")}})
    bilan = {"marque": "données inventées", "outil": lecture_mac.OUTIL, "date": datetime.now().isoformat(timespec="seconds"),
             "images": len(lignes), "taux_d_erreur": round(erreurs / caracteres, 4) if caracteres else None,
             "papiers": lignes, "seuil": SEUIL,
             "note": "images fabriquées par le programme à partir de textes inventés, « INVENTÉ » en travers ; le papier "
                     "« à la main » est écrit avec une police d'écriture ; aucune photo, aucune main"}
    if noter is not None:
        Path(noter).parent.mkdir(parents=True, exist_ok=True)
        Path(noter).write_text(json.dumps(bilan, ensure_ascii=False, indent=1), encoding="utf-8")
    return bilan


def main(reste: list[str] | None = None, ecrire: Callable[[str], None] = print) -> int:
    p = argparse.ArgumentParser(prog="lancer.py papiers-images", description="La clinique en boîte : lire les papiers depuis une image")
    p.add_argument("--fabriquer", action="store_true", help="refaire les sept images à partir des textes de référence")
    a = p.parse_args(reste or [])
    oui, raison = lecture_mac.disponible()
    if not oui:
        ecrire(f"Lecture du Mac indisponible : {raison}. Les papiers gardent leur texte de référence.")
        return 2
    if a.fabriquer:
        images = fabriquer()
        ecrire(f"{len(images)} images refaites dans {DOSSIER_IMAGES} (fabriquées, « {TRAVERS} » en travers).")
    bilan = mesurer(noter=FICHIER_MESURE)
    ecrire(f"LIRE LES PAPIERS DEPUIS UNE IMAGE — {bilan['outil']} — {bilan['images']} images FABRIQUÉES — DONNÉES INVENTÉES")
    ecrire("Pas des photos : des images dessinées par le programme, « INVENTÉ » en travers. Le formulaire « à la main » : une police d'écriture.")
    for l in bilan["papiers"]:
        ecrire(f"- {l['papier']} : erreur de lecture {l['taux_d_erreur'] * 100:.1f} % ; lecture : {l['ecriture_lue']} "
               f"(confiance la plus basse {l['confiance_min']}) ; rangement : {l['type'] or 'type non reconnu'} → "
               f"{l['endroit'] or 'pas rangé'} ; confiance {l['confiance']}"
               + (f" — « {l['dit']} »" if l["dit"] else "")
               + ("" if l["comme_le_texte"] else f" ; DIFFÉRENT du texte de référence (attendu : {l['attendu']})"))
    ecrire(f"taux d'erreur de lecture des papiers : {bilan['taux_d_erreur'] * 100:.1f} % des caractères, sur {bilan['images']} images")
    tapes = [l for l in bilan["papiers"] if not l["a_la_main"] and l["patient"]]
    ecrire(f"papiers tapés rangés comme avec le texte de référence : {sum(l['comme_le_texte'] for l in tapes)} sur {len(tapes)}")
    return 0
