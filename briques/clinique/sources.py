"""D'où vient chaque donnée (avenant 4, tâche L01).

« Dans une vraie clinique, d'où viendraient vos données ? » La table `sources_des_donnees.yaml` le dit, pour chaque
sorte de donnée : ADMIN (le logiciel administratif), SOINS (le dossier de soins), INCONNU (nous ne savons pas quel
outil), NOUS (ce que le prototype crée : le carnet).

    table = charger()
    sans_source(dossier.charger(), table)     # les sortes de données du faux dossier que la table oublie : [] si tout va bien
    qui_lit(table)                            # pour chaque ligne : les badges qui la lisent, demandés à la VRAIE porte
    ce_que_recoit("robot", table)             # tout ce que la porte donne à un badge, et de quelles sources

Cette pièce LIT seulement. Elle ne change ni le faux dossier, ni la porte de lecture.
DIRE VRAI : aucun lien avec un vrai logiciel de clinique ; le prototype ne se connecte à rien. Les sources sont celles
de l'avenant de Hiba ; pour le plan des lieux, la réserve et les feuilles volantes, nous ne savons pas : INCONNU.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

from . import dossier
from .porte import AccesRefuse, JournalDesAcces, PorteDeLecture, charger_badges

FICHIER = Path(__file__).resolve().parent / "sources_des_donnees.yaml"
SOURCES = ("ADMIN", "SOINS", "INCONNU", "NOUS")
ROLES = ("patient", "soignant", "thérapeute", "médecin", "accueil", "direction", "robot")


class TableInvalide(ValueError):
    """La table des sources est mal écrite. Le message dit quoi."""


def charger(fichier: Path = FICHIER) -> list[dict[str, Any]]:
    brut = yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))
    if not isinstance(brut, dict) or brut.get("marque") != "inventé":
        raise TableInvalide(f"{Path(fichier).name} : la marque « inventé » manque")
    lignes = []
    for ligne in brut.get("lignes") or []:
        sorte = ligne.get("sorte") or "?"
        if ligne.get("source") not in SOURCES:
            raise TableInvalide(f"{sorte} : source « {ligne.get('source')} » inconnue (sources : {', '.join(SOURCES)})")
        if not str(ligne.get("explication") or "").strip():
            raise TableInvalide(f"{sorte} : il manque l'explication")
        lignes.append({"sorte": sorte, "source": ligne["source"], "explication": ligne["explication"],
                       **{c: list(ligne.get(c) or []) for c in ("champs", "genres", "fichiers", "vue", "acces", "carnet", "lu_par")}})
    if not lignes:
        raise TableInvalide(f"{Path(fichier).name} : aucune ligne")
    return lignes


def noms_des_sources(fichier: Path = FICHIER) -> dict[str, str]:
    return dict(yaml.safe_load(Path(fichier).read_text(encoding="utf-8"))["sources"])


def en_clair(objet: Any) -> Any:
    """Une fiche du faux dossier (figée) → des dictionnaires et des listes ordinaires."""
    if hasattr(objet, "items"):
        return {c: en_clair(v) for c, v in objet.items()}
    if isinstance(objet, (list, tuple)):
        return [en_clair(v) for v in objet]
    return objet


def sans_source(d, table: list[dict[str, Any]], patients: list[dict[str, Any]] | None = None) -> list[str]:
    """Les sortes de données du faux dossier qui n'ont pas de source dans la table. [] : tout a une source."""
    champs = {c for l in table for c in l["champs"]}
    genres = {g for l in table for g in l["genres"]}
    fichiers = {f for l in table for f in l["fichiers"]}
    manquent: set[str] = set()
    for p in patients if patients is not None else [en_clair(p) for p in d.patients]:
        for cle, valeur in p.items():
            if cle in champs:
                continue
            if cle == "DocumentReference":
                manquent |= {f"DocumentReference : genre « {doc.get('genre')} »" for doc in valeur if doc.get("genre") not in genres}
            elif isinstance(valeur, dict):
                manquent |= {f"{cle}.{sous}" for sous in valeur if f"{cle}.{sous}" not in champs}
            else:
                manquent.add(cle)
    for champ in dataclasses.fields(d):
        if champ.name != "patients" and champ.name not in fichiers:
            manquent.add(f"fichier du faux dossier : {champ.name}")
    return sorted(manquent)


def _ce_que_donne_la_porte(role: str) -> tuple[set[str], set[str]]:
    """Ce que la vraie porte donne à un badge de ce métier : les clés de ses vues, et les autres accès permis."""
    porte = PorteDeLecture(journal=JournalDesAcces())
    badge = next((b for b in charger_badges().values() if b.role == role), None)
    cles: set[str] = set()
    acces: set[str] = set()
    if badge is None:
        return cles, acces
    lectures = {"patients": lambda: porte.patients(badge), "hall": lambda: porte.arrivees_pour_le_hall(badge)}
    for lire in lectures.values():
        try:
            for vue in lire():
                cles |= set(vue)
        except AccesRefuse:
            pass
    autres = {"lieux": lambda: porte.lieux(badge), "reserve": lambda: porte.reserve(badge),
              "feuilles_sans_patient": lambda: porte.feuilles_sans_patient(badge), "comptes": lambda: porte.comptes(badge),
              "liste_de_soin": lambda: porte.liste_de_soin(badge, porte.dossier.listes[0]["id"])}
    for nom, lire in autres.items():
        try:
            lire()
            acces.add(nom)
        except AccesRefuse:
            pass
    return cles, acces


def qui_lit(table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pour chaque ligne de la table : les badges qui ont le droit de la lire, demandés à la vraie porte de lecture."""
    donne = {role: _ce_que_donne_la_porte(role) for role in ROLES}
    lignes = []
    for ligne in table:
        if ligne["carnet"]:
            badges = list(ligne["lu_par"])
        else:
            badges = [role for role in ROLES
                      if set(ligne["vue"]) & donne[role][0] or set(ligne["acces"]) & donne[role][1]]
        lignes.append({**ligne, "badges": badges})
    return lignes


def ce_que_recoit(role: str, table: list[dict[str, Any]]) -> dict[str, Any]:
    """Tout ce que la porte donne à ce badge : les clés, celles qui n'ont pas de ligne dans la table, et les sources."""
    cles, acces = _ce_que_donne_la_porte(role)
    sources: set[str] = set()
    sans_ligne = []
    for cle in sorted(cles):
        lignes = [l for l in table if cle in l["vue"]]
        sources |= {l["source"] for l in lignes}
        if not lignes:
            sans_ligne.append(cle)
    for nom in sorted(acces):
        lignes = [l for l in table if nom in l["acces"]]
        sources |= {l["source"] for l in lignes}
        if not lignes:
            sans_ligne.append(f"accès : {nom}")
    return {"cles": sorted(cles), "acces": sorted(acces), "sans_ligne": sans_ligne, "sources": sorted(sources)}


# ---------------------------------------------------------------------- la page
def dessiner() -> str:
    from .ecrans import _e

    table, noms = charger(), noms_des_sources()
    manquent = sans_source(dossier.charger(), table)
    rangs = "".join(f"<tr><td><b>{_e(l['sorte'])}</b></td><td><b>{_e(l['source'])}</b> — {_e(noms[l['source']])}</td>"
                    f"<td>{_e(l['explication'])}</td><td>{_e(', '.join(l['badges']) or 'aucun')}</td></tr>"
                    for l in qui_lit(table))
    etat = ("<p><b>Toutes les données du faux dossier ont une source.</b></p>" if not manquent else
            f"<p class='dit'><b>Sans source dans la table :</b> {_e(' ; '.join(manquent))}</p>")
    robot = ce_que_recoit("robot", table)
    return ("<p class='ou'>Données inventées. « Dans une vraie clinique, d'où viendraient ces données ? » Cette table le dit, "
            "pour chaque sorte de donnée. Aucun lien avec un vrai logiciel de clinique : le prototype ne se connecte à rien.</p>"
            f"{etat}<table><tr><th>Sorte de donnée</th><th>Source</th><th>Ce que c'est</th><th>Badges qui la lisent</th></tr>{rangs}</table>"
            f"<p class='ou'>Le badge « robot » reçoit des données de ces sources : {_e(', '.join(robot['sources']))}. "
            "Jamais SOINS. L'assistant lit comme la personne pour qui il travaille. Les badges de chaque ligne sont demandés à "
            "la porte de lecture ; pour le carnet, ils sont écrits dans la table.</p>")


def brancher_sources(app) -> None:
    from fastapi.responses import HTMLResponse

    from .ecrans import _page

    @app.get("/clinique/sources", response_class=HTMLResponse)
    async def page_sources():
        return _page("Clinique — D'où vient cette donnée ?", "<h1>D'où vient cette donnée ?</h1>", dessiner(), "")

    @app.get("/api/clinique/sources")
    async def api_sources():
        table = charger()
        return {"marque": "données inventées", "sources": noms_des_sources(), "sans_source": sans_source(dossier.charger(), table),
                "lignes": [{c: l[c] for c in ("sorte", "source", "explication", "badges")} for l in qui_lit(table)]}
