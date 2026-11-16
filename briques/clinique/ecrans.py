"""Les écrans de la clinique (cahier 5.4) : patient, soignant, médecin, accueil, plus le thérapeute et le journal.

    from briques.clinique.ecrans import brancher_ecrans
    brancher_ecrans(app, porte=porte, horloge=horloge)     # ajoute les pages à l'écran de l'ossature (brique 13)

- GET /clinique                     la page d'entrée : la liste des écrans
- GET /clinique/{écran}             un écran ; « ?badge=… » choisit le badge, « ?langue=… » la langue
- GET /clinique/{écran}/contenu     le milieu de l'écran seulement (la page le redemande toutes les deux secondes)
- GET /clinique/journal             le journal des accès : qui a lu quoi, quand
- GET /api/clinique/ecran/{écran}   la même chose en données (pour les essais et le motion design)
- GET /api/clinique/horloge, /api/clinique/badges, /api/clinique/journal

Règles :
- Les écrans lisent TOUT par la porte de lecture, jamais dans les fichiers. Un essai le vérifie.
- Sur chaque écran : le bandeau « DONNÉES INVENTÉES — DÉMONSTRATION », l'heure de l'horloge, le badge, les étiquettes.
- Version simple (tâche T05) : les écrans montrent ce que la porte donne. Rien ne s'écrit encore (pas de coche, pas
  de bouton) : cela vient avec les tâches suivantes.
- Le badge n'est pas un contrôle d'identité (voir NON_TESTE.md). Aucune page ne vient d'Internet.
"""
from __future__ import annotations

import html
import json
import socket
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .carnet import Carnet
from .horloge import HorlogeDeDemonstration
from .listes import ListesDeSoin
from .porte import AccesRefuse, Badge, PorteDeLecture, charger_badges
from .taches import TableauDesTaches

BANDEAU = "DONNÉES INVENTÉES — DÉMONSTRATION"
ETIQUETTES = ("RÉEL", "FAUX ROBOT", "SIMULÉ", "JOUÉ")
RAFRAICHIR_MS = 2000  # le secours : la page redemande son contenu toutes les deux secondes
LIMITE_VIEUX_S = 10  # avenant 2, K03 : au-delà, la zone se grise et dit « information vieille de tant de secondes » (réglable)

# écran → (titre, rôle du badge qui l'ouvre, langues de l'écran)
ECRANS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "patient": ("Patient", "patient", ("fr", "de", "it", "en")),
    "soignant": ("Soignant", "soignant", ("fr", "de")),
    "medecin": ("Médecin", "médecin", ("fr", "de")),
    "accueil": ("Accueil", "accueil", ("fr",)),
    "therapeute": ("Thérapeute", "thérapeute", ("fr",)),
}

# Les mots des écrans. Allemand, italien, anglais : écrits par l'agent, pas relus par quelqu'un qui parle la langue.
TEXTES: dict[str, dict[str, str]] = {
    "fr": {"mon_programme": "Mon programme du jour", "mes_documents": "Mes documents", "chambre": "Chambre",
           "etage": "étage", "langue": "langue", "mes_patients": "Mes patients", "habitudes": "Habitudes",
           "programme": "Programme du jour", "listes": "Listes de soin prévues", "documents": "Documents",
           "raison": "Raison du séjour", "arrivees": "Arrivées du jour", "papiers": "Papiers apportés",
           "arrivee": "Arrivée", "rien": "Rien pour aujourd'hui.", "personne": "Personne pour l'instant.",
           "age": "ans", "aucun": "aucun"},
    "de": {"mon_programme": "Mein Programm heute", "mes_documents": "Meine Dokumente", "chambre": "Zimmer",
           "etage": "Stock", "langue": "Sprache", "mes_patients": "Meine Patienten", "habitudes": "Gewohnheiten",
           "programme": "Programm heute", "listes": "Geplante Pflegelisten", "documents": "Dokumente",
           "raison": "Grund des Aufenthalts", "arrivees": "Ankünfte heute", "papiers": "Mitgebrachte Papiere",
           "arrivee": "Ankunft", "rien": "Heute nichts.", "personne": "Im Moment niemand.", "age": "Jahre",
           "aucun": "keine"},
    "it": {"mon_programme": "Il mio programma di oggi", "mes_documents": "I miei documenti", "chambre": "Camera",
           "etage": "piano", "langue": "lingua", "rien": "Niente per oggi.", "aucun": "nessuno"},
    "en": {"mon_programme": "My programme today", "mes_documents": "My documents", "chambre": "Room",
           "etage": "floor", "langue": "language", "rien": "Nothing for today.", "aucun": "none"},
}


@dataclass
class Clinique:
    """Ce que les écrans partagent : la porte, l'horloge, les badges, le carnet, les listes de soin."""
    porte: PorteDeLecture
    horloge: HorlogeDeDemonstration
    badges: dict[str, Badge]
    carnet: Carnet
    listes: ListesDeSoin
    taches: TableauDesTaches
    coursier: Any = None  # le coursier, si un robot est branché (sinon les tâches « pour un robot » attendent)
    resume: Any = None  # le résumé du médecin (resume.py)
    papiers: Any = None  # les papiers à ranger (papiers.py)
    accueil: Any = None  # l'accueil du hall (accueil.py), si un badge de robot existe
    soir: Any = None  # les questions du soir et la dictée, version simple (soir.py)
    flotte: Any = None  # les quatre robots, la panne et la reprise, version simple (flotte.py)
    essais_reels: Any = None  # le compteur d'essais réels, pour l'équipe (essais_reels.py)
    etageres: Any = None  # l'épreuve des étagères, dix minutes, pour l'équipe (etageres.py)
    faux_logiciel: Any = None  # le faux logiciel administratif, SIMULÉ, à part (lien_logiciel.py, avenant 4)
    lecteur_admin: Any = None  # une fonction qui rend le traducteur des messages (traducteur.py, avenant 4, L03)
    pre_admissions: Any = None  # une fonction qui rend les pré-admissions (pre_admission.py, avenant 4, L04)
    pauses_des_soignants: Any = None  # les pauses mises par les soignants (pauses.py, avenant jury, J05)
    messages_du_faux_logiciel: Any = None  # ce qu'il a écrit pendant cette séance (des numéros, pas de nom)
    pannes: Any = None  # les pannes provoquées (pannes.py)
    tableau_de_flotte: Any = None  # le tableau de flotte (tableau_flotte.py, T25)
    avis: Any = None  # les avis des personnes (avis.py, K06)
    invite: Any = None  # l'écran « Invité » (invite.py, K07a)
    interprete: Any = None  # le mode interprète de la régie (interprete_ecran.py, H10b)
    moments: Any = None  # les séances de cet ordinateur, pour la page « Moments » (moments.py)


def _entendre(self, badge: Badge, patient: str, liste: str, phrase: str) -> dict[str, Any]:
    """Une phrase entendue sur la page d'une liste (T16, T17) : une réponse à une question du robot, une coche, ou une
    demande au robot. Micro en panne (J02) : la phrase arrive comme du bruit. Une demande au robot part ensuite, sous le gardien."""
    phrase, confiance = self.pannes.entendre(phrase) if self.pannes is not None else (phrase, 1.0)
    if (badge.id, patient) in self.taches._questions:  # le robot attend une réponse : la phrase est pour lui
        reponse = self.taches.entendre(badge, patient, phrase, confiance)
    else:
        reponse = self.listes.entendre(badge, patient, liste, phrase, confiance)
        if reponse["compris"] == "rien" and confiance >= 0.6:
            demande = self.taches.entendre(badge, patient, phrase, confiance)
            if demande["compris"] != "rien":
                reponse = demande
    tache = reponse.get("tache")
    if tache and tache.get("sorte") == "robot" and self.coursier is not None:
        self.coursier.lancer(tache["id"])  # la course part ; chaque geste passera par le gardien
    return reponse


Clinique.entendre = _entendre


def _e(texte: Any) -> str:
    return html.escape(str(texte), quote=True)


def _mots(langue: str) -> dict[str, str]:
    return {**TEXTES["fr"], **TEXTES.get(langue, {})}


# ---------------------------------------------------------------------- lire par la porte
def lire_ecran(clinique: Clinique, ecran: str, badge: Badge) -> dict[str, Any]:
    """Ce qu'un écran montre : uniquement ce que la porte donne à ce badge. Un refus est rendu, pas caché."""
    titre, role, _ = ECRANS[ecran]
    heure = clinique.horloge.etat()
    reponse: dict[str, Any] = {"marque": "données inventées", "bandeau": BANDEAU, "ecran": ecran, "horloge": heure,
                               "badge": {"id": badge.id, "role": badge.role, "libelle": badge.libelle},
                               "etiquettes": list(ETIQUETTES), "refuse": False}
    try:
        if badge.role != role:
            clinique.porte.refuser(badge, f"écran : {titre}", f"le badge « {badge.libelle} » n'ouvre pas l'écran « {titre} »")
        if ecran == "patient":
            patients = [clinique.porte.patient(badge, badge.patient or "")]
        else:
            patients = clinique.porte.patients(badge)
    except AccesRefuse as refus:
        return {**reponse, "refuse": True, "raison": str(refus)}
    donnees: dict[str, Any] = {"jour": heure["jour"], "patients": patients}
    prevues = sorted({identifiant for p in patients for identifiant in p.get("listes") or ()})
    if prevues:  # les titres des listes prévues, lus par la porte
        donnees["listes"] = {i: clinique.porte.liste_de_soin(badge, i)["titre"] for i in prevues}
    if ecran == "soignant":
        donnees["prise_de_poste"] = clinique.listes.prise_de_poste(badge)
        donnees["taches"] = clinique.taches.tableau(badge)
        donnees["robot_branche"] = clinique.coursier is not None
        if clinique.accueil is not None:  # ce que le robot du hall a transmis à cet étage
            donnees["messages_du_hall"] = clinique.accueil.messages_pour_l_etage(badge)
    if ecran == "patient" and clinique.soir is not None:  # le soir : la question pour le médecin, dans sa langue
        donnees["soir"] = clinique.soir.invitation(badge)
    if ecran in ("therapeute", "medecin") and clinique.soir is not None:  # la dictée du médecin ; pour lui : les questions du soir (H02)
        donnees["taches_pour_moi"] = clinique.soir.pour_moi(badge)
    if ecran == "accueil":  # H17 (Q24 : B) : ses trois points de la liste de sortie, et rien d'autre
        donnees["sorties_accueil"] = clinique.listes.sorties_pour_l_accueil(badge)
    if ecran == "accueil" and clinique.papiers is not None:  # les papiers du jour, avec leur proposition
        donnees["papiers"] = clinique.papiers.pile(badge)
    if ecran == "accueil" and clinique.lecteur_admin is not None:  # l'heure de la dernière nouvelle du logiciel administratif
        donnees["nouvelle_admin"] = clinique.lecteur_admin().derniere_nouvelle() or {}
    if ecran == "accueil" and clinique.accueil is not None:  # les fois où le robot du hall a appelé un humain
        donnees["appels_du_hall"] = clinique.accueil.appels(badge)
    if ecran == "medecin" and clinique.resume is not None:  # le résumé de chaque patient, avec ses sources
        donnees["resumes"] = {r["patient"]: r for r in clinique.resume.tous(badge)}
    return {**reponse, "donnees": donnees}


# ---------------------------------------------------------------------- dessiner
def _programme_du_jour(patient: dict[str, Any], jour: int, mots: dict[str, str]) -> str:
    lignes = [r for r in patient.get("programme") or [] if r.get("jour") == jour]
    if not lignes:
        return f"<p class='rien'>{_e(mots['rien'])}</p>"
    return "<ul>" + "".join(f"<li><b>{_e(r['heure'])}</b> {_e(r['quoi'])} — {_e(r['lieu'])}</li>" for r in lignes) + "</ul>"


def _liste(elements: list[Any], mots: dict[str, str]) -> str:
    if not elements:
        return f"<p class='rien'>{_e(mots['aucun'])}</p>"
    return "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in elements) + "</ul>"


def _titres(documents: list[dict[str, Any]]) -> list[str]:
    return [f"{d.get('genre', '')} : {d.get('titre', '')}" for d in documents or []]


def _carte(patient: dict[str, Any], ecran: str, jour: int, mots: dict[str, str], titres: dict[str, str] | None = None,
           badge: str = "") -> str:
    """Un patient, sur un écran. On ne dessine que les champs que la porte a donnés."""
    p, titres = patient, titres or {}
    morceaux = [f"<h3>{_e(p.get('nom', ''))}</h3>",
                f"<p class='ou'>{_e(mots['chambre'])} {_e(p.get('chambre', '?'))} · {_e(mots['etage'])} "
                f"{_e(p.get('etage', '?'))} · {_e(mots['langue'])} : {_e(p.get('langue', '?'))}</p>"]
    if ecran == "accueil":
        arrivee = p.get("arrivee") or {}
        morceaux += [f"<p>{_e(mots['arrivee'])} : {_e(arrivee.get('heure', '?'))}</p>",
                     f"<h4>{_e(mots['papiers'])}</h4>", _liste(_titres(p.get("documents")), mots)]
        from .lien_logiciel import lien_vers_la_fiche  # la fiche administrative, dans le faux logiciel (SIMULÉ, à part)
        morceaux.append(f"<p><a href=\"{_e(lien_vers_la_fiche(p['id']))}\">Fiche dans le faux logiciel administratif (SIMULÉ)</a></p>")
        return "<article>" + "".join(morceaux) + "</article>"
    if p.get("dossier_de_soins"):  # arrivée par message du logiciel administratif : rien de médical à montrer
        morceaux.append(f"<p class='ou'>dossier de soins : {_e(p['dossier_de_soins'])}</p>")
        return "<article>" + "".join(morceaux) + "</article>"
    if "raison" in p:
        morceaux.append(f"<p><b>{_e(mots['raison'])}</b> : {_e(p['raison'])} ({_e(p.get('age', '?'))} {_e(mots['age'])})</p>")
    if "habitudes" in p:
        morceaux += [f"<h4>{_e(mots['habitudes'])}</h4>", _liste(p["habitudes"], mots)]
    morceaux += [f"<h4>{_e(mots['programme'])}</h4>", _programme_du_jour(p, jour, mots)]
    if "listes" in p:
        if ecran == "soignant":  # le soignant ouvre la liste d'un doigt
            liens = "".join(f"<li><a class='bouton' href=\"/clinique/soignant/liste?badge={_e(badge)}&amp;patient={_e(p['id'])}"
                            f"&amp;liste={_e(i)}\">{_e(titres.get(i, i))}</a></li>" for i in p["listes"])
            morceaux += [f"<h4>{_e(mots['listes'])}</h4>", f"<ul class='liens'>{liens}</ul>" if liens else _liste([], mots)]
        else:
            morceaux += [f"<h4>{_e(mots['listes'])}</h4>", _liste([titres.get(i, i) for i in p["listes"]], mots)]
    if "documents" in p:
        morceaux += [f"<h4>{_e(mots['documents'])}</h4>", _liste(_titres(p["documents"]), mots)]
    return "<article>" + "".join(morceaux) + "</article>"


def _langue(ecran: str, vue: dict[str, Any], demandee: str | None) -> str:
    langues = ECRANS[ecran][2]
    if demandee in langues:
        return demandee
    if ecran == "patient" and not vue["refuse"]:  # l'écran du patient s'ouvre dans sa langue, si on l'a
        sienne = vue["donnees"]["patients"][0].get("langue")
        if sienne in langues:
            return sienne
    return "fr"


def dessiner_contenu(ecran: str, vue: dict[str, Any], demandee: str | None = None) -> str:
    """Le milieu de l'écran, en HTML, puis ses textes traduits (H03 : un seul fichier de phrases, traductions_ecrans.yaml)."""
    from . import traductions

    langue = demandee if vue["refuse"] else _langue(ecran, vue, demandee)
    return traductions.traduire(_dessiner_contenu(ecran, vue, demandee), langue, ecran)


def _dessiner_contenu(ecran: str, vue: dict[str, Any], demandee: str | None = None) -> str:
    """Le milieu de l'écran, en HTML. Tout texte venu des données est protégé (aucune balise ne passe)."""
    if vue["refuse"]:
        return f"<p class='refus'>Accès refusé : {_e(vue['raison'])}. Ce refus est noté au journal des accès.</p>"
    mots, jour, patients = _mots(_langue(ecran, vue, demandee)), vue["donnees"]["jour"], vue["donnees"]["patients"]
    if ecran == "patient":
        p = patients[0]
        from .ecrans_soir import dessiner_invitation
        soir = dessiner_invitation(vue["donnees"].get("soir") or {}, vue["badge"]["id"])  # le soir seulement
        return soir + (f"<article><h3>{_e(p.get('nom', ''))}</h3><p class='ou'>{_e(mots['chambre'])} {_e(p.get('chambre', '?'))}"
                f" · {_e(mots['etage'])} {_e(p.get('etage', '?'))}</p><h4>{_e(mots['mon_programme'])}</h4>"
                f"{_programme_du_jour(p, jour, mots)}<h4>{_e(mots['mes_documents'])}</h4>"
                f"{_liste(_titres(p.get('documents')), mots)}</article>")
    titre = mots["arrivees"] if ecran == "accueil" else mots["mes_patients"]
    haut = ""
    if vue["donnees"].get("taches_pour_moi"):
        from .ecrans_soir import dessiner_taches_pour_moi
        haut = dessiner_taches_pour_moi(vue["donnees"]["taches_pour_moi"])
    if "papiers" in vue["donnees"]:  # l'accueil : le bouton vers les papiers à valider, même sans arrivée
        from .ecrans_papiers import dessiner_lien_papiers
        haut = dessiner_lien_papiers(vue["donnees"]["papiers"], vue["badge"]["id"])
    if "nouvelle_admin" in vue["donnees"]:  # si le logiciel se tait, la vue reste, et cette heure se voit
        nouvelle = vue["donnees"]["nouvelle_admin"]
        quand = (f"dernière nouvelle reçue à {nouvelle['heure']} (jour {nouvelle['jour']})" if nouvelle else "aucune nouvelle reçue")
        haut += f"<p class='ou'>Logiciel administratif (SIMULÉ) : {_e(quand)}.</p>"
    if vue["donnees"].get("sorties_accueil"):
        from .ecrans_listes import dessiner_sorties_accueil
        haut += dessiner_sorties_accueil(vue["donnees"]["sorties_accueil"], vue["badge"]["id"])
    if vue["donnees"].get("appels_du_hall"):
        from .ecrans_accueil import dessiner_appels
        haut += dessiner_appels(vue["donnees"]["appels_du_hall"])
    if not patients:
        return haut + f"<h2>{_e(titre)}</h2><p class='rien'>{_e(mots['personne'])}</p>"
    if "prise_de_poste" in vue["donnees"]:
        from .ecrans_listes import dessiner_prise_de_poste
        from .ecrans_listes import dessiner_taches
        from .ecrans_accueil import dessiner_messages
        haut = (dessiner_messages(vue["donnees"].get("messages_du_hall") or [])
                + dessiner_prise_de_poste(vue["donnees"]["prise_de_poste"], vue["badge"]["id"])
                + dessiner_taches(vue["donnees"].get("taches") or [], vue["donnees"].get("robot_branche", False),
                                  vue["badge"]["id"]))
    titres = vue["donnees"].get("listes")
    resumes = vue["donnees"].get("resumes")
    if resumes is not None:  # l'écran du médecin : la recherche en haut, le résumé au-dessus de chaque fiche
        from .ecrans_resume import dessiner_recherche, dessiner_resume
        from .ecrans_soir import lien_dictee
        haut += dessiner_recherche(vue["badge"]["id"])  # H02 : d'abord les tâches pour lui (les questions du soir), s'il y en a
        return haut + f"<h2>{_e(titre)} ({len(patients)})</h2>" + "".join(
            (dessiner_resume(resumes[p["id"]], vue["badge"]["id"]) if p["id"] in resumes else "")
            + _carte(p, ecran, jour, mots, titres, vue["badge"]["id"]) + lien_dictee(vue["badge"]["id"], p["id"])
            for p in patients)
    return haut + f"<h2>{_e(titre)} ({len(patients)})</h2>" + "".join(
        _carte(p, ecran, jour, mots, titres, vue["badge"]["id"]) for p in patients)


STYLE = """
*{box-sizing:border-box}body{margin:0;font:17px/1.45 -apple-system,system-ui,sans-serif;background:#f4f5f7;color:#16202a}
.bandeau{background:#b00020;color:#fff;text-align:center;font-weight:700;padding:.45rem .5rem;letter-spacing:.03em}
header{background:#fff;padding:.6rem .9rem;border-bottom:1px solid #d5d9df;display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center}
header h1{font-size:1.2rem;margin:0}.heure{font-weight:700}.accelere{background:#ffd54a;padding:0 .35rem;border-radius:.3rem}
select,a.l{font:inherit;padding:.3rem .5rem}main{padding:.9rem;max-width:46rem;margin:auto}
article{background:#fff;border:1px solid #d5d9df;border-radius:.6rem;padding:.7rem .9rem;margin:.7rem 0}
h2{font-size:1.15rem}h3{margin:.1rem 0;font-size:1.1rem}h4{margin:.7rem 0 .2rem;font-size:.95rem;color:#44505c}
ul{margin:.2rem 0;padding-left:1.2rem}.ou,.rien,footer{color:#5a6570}.refus{background:#fff3cd;padding:.7rem;border-radius:.5rem}
footer{padding:.9rem;font-size:.85rem;text-align:center}.vieux{background:#ffe0b2;padding:.4rem .9rem;display:none}
.age{font-size:.85rem;padding:.15rem .9rem;color:#555}.age.vieille{background:#ffe0b2;color:#16181d;font-weight:700}
.grise{opacity:.45;filter:grayscale(1)}
@media (max-width:600px){table{table-layout:fixed;font-size:.7rem}td,th{padding:.2rem .2rem;overflow-wrap:anywhere;hyphens:auto}}
main{overflow-x:auto}table{border-collapse:collapse;width:100%;background:#fff;font-size:.85rem}td,th{border:1px solid #d5d9df;padding:.25rem .4rem;text-align:left}
button,a.bouton{font:inherit;padding:.45rem .8rem;border:1px solid #8a94a0;border-radius:.5rem;background:#eef1f5;color:inherit;text-decoration:none;display:inline-block;margin:.15rem .2rem .15rem 0}
ul.liens,ul.points{list-style:none;padding-left:0}ul.points li{background:#fff;border:1px solid #d5d9df;border-radius:.6rem;padding:.6rem .8rem;margin:.4rem 0}
li.fait{color:#2e6b3a}.dit{background:#e8f0fe;border-radius:.6rem;padding:.7rem .9rem;margin:.6rem 0;font-size:1.1rem}.dit:empty{display:none}
nav a{display:block;background:#fff;border:1px solid #d5d9df;border-radius:.6rem;padding:.9rem;margin:.6rem 0;font-size:1.2rem;color:inherit}
"""

LEGENDE = ("Étiquettes : " + " · ".join(ETIQUETTES) + ". Sur cet écran, pour l'instant : rien n'est fait par un robot ; "
           "tout ce qui est affiché est une donnée inventée.")


def _heure_html(heure: dict[str, Any]) -> str:
    base = f"Jour {heure['jour']} — {int(heure['heure'][:2])} h {heure['heure'][3:]}"
    marque = f" <span class='accelere'>{_e(heure['marque'].upper())}</span>" if heure["temps_accelere"] else ""
    return _e(base) + marque


# Avenant 2, K07 : sur les écrans Invité et Patient, de gros caractères. Aucun texte plus petit que le seuil des réglages
# (ecran.taille_texte_min_px, mesuré dans Chrome par lisibilite.py). Les autres écrans gardent leur style.
STYLE_LISIBLE = (
    "body.lisible{font-size:1.25rem;line-height:1.5}"
    "body.lisible .age,body.lisible footer,body.lisible footer a,body.lisible label,body.lisible input,body.lisible .bandeau,"
    "body.lisible h4,body.lisible .heure,body.lisible .ou,body.lisible table,body.lisible td,body.lisible th,body.lisible small,"
    "body.lisible code,body.lisible .vieux,body.lisible li,body.lisible p,body.lisible span,body.lisible button,"
    "body.lisible a,body.lisible select{font-size:max(1.15rem,18px)!important}"
    "body.lisible h1{font-size:2.2rem}body.lisible h2{font-size:1.6rem}body.lisible h3{font-size:1.35rem}"
    "body.lisible .age.vieille{color:#16181d}body.lisible .ou{color:#2b2f36}")
CORPS_LISIBLE = " class='lisible'"


def _page(titre: str, entete: str, milieu: str, script: str = "", lisible: bool = False) -> str:
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{_e(titre)}</title>"
            f"<style>{STYLE}{STYLE_LISIBLE if lisible else ''}</style></head><body{CORPS_LISIBLE if lisible else ''}>"
            f"<div class='bandeau'>{BANDEAU}</div><header>{entete}</header>"
            f"<div class='vieux' id='vieux'>Connexion perdue : ce qui est affiché peut être vieux.</div>"
            f"<div class='age' id='age'></div>"
            f"<main id='contenu'>{milieu}</main><footer>{_e(LEGENDE)}<br><a href=\"/clinique\">Tous les écrans</a></footer>"
            f"{script}</body></html>")


def dessiner_page(clinique: Clinique, ecran: str, badge: Badge, demandee: str | None) -> str:
    titre, role, langues = ECRANS[ecran]
    vue = lire_ecran(clinique, ecran, badge)
    langue = _langue(ecran, vue, demandee)
    du_metier = [b for b in clinique.badges.values() if b.role == role]
    choix = "".join(f"<option value=\"{_e(b.id)}\"{' selected' if b.id == badge.id else ''}>{_e(b.libelle)}</option>"
                    for b in du_metier)
    if badge.role != role:  # un badge d'un autre métier, arrivé par l'adresse : on le montre, il est refusé plus bas
        choix = f"<option selected disabled>{_e(badge.libelle)}</option>" + choix
    liens = "".join(f" <a class='l' href=\"?badge={_e(badge.id)}&amp;langue={l}\">{'<b>' + l + '</b>' if l == langue else l}</a>"
                    for l in langues) if len(langues) > 1 else ""
    entete = (f"<h1>{_e(titre)}</h1><span class='heure' id='heure'>{_heure_html(vue['horloge'])}</span>"
              f"<label>Badge : <select id='badge'>{choix}</select></label><span>{liens}</span>")
    suite = "?" + "&".join(f"{cle}={valeur}" for cle, valeur in (("badge", badge.id), ("langue", langue)))
    script = script_de_mise_a_jour(f"/clinique/{ecran}/contenu" + suite, avec_badge=True)
    return _page(f"Clinique — {titre}", entete, dessiner_contenu(ecran, vue, langue), script, lisible=ecran == "patient")


def script_de_mise_a_jour(chemin: str, avec_badge: bool = False, limite_s: int = LIMITE_VIEUX_S) -> str:
    """Le secours : la page redemande son milieu et l'heure toutes les deux secondes. Si ça rate, elle le dit.
    L'âge de l'information (avenant 2, K03) : « mis à jour il y a tant de secondes » ; au-delà de `limite_s`, la zone se
    grise et dit « information vieille de tant de secondes »."""
    badge = ("document.getElementById('badge').onchange = e => { location.search = '?badge=' + "
             "encodeURIComponent(e.target.value); };") if avec_badge else ""
    return f"""<script>
{badge}
async function rafraichir() {{
  try {{
    const c = await fetch({json.dumps(chemin)}, {{cache: 'no-store'}});
    const h = await fetch('/clinique/heure', {{cache: 'no-store'}});
    if (!c.ok || !h.ok) throw new Error('réponse');
    // N01b : on ne remplace le milieu de la page que s'il a changé. Sinon, un lien remplacé sous le doigt pendant un
    // clic perdait ce clic (vu dans un vrai navigateur : « Source » ne s'ouvrait pas).
    const recu = await c.text();
    // Et jamais pendant qu'un doigt ou un bouton de souris est appuyé : on attend le tour suivant.
    if (recu !== dernierContenu && !appuye) {{
      document.getElementById('contenu').innerHTML = recu;
      dernierContenu = recu;
    }}
    const heure = await h.text();
    if (heure !== derniereHeure) {{ document.getElementById('heure').innerHTML = heure; derniereHeure = heure; }}
    document.getElementById('vieux').style.display = 'none';
    derniereMiseAJour = Date.now();
    direLAge();
  }} catch (erreur) {{ document.getElementById('vieux').style.display = 'block'; }}
}}
const LIMITE_VIEUX_S = {int(limite_s)};
let derniereMiseAJour = Date.now();
let dernierContenu = null, derniereHeure = null;  // ce que le serveur a rendu la dernière fois
let appuye = false;  // un doigt ou un bouton de souris est-il appuyé sur la page ?
if (typeof window !== 'undefined' && window.addEventListener) {{  // dans un navigateur (pas dans l'essai sans page)
  for (const debut of ['mousedown', 'touchstart']) window.addEventListener(debut, () => {{ appuye = true; }}, true);
  for (const fin of ['mouseup', 'touchend', 'touchcancel', 'blur']) window.addEventListener(fin, () => {{ appuye = false; }}, true);
}}
function direLAge() {{
  const secondes = Math.floor((Date.now() - derniereMiseAJour) / 1000);
  const mot = secondes <= 1 ? ' seconde' : ' secondes';
  const zone = document.getElementById('contenu'), age = document.getElementById('age');
  if (secondes > LIMITE_VIEUX_S) {{
    zone.classList.add('grise');
    age.className = 'age vieille';
    age.textContent = 'information vieille de ' + secondes + mot;
  }} else {{
    zone.classList.remove('grise');
    age.className = 'age';
    age.textContent = 'mis à jour il y a ' + secondes + mot;
  }}
}}
setInterval(rafraichir, {RAFRAICHIR_MS});
setInterval(direLAge, 1000);
direLAge();
</script>"""


def dessiner_journal(clinique: Clinique) -> str:
    lignes = clinique.porte.journal.lignes()[-200:]
    rangs = "".join(f"<tr><td>{_e(l['quand'][11:19])}</td><td>{_e(l['qui'])}{' pour ' + _e(l['pour']) if l.get('pour') else ''}</td>"
                    f"<td>{_e(l['quoi'])}</td><td>{_e(', '.join(l['patients']))}</td><td>{_e(l['resultat'])}</td>"
                    f"<td>{_e(l.get('raison', ''))}</td></tr>" for l in reversed(lignes))
    entete = f"<h1>Journal des accès</h1><span class='heure'>{_heure_html(clinique.horloge.etat())}</span>"
    milieu = (f"<p>Qui a lu quoi, quand. Les {len(lignes)} dernières lignes, la plus récente en haut. Heure réelle (UTC). "
              "Des numéros de dossier, jamais de nom.</p><table><tr><th>Quand</th><th>Qui</th><th>Quoi</th>"
              f"<th>Dossiers</th><th>Résultat</th><th>Raison</th></tr>{rangs}</table>")
    return _page("Clinique — Journal des accès", entete, milieu)


def dessiner_entree(clinique: Clinique) -> str:
    liens = "".join(f"<a href=\"/clinique/{ecran}\">{_e(titre)}</a>" for ecran, (titre, _, _) in ECRANS.items())
    entete = f"<h1>La clinique en boîte</h1><span class='heure'>{_heure_html(clinique.horloge.etat())}</span>"
    return _page("La clinique en boîte", entete,
                 f"<nav>{liens}<a href=\"/clinique/hall\">Hall (le robot d'accueil)</a><a href=\"/clinique/flotte\">Flotte (les quatre robots)</a><a href=\"/clinique/tableau-de-flotte\">Tableau de flotte (le plan, la batterie)</a><a href=\"/clinique/fiche-de-verite\">Fiche de vérité (la dernière répétition)</a><a href=\"/clinique/invite\">Invité (un juré aux commandes)</a><a href=\"/clinique/telephones\">Sur un téléphone (les adresses du Wi-Fi)</a><a href=\"/clinique/preuves\">Preuves (huit questions du jury)</a><a href=\"/clinique/concours\">Concours (le tirage, les chiffres, les capacités, l'invité)</a><a href=\"/clinique/qui-decide\">Qui décide</a><a href=\"/clinique/regie\">Régie (interprète)</a><a href=\"/clinique/tirage\">Demande au hasard</a><a href=\"/clinique/sources\">D'où vient cette donnée ?</a><a href=\"/clinique/aide-humaine\">Aide humaine</a><a href=\"/clinique/essais-reels\">Essais réels (pour l'équipe)</a><a href=\"/clinique/pannes\">Pannes (pour l'équipe)</a><a href=\"/clinique/moments\">Moments (pour l'équipe)</a><a href=\"/clinique/ce-qu-on-nous-a-dit\">Ce qu'on nous a dit</a><a href=\"/clinique/direction\">Direction</a><a href=\"/clinique/journal\">Journal des accès</a></nav>")


# ---------------------------------------------------------------------- brancher
def brancher_ecrans(app: FastAPI, porte: PorteDeLecture | None = None, horloge: HorlogeDeDemonstration | None = None,
                    badges: dict[str, Badge] | None = None, carnet: Carnet | None = None, systeme=None,
                    code_equipe: str | None = None) -> Clinique:
    """Ajoute les pages de la clinique à une application (celle de la brique 13, ou une application vide)."""
    horloge = horloge or HorlogeDeDemonstration()
    porte = porte or PorteDeLecture(jour=horloge.jour)
    carnet = carnet or Carnet.de_la_seance(horloge)
    listes = ListesDeSoin(porte, carnet)
    clinique = Clinique(porte, horloge, badges or charger_badges(), carnet, listes,
                        TableauDesTaches(porte, carnet, listes))
    robots = [b for b in clinique.badges.values() if b.role == "robot"]
    if systeme is not None and robots:  # un robot est branché : les demandes partent, toujours sous le gardien
        from .coursier import Coursier
        clinique.coursier = Coursier(systeme, clinique.taches, listes, robots[0])

    def badge_de(ecran: str, identifiant: str | None) -> Badge:
        if ecran not in ECRANS:
            raise HTTPException(404, "Cet écran n'existe pas. La liste : /clinique")
        if identifiant is None:
            du_metier = [b for b in clinique.badges.values() if b.role == ECRANS[ecran][1]]
            if not du_metier:
                raise HTTPException(404, "Aucun badge pour cet écran dans badges.yaml")
            return du_metier[0]
        if identifiant not in clinique.badges:
            raise HTTPException(404, "Ce badge n'existe pas")
        return clinique.badges[identifiant]

    if robots:  # l'accueil du hall est tenu par un robot (ici : une phrase tapée, aucun robot ne bouge)
        from .accueil import AccueilDuHall
        from .ecrans_accueil import brancher_accueil
        clinique.accueil = AccueilDuHall(porte, carnet, robots[0])
        brancher_accueil(app, clinique)

    from .ecrans_papiers import brancher_papiers
    from .papiers import Papiers
    clinique.papiers = Papiers(porte, carnet)
    brancher_papiers(app, clinique, badge_de)

    from .ecrans_resume import brancher_resume
    from .resume import ResumeDuMedecin
    clinique.resume = ResumeDuMedecin(porte, carnet, horloge)
    from .resume_apertus import brancher_si_demande
    brancher_si_demande(clinique.resume)  # T13 : Apertus n'écrit le résumé que si l'équipe le demande au lancement
    brancher_resume(app, clinique, badge_de)

    # Le compteur d'essais réels : ses boutons demandent le code d'équipe, comme les boutons protégés de la brique 13.
    from briques.b13_ecran.serveur import code_equipe_de, controle_acces
    from .essais_reels import CompteurReel, brancher_essais_reels
    reglages_ecran = (systeme.reglages.get("ecran") or {}) if systeme is not None else {}
    if code_equipe is None:
        code_equipe = code_equipe_de(systeme.reglages) if systeme is not None else ""
    protege = [Depends(controle_acces(code_equipe, bool(reglages_ecran.get("local_sans_code", True))))]
    clinique.essais_reels = CompteurReel()
    brancher_essais_reels(app, clinique, protege)
    from .lien_logiciel import brancher_faux_logiciel
    brancher_faux_logiciel(app, clinique, protege, bus=systeme.bus if systeme is not None else getattr(horloge, "bus", None))
    from .qui_decide import brancher_qui_decide
    brancher_qui_decide(app)
    from .tirage import brancher_tirage
    brancher_tirage(app, clinique, protege)
    from .interprete_ecran import brancher_interprete  # H10b : la régie, le mode interprète (français dit → anglais)
    brancher_interprete(app, clinique, protege)
    from .sources import brancher_sources
    brancher_sources(app)
    from .etageres import brancher_etageres
    brancher_etageres(app, clinique, protege)
    from .aide_humaine import brancher_aide_humaine
    brancher_aide_humaine(app, clinique, protege, bus=systeme.bus if systeme is not None else getattr(horloge, "bus", None))
    if systeme is not None:  # la main humaine de l'ossature (brique 11) : reprise et gestes télécommandés comptent comme des aides
        from .aide_humaine import ecouter_la_main
        ecouter_la_main(systeme.bus, clinique.taches, vrai_robot=lambda: systeme.prise.carte().vrai_robot)

    from .pannes import Pannes, brancher_pannes
    clinique.pannes = Pannes(carnet, clinique.taches, clinique.coursier, systeme, bus=getattr(horloge, "bus", None))
    clinique.pannes.resume, clinique.pannes.papiers = clinique.resume, clinique.papiers
    brancher_pannes(app, clinique, protege)

    from .paroles import brancher_paroles
    brancher_paroles(app, clinique)

    from .moments import brancher_moments
    brancher_moments(app, clinique, protege, systeme)

    from .flotte import Flotte, brancher_flotte
    from .cartes_gardien import brancher_les_cartes
    cartes_de_role, carte_r1 = brancher_les_cartes(clinique.coursier, systeme)  # la carte de R1 ira chez le gardien
    clinique.flotte = Flotte(clinique.taches, carnet, clinique.coursier, cartes=cartes_de_role, carte_r1=carte_r1)
    from .ecrans_pauses import brancher_pauses
    from .pauses import Pauses
    clinique.pauses_des_soignants = Pauses(porte, carnet, horloge,
                                           bus=systeme.bus if systeme is not None else getattr(horloge, "bus", None))
    if carte_r1 is not None:  # le gardien applique les pauses avec la carte de rôle, au prochain geste du robot
        carte_r1.pauses = clinique.pauses_des_soignants

        from contextlib import asynccontextmanager

        cycle_d_avant = app.router.lifespan_context

        @asynccontextmanager
        async def cycle_avec_la_carte(application):
            """Relecture de la tranche 3 : la carte va chez le gardien dès le démarrage, pas seulement au premier geste.
            Si cela rate, le serveur démarre quand même : le coursier réessaie avant son premier geste, et la page le dit."""
            async with cycle_d_avant(application) as etat:
                try:
                    if not carte_r1.appliquee():
                        await carte_r1.appliquer()
                except Exception:  # noqa: BLE001
                    pass
                yield etat

        app.router.lifespan_context = cycle_avec_la_carte
    brancher_pauses(app, clinique)
    brancher_flotte(app, clinique)
    from .avis import brancher_avis  # K06 : l'avis des personnes (oui de Hiba à Q9, à ses conditions)
    brancher_avis(app, clinique, protege)
    from .capacites import brancher_capacites  # K05 : le tableau des capacités, et la page « Concours »
    brancher_capacites(app)
    from .preuves import brancher_preuves  # J07a : la page des preuves, huit questions
    brancher_preuves(app, clinique)
    from .reseau_local import brancher_reseau_local  # T30 : les adresses du Wi-Fi, pour les téléphones
    brancher_reseau_local(app, ecoute=reglages_ecran.get("hote"), port_des_reglages=reglages_ecran.get("port"))
    from .invite import brancher_invite  # K07a : l'écran « Invité », pour un juré aux commandes
    brancher_invite(app, clinique, protege, bus=systeme.bus if systeme is not None else getattr(horloge, "bus", None))
    from .ecrans_fiche import brancher_fiche  # T27 : la fiche de vérité de la dernière répétition
    brancher_fiche(app)
    from .tableau_flotte import brancher_tableau_de_flotte  # T25 : le plan, la batterie, la panne et la reprise, « Pourquoi ? »
    brancher_tableau_de_flotte(app, clinique, protege, cartes_de_role)

    from .ecrans_soir import brancher_soir
    from .soir import LeSoir
    clinique.soir = LeSoir(porte, carnet, horloge, clinique.taches, clinique.badges)
    brancher_soir(app, clinique)

    from .ecrans_listes import brancher_listes
    brancher_listes(app, clinique, badge_de)  # avant « /clinique/{ecran} », pour que « /clinique/direction » soit trouvée

    @app.get("/clinique", response_class=HTMLResponse)
    async def entree():
        return dessiner_entree(clinique)

    @app.get("/clinique/journal", response_class=HTMLResponse)
    async def page_journal():
        return dessiner_journal(clinique)

    @app.get("/clinique/heure", response_class=HTMLResponse)
    async def heure():
        # toutes les pages redemandent ce morceau toutes les deux secondes : une panne s'y affiche, partout
        return _heure_html(clinique.horloge.etat()) + (clinique.pannes.bandeau() if clinique.pannes is not None else "")

    @app.get("/clinique/{ecran}", response_class=HTMLResponse)
    async def page(ecran: str, badge: str | None = None, langue: str | None = None):
        return dessiner_page(clinique, ecran, badge_de(ecran, badge), langue)

    @app.get("/clinique/{ecran}/contenu", response_class=HTMLResponse)
    async def contenu(ecran: str, badge: str | None = None, langue: str | None = None):
        return dessiner_contenu(ecran, lire_ecran(clinique, ecran, badge_de(ecran, badge)), langue)

    @app.get("/api/clinique/ecran/{ecran}")
    async def api_ecran(ecran: str, badge: str | None = None):
        return lire_ecran(clinique, ecran, badge_de(ecran, badge))

    @app.get("/api/clinique/horloge")
    async def api_horloge():
        return clinique.horloge.etat()

    @app.get("/api/clinique/badges")
    async def api_badges():
        ecran_du_role = {role: ecran for ecran, (_, role, _) in ECRANS.items()}
        return {"badges": [{"id": b.id, "role": b.role, "libelle": b.libelle, "ecran": ecran_du_role.get(b.role)}
                           for b in clinique.badges.values()]}

    @app.get("/api/clinique/journal")
    async def api_journal():
        return {"marque": "données inventées", "lignes": clinique.porte.journal.lignes()[-200:]}

    return clinique


# ---------------------------------------------------------------------- l'adresse du réseau local
def adresse_du_reseau_local() -> str | None:
    """L'adresse de cet ordinateur sur le réseau local (celle qu'un téléphone du même Wi-Fi utiliserait), ou None.
    Aucun message n'est envoyé : on demande seulement au système par quelle adresse il sortirait."""
    prise = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        prise.connect(("192.0.2.1", 9))  # adresse réservée aux exemples ; en UDP, « connect » n'envoie rien
        adresse = prise.getsockname()[0]
    except OSError:
        return None
    finally:
        prise.close()
    return None if adresse.startswith("127.") or adresse == "0.0.0.0" else adresse
