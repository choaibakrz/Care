"""H06a — Le rangement des papiers refait avec le vrai Apertus, et mesuré (demande de Hiba, 12.11.2026).

    python3 lancer.py papiers-apertus          tous les papiers du faux dossier, rangés par le vrai Apertus, mesurés

- Apertus se branche sur la porte déjà écrite pour T14 : `lire(texte, types, patients)`. Sa réponse suit un formulaire
  imposé (le type et le patient sont choisis dans une liste, ou « rien »).
- Sa proposition est ensuite vérifiée contre le papier par `proposer_avec_cerveau` (T14), sans changement : le patient
  est décidé par la règle, la date et l'auteur doivent être recopiés du papier, un désaccord donne « je ne suis pas sûr ».
- La mesure : tous les documents des patients du faux dossier et les feuilles sans nom, lus par la porte. Pour chaque
  papier : ce que le modèle seul a répondu, ce qui reste après vérification, et le temps.
  « Bien rangé et sûr » : bon type, bon patient, confiance haute. « Pas sûr » : un humain choisit (ce n'est pas une faute).
  « Mal rangé et dit sûr » : le cas grave — il doit rester à zéro.
- Les chiffres sont calculés depuis les réponses, jamais tapés. Rien ne sort de l'ordinateur.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .papiers import TYPES, proposer, proposer_avec_cerveau

RACINE = Path(__file__).resolve().parents[2]
FICHIER = RACINE / "docs/projet/MESURE_PAPIERS_APERTUS.md"
URL = "http://127.0.0.1:8089"
LIMITE_LENTE_MS = 5000
CONSIGNE = ("Tu ranges un papier apporté à l'accueil d'une clinique. Lis le texte du papier. Réponds avec : son type "
            "(choisi dans la liste, ou null si aucun ne va), sa date (recopiée telle quelle du papier, ou null), son auteur "
            "(le cabinet ou l'organisme, recopié tel quel du papier, ou null), le patient (choisi dans la liste, seulement si "
            "son nom est écrit sur le papier, sinon null), et ta confiance : haute, moyenne ou basse. N'invente rien.")


class ApertusDesPapiers:
    """Le vrai Apertus, par le serveur llama.cpp de l'ossature, sur cet ordinateur. Même porte que le cerveau de test."""

    nom = "Apertus 8B"

    def __init__(self, url: str = URL, delai_s: float = 20.0) -> None:
        self.url, self.delai_s = url.rstrip("/"), delai_s

    def lire(self, texte: str, types: list[str], patients: list[str]) -> Any:
        import httpx

        ou_rien = lambda schema: {"anyOf": [schema, {"type": "null"}]}  # noqa: E731
        schema = {"type": "object", "required": ["type", "date", "auteur", "patient", "confiance"], "additionalProperties": False,
                  "properties": {"type": ou_rien({"enum": list(types)}), "date": ou_rien({"type": "string", "maxLength": 40}),
                                 "auteur": ou_rien({"type": "string", "maxLength": 80}),
                                 "patient": ou_rien({"enum": list(patients)}) if patients else {"type": "null"},
                                 "confiance": {"enum": ["haute", "moyenne", "basse"]}}}
        corps = {"messages": [{"role": "system", "content": CONSIGNE},
                              {"role": "user", "content": f"Types possibles : {', '.join(types)}.\nPatients attendus : "
                                                          f"{', '.join(patients) or 'aucun'}.\n\nLe papier :\n{texte[:2000]}"}],
                 "temperature": 0, "max_tokens": 160, "stream": False, "response_format": {"type": "json_object", "schema": schema}}
        r = httpx.post(f"{self.url}/v1/chat/completions", json=corps, timeout=self.delai_s)
        r.raise_for_status()
        reponse = json.loads(r.json()["choices"][0]["message"]["content"])
        # Vu le 12.11 : le modèle écrit parfois le mot « null » entre guillemets au lieu de « rien ». C'est « rien ».
        return {cle: (None if isinstance(v, str) and v.strip().lower() in ("null", "") else v) for cle, v in reponse.items()}


def papiers_du_faux_dossier(journal=None) -> list[dict[str, Any]]:
    """Tous les papiers, lus par la porte avec le badge « assistant » (H09 : ces textes vont à un cerveau) : au service du
    médecin d'exemple pour les documents des patients, au service de l'accueil pour les feuilles sans nom.
    Le vrai type et le vrai patient viennent du faux dossier : ils servent à juger, jamais à ranger."""
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges

    horloge = HorlogeDeDemonstration()
    porte, badges = PorteDeLecture(journal=journal or JournalDesAcces(), jour=horloge.jour), charger_badges()
    pour_le_medecin = badges["assistant"].travaille_pour(badges["medecin-exemple"])
    pour_l_accueil = badges["assistant"].travaille_pour(badges["accueil"])
    patients = porte.patients(pour_le_medecin)
    attendus = [{"id": p["id"], "nom": p["nom"]} for p in patients]
    papiers = [{"id": d["id"], "texte": d["texte"], "ecriture": d.get("ecriture", "tapée"), "langue": d.get("langue"),
                "vrai_type": d["genre"], "vrai_patient": p["id"], "vrai_nom": p["nom"], "attendus": attendus}
               for p in patients for d in p.get("documents") or ()]
    sans_nom = {f["id"] for f in porte.feuilles_sans_patient(pour_l_accueil)}  # lesquelles sont sans nom (sans leur texte)
    papiers += [{"id": f["id"], "texte": f["texte"], "ecriture": f.get("ecriture", "tapée"), "langue": f.get("langue"),
                 "vrai_type": None, "vrai_patient": None, "vrai_nom": None, "attendus": attendus}
                for f in porte.papiers_a_ranger(pour_l_accueil) if f["id"] in sans_nom]
    return papiers


class _Espion:
    """Garde la réponse brute du cerveau et son temps, sans rien changer à ce qui passe."""

    def __init__(self, cerveau, montre: Callable[[], float]) -> None:
        self.cerveau, self.nom, self.montre = cerveau, getattr(cerveau, "nom", "cerveau"), montre
        self.brute: Any = None
        self.ms: int | None = None
        self.erreur: str | None = None

    def lire(self, texte: str, types: list[str], patients: list[str]) -> Any:
        self.brute, self.erreur, t0 = None, None, self.montre()
        try:
            self.brute = self.cerveau.lire(texte, types, patients)
            return self.brute
        except Exception as erreur:
            self.erreur = type(erreur).__name__
            raise
        finally:
            self.ms = round((self.montre() - t0) * 1000)


def mesurer(cerveau, montre: Callable[[], float] = time.perf_counter) -> dict[str, Any]:
    espion, detail = _Espion(cerveau, montre), []
    for papier in papiers_du_faux_dossier():
        regles = proposer(papier["texte"], papier["ecriture"], papier["attendus"])
        p = proposer_avec_cerveau(papier["texte"], papier["ecriture"], papier["attendus"], espion)
        brute = espion.brute if isinstance(espion.brute, dict) else {}
        juste = p["type"] == papier["vrai_type"] and p["patient"] == papier["vrai_patient"]
        sur = p["confiance"] == "haute"
        detail.append({"id": papier["id"], "ecriture": papier["ecriture"], "langue": papier["langue"],
                       "vrai_type": papier["vrai_type"], "vrai_patient": papier["vrai_patient"],
                       "modele_type": brute.get("type"), "modele_patient": brute.get("patient"), "modele_confiance": brute.get("confiance"),
                       "modele_date": brute.get("date"), "modele_auteur": brute.get("auteur"),
                       "regles_type": regles["type"], "regles_sur": regles["confiance"] == "haute",
                       "type": p["type"], "patient": p["patient"], "date": p["date"], "auteur": p["auteur"], "raisons": p["raisons"],
                       "sans_reponse": espion.erreur or ("hors formulaire" if "n'a pas répondu" in p["version"] else None),
                       "issue": "bien rangé" if juste and sur else ("MAL RANGÉ, DIT SÛR" if sur else "pas sûr"),
                       "ms": espion.ms})
    temps = [l["ms"] for l in detail if l["ms"] is not None]
    avec_type = [l for l in detail if l["vrai_type"]]
    return {"possible": True, "quand": datetime.now().astimezone().isoformat(timespec="seconds"), "cerveau": espion.nom,
            "papiers": len(detail), "papiers_avec_un_type": len(avec_type),
            "bien_ranges_surs": sum(1 for l in detail if l["issue"] == "bien rangé"),
            "pas_surs": sum(1 for l in detail if l["issue"] == "pas sûr"),
            "mal_ranges_dits_surs": sum(1 for l in detail if l["issue"] == "MAL RANGÉ, DIT SÛR"),
            "sans_reponse": sum(1 for l in detail if l["sans_reponse"]),
            "modele_seul_type_juste": sum(1 for l in avec_type if l["modele_type"] == l["vrai_type"]),
            "modele_seul_patient_juste": sum(1 for l in detail if (l["modele_patient"] or None) == (
                next((a["nom"] for a in papiers_du_faux_dossier()[0]["attendus"] if a["id"] == l["vrai_patient"]), None))),
            "regles_seules_bien_ranges_surs": sum(1 for l in detail if l["regles_sur"] and l["regles_type"] == l["vrai_type"]),
            "temps_median_ms": round(statistics.median(temps)) if temps else None, "temps_max_ms": max(temps, default=None),
            "plus_de_5_s": [l for l in detail if (l["ms"] or 0) > LIMITE_LENTE_MS], "detail": detail}


def rapport(r: dict[str, Any]) -> list[str]:
    jour = datetime.fromisoformat(r["quand"]).strftime("%d.%m.%Y, %H h %M")
    if not r["possible"]:
        return [f"RANGEMENT PAR APERTUS : PAS POSSIBLE — {jour}", f"Raison : {r['raison']}.", "Aucun chiffre : rien n'a été mesuré."]
    vrai = "RÉEL (vrai modèle, " + r["cerveau"] + ")" if "Apertus" in r["cerveau"] else r["cerveau"]
    n = r["papiers"]
    L = [f"RANGEMENT DES PAPIERS — cerveau : {vrai} ; DONNÉES INVENTÉES ; aucun robot — {jour}",
         f"{n} papiers du faux dossier (textes de référence, pas des images), lus par la porte. Sur cet ordinateur, Internet inutile.",
         f"RÉSULTAT, après vérification contre le papier : {r['bien_ranges_surs']} bien rangés et sûrs sur {n} ; {r['pas_surs']} « je ne suis "
         f"pas sûr » (un humain choisit) ; {r['mal_ranges_dits_surs']} mal rangés et dits sûrs.",
         f"Le modèle seul, avant vérification : le bon type pour {r['modele_seul_type_juste']} papiers sur {r['papiers_avec_un_type']} ; "
         f"le bon patient (ou « aucun » pour une feuille sans nom) pour {r['modele_seul_patient_juste']} sur {n}.",
         f"Pour comparer, les règles simples seules : {r['regles_seules_bien_ranges_surs']} bien rangés et sûrs sur {n}."]
    if r["sans_reponse"]:
        L.append(f"{r['sans_reponse']} fois, le cerveau n'a pas répondu (panne, délai ou hors formulaire) : les règles simples ont rangé.")
    if r["temps_median_ms"] is not None:
        L.append(f"Temps de réponse par papier : médian {r['temps_median_ms']} ms ; le plus long {r['temps_max_ms']} ms.")
    lentes = r["plus_de_5_s"]
    if lentes:
        L.append(f"{len(lentes)} réponse{'s' if len(lentes) > 1 else ''} de plus de 5 secondes : "
                 + ", ".join(f"{l['id']} ({l['ms']} ms)" for l in lentes) + ".")
    else:
        L.append("Aucune réponse de plus de 5 secondes.")
    L.append("Papier par papier, tel quel :")
    for l in r["detail"]:
        L.append(f"- {l['id']} ({l['ecriture']}, {l['langue'] or '?'}) — vrai type : {l['vrai_type'] or 'aucun (feuille sans nom)'} — "
                 f"modèle : {l['modele_type'] or 'rien'}, patient {l['modele_patient'] or 'aucun'}, confiance {l['modele_confiance'] or '?'}, "
                 f"date {l['modele_date'] or 'rien'}, auteur {l['modele_auteur'] or 'rien'} — après vérification : {l['issue']}"
                 + (f" ({' ; '.join(l['raisons'])})" if l["raisons"] else "") + f" — {l['ms']} ms")
    L.append("Limites : textes tapés du faux dossier, pas des images ; écrits par un agent ; un seul passage.")
    return L


def main(argv: list[str] | None = None) -> int:
    from commun.systeme import charger_reglages, creer_serveurs

    argparse.ArgumentParser(prog="lancer.py papiers-apertus").parse_args(argv)
    serveur = creer_serveurs(charger_reglages()).get("apertus_8b")
    quand = datetime.now().astimezone().isoformat(timespec="seconds")
    if serveur is None or not Path(serveur.modele).exists():
        r = {"possible": False, "raison": "le modèle Apertus 8B n'est pas sur cet ordinateur", "quand": quand}
    else:
        deja = serveur.en_marche()
        if not deja:
            serveur.lancer()
        try:
            if deja or serveur.attendre(180):
                cerveau = ApertusDesPapiers(serveur.url)
                try:  # une première demande met le modèle en route : elle n'est pas comptée
                    cerveau.lire("INVENTÉ — essai de mise en route.", list(TYPES), [])
                except Exception:
                    pass
                r = mesurer(cerveau)
            else:
                r = {"possible": False, "raison": "le serveur du modèle n'a pas démarré", "quand": quand}
        finally:
            if not deja:
                serveur.eteindre()
    lignes = rapport(r)
    for ligne in lignes:
        print(ligne)
    from . import mesures_cerveau  # T21 : gardé pour la fiche de vérité

    mesures_cerveau.noter("papiers", r)
    FICHIER.write_text("# Le rangement des papiers par Apertus (dernière mesure)\n\n" + "\n\n".join(lignes) + "\n", encoding="utf-8")
    print(f"Écrit dans {FICHIER.name}")
    return 0 if r["possible"] else 2
