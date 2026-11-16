"""T13 — Le résumé du médecin, écrit par un cerveau (Apertus), puis VÉRIFIÉ ligne par ligne (cahier 5.7).

    resume.cerveau = ApertusDuResume()              # le vrai Apertus, par le serveur de l'ossature (port des réglages)
    resume.cerveau = CerveauDeTest(lambda titre, sources: {...})   # pour les vérifications : réponses fixes
    python3 lancer.py resume-apertus                # mesure avec le vrai Apertus, sur le faux dossier

Un cerveau peut inventer. Donc :
- il ne reçoit, pour une ligne, que les sources que les règles simples ont choisies pour cette ligne ;
- SOURCES OBLIGATOIRES : chaque phrase cite ses sources, prises dans cette liste. Sinon elle est retirée ;
- VERROU DES CHIFFRES : chaque suite de chiffres d'une phrase doit se trouver dans une source citée (le contrôle de la
  version simple, `garder_les_phrases_sures`) ;
- LES MOTS : une phrase dont trop de mots ne viennent pas de ses sources est retirée (le résumé recopie, il ne conclut pas) ;
- RIEN DE PERDU, RIEN D'AJOUTÉ : la ligne ne doit pas répéter son titre ; elle doit avoir tous les chiffres de la version
  simple, et aucun autre (ce sont les règles qui choisissent les faits, le cerveau ne fait que les écrire) ;
- « JE NE SUIS PAS SÛR » : si le cerveau le dit, ou si une de ses phrases est retirée, la ligne revient à la version
  simple, et l'écran le dit ;
- les questions de la patiente (ses mots à elle) et un désaccord entre deux sources ne passent jamais par le cerveau ;
- cerveau en panne, hors formulaire, ou trop lent : TOUT le résumé revient à la version simple, et la version le dit.
Limites du contrôle : il ne comprend pas le sens. Depuis la relecture de la tranche 2, la ligne du cerveau doit avoir les
mêmes chiffres dans le même ordre, tous les mots longs de la version simple, et aucun mot venu d'ailleurs : il ne lui
reste qu'à redire la version simple. Deux mots de la source échangés entre eux (« arrivée » et « sortie », quand les
deux sont dans la version simple) passeraient encore.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .resume import RIEN, VERSION, _meme_mot, _mots, _nombres, garder_les_phrases_sures

RACINE = Path(__file__).resolve().parents[2]
FICHIER = RACINE / "docs/projet/MESURE_RESUME_APERTUS.md"
URL = "http://127.0.0.1:8089"
JAMAIS_PAR_LE_CERVEAU = ("questions",)  # les mots de la patiente restent ses mots
BUDGET_S = 30.0  # pour un patient : au-delà, on retombe sur la version simple (« trop long »)
PART_DES_MOTS = 0.7  # part des mots de cinq lettres et plus qui doivent venir des sources citées
MOTS_LIBRES = {"patient", "patiente", "madame", "monsieur", "prevu", "prevue", "prevus", "prevues", "aujourd", "depuis",
               "apres", "avant", "pendant", "sejour", "arrivee", "sortie", "raison", "chambre", "jours", "heure", "heures"}
LIMITE_LENTE_MS = 5000
LIENS = {"le", "la", "les", "l", "de", "du", "des", "d", "a", "au", "aux", "et", "en", "un", "une", "pour", "sur", "dans", "par"}
NEGATIONS = {"pas", "ne", "n", "ni", "non", "sans", "aucun", "aucune", "jamais", "plus", "annule", "annulee"}


class TropLong(Exception):
    pass


class CerveauDeTest:
    """Un cerveau de test : des réponses fixes (cahier 2.8). `repondre(titre, sources)` rend la réponse."""

    nom = "cerveau de test (réponses fixes)"

    def __init__(self, repondre: Callable[[str, dict[str, str]], Any]) -> None:
        self._repondre = repondre

    def ecrire(self, titre: str, sources: dict[str, str]) -> Any:
        return self._repondre(titre, sources)


CONSIGNE = ("Tu écris une ligne d'un résumé pour un médecin, en français. Utilise SEULEMENT les textes donnés. "
            "Recopie les chiffres, les heures et les dates tels quels. N'ajoute rien. Ne conclus rien. Ne donne aucun avis "
            "médical. Une ou deux phrases courtes. Pour chaque phrase, donne les références des textes utilisés. "
            "Écris d'abord les phrases. Ensuite \"sur\": true si chaque phrase vient des textes ; "
            "\"sur\": false seulement si les textes ne permettent pas d'écrire cette ligne.")


class ApertusDuResume:
    """Le vrai Apertus, par le serveur llama.cpp lancé par l'ossature (`python3 lancer.py cerveau`). Sur cet ordinateur :
    rien ne sort. La réponse est forcée à suivre un formulaire (les références possibles sont dans le formulaire)."""

    nom = "Apertus 8B"

    def __init__(self, url: str = URL, delai_s: float = 12.0) -> None:
        self.url, self.delai_s = url.rstrip("/"), delai_s

    def ecrire(self, titre: str, sources: dict[str, str]) -> Any:
        import httpx

        # l'ordre compte : le modèle écrit d'abord ses phrases, puis dit s'il est sûr (première mesure, 12.11 : avec
        # « sur » en premier, il répondait « pas sûr » à toutes les lignes, 0 sur 13)
        schema = {"type": "object", "required": ["phrases", "sur"], "additionalProperties": False, "properties": {
            "phrases": {"type": "array", "maxItems": 2, "items": {
                "type": "object", "required": ["texte", "sources"], "additionalProperties": False, "properties": {
                    "texte": {"type": "string", "maxLength": 200},
                    "sources": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"enum": list(sources)}}}}},
            "sur": {"type": "boolean"}}}
        textes = "\n\n".join(f"[{ref}]\n{texte[:1500]}" for ref, texte in sources.items())
        corps = {"messages": [{"role": "system", "content": CONSIGNE},
                              {"role": "user", "content": f"Textes :\n\n{textes}\n\nÀ partir de ces textes, écris ce qu'il faut savoir "
                                                          f"sur le point « {titre} ». Ne répète pas ce titre : donne les faits, "
                                                          f"avec tous les chiffres et toutes les heures utiles."}],
                 "temperature": 0, "max_tokens": 220, "stream": False,
                 "response_format": {"type": "json_object", "schema": schema}}
        r = httpx.post(f"{self.url}/v1/chat/completions", json=corps, timeout=self.delai_s)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


# ---------------------------------------------------------------------- le contrôle
def _lisible(reponse: Any) -> bool:
    if not isinstance(reponse, dict) or not isinstance(reponse.get("sur"), bool) or not isinstance(reponse.get("phrases"), list):
        return False
    return all(isinstance(p, dict) and isinstance(p.get("texte"), str) and isinstance(p.get("sources"), list)
               and all(isinstance(s, str) for s in p["sources"]) for p in reponse["phrases"])


def _mots_des_sources(phrase: dict[str, Any], textes: dict[str, str]) -> bool:
    """Assez de mots de la phrase (cinq lettres et plus) viennent-ils de ses sources ?"""
    longs = [m for m in _mots(phrase["texte"]) if len(m) >= 5 and m not in MOTS_LIBRES]
    if not longs:
        return True
    connus = {m for ref in phrase["sources"] for m in _mots(textes[ref])}
    trouves = sum(1 for m in longs if any(_meme_mot(m, autre) for autre in connus))
    return trouves / len(longs) >= PART_DES_MOTS


def controler(reponse: dict[str, Any], textes: dict[str, str], titre: str = "", simple: str = "") -> tuple[list[dict[str, Any]], str]:
    """Les phrases gardées, et la raison si la ligne n'est pas sûre (« » si tout va bien).
    `textes` : les seules sources données au cerveau pour cette ligne. `titre`, `simple` : le titre de la ligne et sa
    version simple — la ligne du cerveau ne doit ni répéter le titre, ni perdre un chiffre de la version simple
    (mesure du 12.11 : Apertus écrivait « Prévu aujourd'hui » à la place du programme, et la ligne passait)."""
    if not reponse["sur"]:
        return [], "le cerveau dit qu'il n'est pas sûr"
    phrases = [{"texte": " ".join(p["texte"].split())[:300], "sources": list(dict.fromkeys(p["sources"]))} for p in reponse["phrases"]]
    phrases = [p for p in phrases if p["texte"]]
    if not phrases:
        return [], "le cerveau n'a rien écrit"
    for p in phrases:
        if not p["sources"] or any(ref not in textes for ref in p["sources"]):
            return [], "une phrase sans source, ou avec une source qui n'est pas celle de cette ligne"
        if not garder_les_phrases_sures([p], textes):
            return [], "un chiffre de la phrase n'est pas dans sa source"
        if not _mots_des_sources(p, textes):
            return [], "trop de mots de la phrase ne viennent pas de ses sources"
    ecrit = " ".join(p["texte"] for p in phrases)
    du_titre, des_sources = set(_mots(titre)), {m for texte in textes.values() for m in _mots(texte)}
    if not [m for m in _mots(ecrit) if len(m) >= 4 and m not in du_titre and m in des_sources]:
        return [], "la ligne ne dit rien : elle répète le titre"
    manquants = [n for n in dict.fromkeys(_nombres(simple)) if n not in _nombres(ecrit)]
    if manquants:
        return [], f"il manque un chiffre de la version simple ({', '.join(manquants[:4])})"
    # mesure du 12.11 : Apertus mettait dans « Prévu aujourd'hui » des rendez-vous de demain, pris dans la même source.
    # Ce sont les règles qui choisissent les faits : le cerveau ne peut pas en ajouter.
    en_trop = [n for n in dict.fromkeys(_nombres(ecrit)) if simple and n not in _nombres(simple)]
    if en_trop:
        return [], f"un chiffre de la ligne n'est pas dans la version simple ({', '.join(en_trop[:4])})"
    # Relecture de la tranche 2 (12.11) : un relecteur neuf a fait passer « Pas de réadaptation… », des heures échangées,
    # « Sortie le jour 1 » à la place de « Arrivée le jour 1 », et « Elle va mal ». Quatre contrôles de plus :
    if simple and _nombres(ecrit) != _nombres(simple):
        return [], "les chiffres ne sont pas ceux de la version simple, dans le même ordre"
    connus = des_sources | set(_mots(simple)) | LIENS
    inconnus = [m for m in dict.fromkeys(_mots(ecrit)) if m not in connus]
    if inconnus:  # tous les mots, même courts : « pas », « mal », « va »
        return [], f"un mot de la ligne ne vient ni des sources ni de la version simple ({', '.join(inconnus[:4])})"
    nies = [m for m in dict.fromkeys(_mots(ecrit)) if m in NEGATIONS and m not in _mots(simple)]
    if nies:
        return [], f"la ligne dit « {nies[0]} », que la version simple ne dit pas"
    perdus = [m for m in dict.fromkeys(_mots(simple)) if len(m) >= 5 and m not in _mots(ecrit)]
    if perdus:
        return [], f"il manque un mot de la version simple ({', '.join(perdus[:4])})"
    return phrases, ""


def reecrire(resume: dict[str, Any], sources: dict[str, dict[str, Any]], cerveau, montre: Callable[[], float] = time.perf_counter,
             budget_s: float = BUDGET_S, noter: Callable[[str, list[str]], None] | None = None) -> dict[str, Any]:
    """Le résumé simple, dont chaque ligne permise est réécrite par le cerveau, puis contrôlée.
    Rend toujours un résumé : au pire, le résumé simple, avec la raison dans « version »."""
    nom = getattr(cerveau, "nom", "cerveau")
    depart = montre()
    lignes, ecartees, ecrites, temps = [], [], 0, []  # écartées : pas « retirées faute de source » (cahier 5.11), comptées à part
    try:
        for ligne in resume["lignes"]:
            if ligne["texte"] == RIEN or ligne["desaccord"] or ligne["point"] in JAMAIS_PAR_LE_CERVEAU or not ligne["sources"]:
                lignes.append(ligne)
                continue
            textes = {s["ref"]: sources[s["ref"]]["texte"] for s in ligne["sources"]}
            if noter is not None:  # H09 : le journal des accès dit ce que le cerveau reçoit, avant qu'il le reçoive
                noter(ligne["titre"], list(textes))
            t0 = montre()
            reponse = cerveau.ecrire(ligne["titre"], textes)
            temps.append(round((montre() - t0) * 1000))
            if montre() - depart > budget_s:
                raise TropLong(f"plus de {budget_s:.0f} secondes pour ce résumé")
            if not _lisible(reponse):
                raise ValueError("réponse hors formulaire")
            phrases, raison = controler(reponse, textes, ligne["titre"], ligne["texte"])
            if raison:  # la ligne revient à la version simple, et on le dit
                for p in reponse["phrases"]:
                    ecartees.append({"point": ligne["point"], "texte": str(p.get("texte", ""))[:200], "raison": raison})
                lignes.append({**ligne, "ecrit_par": "règles simples",
                               "pas_sur": f"je ne suis pas sûr ({raison}) : version simple pour cette ligne"})
                continue
            refs = list(dict.fromkeys(ref for p in phrases for ref in p["sources"]))
            ecrites += 1
            lignes.append({**ligne, "texte": " ".join(p["texte"] for p in phrases), "phrases": phrases, "ecrit_par": "cerveau",
                           "sources": [s for s in ligne["sources"] if s["ref"] in refs]})
    except TropLong as erreur:
        return {**resume, "version": f"règles simples (le cerveau n'a pas fini à temps : trop long, {erreur})"}
    except Exception as erreur:  # éteint, cassé, hors formulaire : on ne bloque jamais la visite
        raison = str(erreur) if isinstance(erreur, ValueError) else type(erreur).__name__
        return {**resume, "version": f"règles simples (le cerveau n'a pas répondu : {raison[:80]})"}
    return {**resume, "lignes": lignes, "ecartees_du_cerveau": ecartees, "temps_cerveau_ms": sum(temps), "temps_par_ligne_ms": temps,
            "version": (f"écrit par {nom} pour {ecrites} ligne{'s' if ecrites > 1 else ''} sur {len(lignes)}, vérifié ligne "
                        f"par ligne ; le reste : {VERSION}")}


def brancher_si_demande(resume) -> bool:
    """Dans la séance : Apertus n'écrit le résumé que si l'équipe le demande (variable CLINIQUE_APERTUS=1 au lancement).
    Par défaut : la version simple, comme avant."""
    if os.environ.get("CLINIQUE_APERTUS") == "1":
        resume.cerveau = ApertusDuResume()
        return True
    return False


# ---------------------------------------------------------------------- la mesure avec le vrai Apertus
def mesurer(cerveau=None) -> dict[str, Any]:
    """Tous les patients du médecin d'exemple, jour 1, sur le faux dossier. Chaque chiffre vient des résumés produits."""
    from .carnet import Carnet
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges
    from .resume import ResumeDuMedecin

    horloge = HorlogeDeDemonstration()
    porte = PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour)
    badge = charger_badges()["medecin-exemple"]
    simple = ResumeDuMedecin(porte, Carnet(horloge=horloge), horloge)
    avec = ResumeDuMedecin(porte, Carnet(horloge=horloge), horloge)
    avec.cerveau = cerveau or ApertusDuResume()
    patients = []
    for s in simple.tous(badge):
        t0 = time.perf_counter()
        a = avec.resume(badge, s["patient"])
        patients.append({"patient": s["patient"], "nom": s["nom"], "version": a["version"], "ms": round((time.perf_counter() - t0) * 1000),
                         "par_ligne_ms": a.get("temps_par_ligne_ms") or [],
                         "retirees": list(a.get("ecartees_du_cerveau") or []),
                         "lignes": [{"titre": l["titre"], "simple": ls["texte"], "obtenu": l["texte"], "ecrit_par": l.get("ecrit_par"),
                                     "pas_sur": l.get("pas_sur")} for l, ls in zip(a["lignes"], s["lignes"])]})
    lignes = [l for p in patients for l in p["lignes"]]
    par_ligne = [ms for p in patients for ms in p["par_ligne_ms"]]
    return {"possible": True, "quand": datetime.now().astimezone().isoformat(timespec="seconds"), "cerveau": getattr(avec.cerveau, "nom", "?"),
            "patients": patients, "lignes": len(lignes), "demandees": sum(1 for l in lignes if l["ecrit_par"]),
            "ecrites": sum(1 for l in lignes if l["ecrit_par"] == "cerveau"), "pas_sures": sum(1 for l in lignes if l["pas_sur"]),
            "retombes": sum(1 for p in patients if p["version"].startswith("règles simples")),
            "phrases_retirees": sum(len(p["retirees"]) for p in patients),
            "ligne_mediane_ms": round(statistics.median(par_ligne)) if par_ligne else None, "ligne_max_ms": max(par_ligne, default=None),
            "patient_median_ms": round(statistics.median(p["ms"] for p in patients)), "patient_max_ms": max(p["ms"] for p in patients),
            "lignes_lentes": sum(1 for ms in par_ligne if ms > LIMITE_LENTE_MS)}


def rapport(r: dict[str, Any]) -> list[str]:
    jour = datetime.fromisoformat(r["quand"]).strftime("%d.%m.%Y, %H h %M")
    if not r["possible"]:
        return [f"RÉSUMÉ PAR APERTUS : PAS POSSIBLE — {jour}", f"Raison : {r['raison']}.", "Aucun chiffre : rien n'a été mesuré."]
    L = [f"RÉSUMÉ PAR APERTUS — cerveau : RÉEL (vrai modèle, {r['cerveau']}) ; DONNÉES INVENTÉES ; aucun robot — {jour}",
         f"{len(r['patients'])} patients du faux dossier, jour 1, {r['lignes']} lignes de résumé. Sur cet ordinateur, Internet inutile.",
         f"Lignes confiées au cerveau : {r['demandees']} (les autres : « rien de nouveau », un désaccord, ou les questions de la patiente).",
         f"RÉSULTAT : {r['ecrites']} lignes écrites par le cerveau et gardées après contrôle, sur {r['demandees']} ; "
         f"{r['pas_sures']} revenues à la version simple (« je ne suis pas sûr ») ; {r['phrases_retirees']} phrases du cerveau écartées.",
         f"Résumés entièrement revenus à la version simple (panne, hors formulaire, trop long) : {r['retombes']} sur {len(r['patients'])}."]
    if r["ligne_mediane_ms"] is not None:
        L.append(f"Temps par ligne : médian {r['ligne_mediane_ms']} ms ; le plus long {r['ligne_max_ms']} ms. "
                 f"Temps par patient : médian {r['patient_median_ms']} ms ; le plus long {r['patient_max_ms']} ms.")
        L.append(f"{r['lignes_lentes']} ligne(s) de plus de 5 secondes." if r["lignes_lentes"] else "Aucune ligne de plus de 5 secondes.")
    L.append("Le contrôle regarde les sources, les chiffres et les mots. Il ne comprend pas le sens : chaque ligne ci-dessous "
             "est à relire par un humain. Les deux versions, telles quelles :")
    for p in r["patients"]:
        L.append(f"## {p['nom']} — {p['ms']} ms — {p['version']}")
        for l in p["lignes"]:
            if l["ecrit_par"] == "cerveau":
                L.append(f"- {l['titre']} — simple : « {l['simple']} » — cerveau : « {l['obtenu']} »")
            elif l["pas_sur"]:
                L.append(f"- {l['titre']} — {l['pas_sur']} : « {l['obtenu']} »")
        for d in p["retirees"]:
            L.append(f"- phrase du cerveau écartée (raison donnée pour toute la ligne : {d['raison']}) : « {d['texte']} »")
    return L


def main(argv: list[str] | None = None) -> int:
    from commun.systeme import charger_reglages, creer_serveurs

    argparse.ArgumentParser(prog="lancer.py resume-apertus").parse_args(argv)
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
                r = mesurer(ApertusDuResume(serveur.url))
            else:
                r = {"possible": False, "raison": "le serveur du modèle n'a pas démarré", "quand": quand}
        finally:
            if not deja:
                serveur.eteindre()
    lignes = rapport(r)
    for ligne in lignes:
        print(ligne)
    from . import mesures_cerveau  # T21 : gardé pour la fiche de vérité

    mesures_cerveau.noter("resume", r)
    FICHIER.write_text("# Le résumé écrit par Apertus (dernière mesure)\n\n" + "\n\n".join(lignes) + "\n", encoding="utf-8")
    print(f"Écrit dans {FICHIER.name}")
    return 0 if r["possible"] else 2
