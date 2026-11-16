"""Le résumé du médecin à l'écran (cahier 5.4 et 5.7, tâche T08) : le résumé, la source qui s'ouvre, la recherche.

    /clinique/medecin                         le résumé de chaque patient, au-dessus de sa fiche
    /clinique/medecin/source?patient=…&ref=…  un doigt sur une source : elle s'ouvre
    /clinique/medecin/recherche?q=…           « la lettre du médecin de Madame B. » ouvre le document

Tout passe par la pièce resume.py, donc par la porte de lecture. Un refus est montré et noté.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .ecrans import Clinique, _e, _heure_html, _page
from .porte import AccesRefuse, Badge
from .resume import RIEN


def _lien_source(badge: str, patient: str, ref: str) -> str:
    return f"/clinique/medecin/source?badge={quote(badge)}&amp;patient={quote(patient)}&amp;ref={quote(ref)}"


def dessiner_recherche(badge: str, question: str = "") -> str:
    return (f"<form class='recherche' method='get' action=\"/clinique/medecin/recherche\">"
            f"<input type='hidden' name='badge' value=\"{_e(badge)}\">"
            f"<label>Chercher un document : <input name='q' value=\"{_e(question)}\" size='34' "
            f"placeholder=\"la lettre du médecin de Madame B.\"></label> <button>Ouvrir</button></form>")


def dessiner_resume(resume: dict[str, Any], badge: str) -> str:
    """Les cinq lignes d'un patient. Chaque source est un bouton : un doigt dessus, elle s'ouvre."""
    lignes = []
    for ligne in resume["lignes"]:
        sources = "".join(f" <a class='bouton source' href=\"{_lien_source(badge, resume['patient'], s['ref'])}\">"
                          f"Source : {_e(s['titre'])}</a>" for s in ligne["sources"])
        classe = "rien" if ligne["texte"] == RIEN else ("desaccord" if ligne["desaccord"] else "")
        pas_sur = f" <i class='ou'>({_e(ligne['pas_sur'])})</i>" if ligne.get("pas_sur") else ""  # T13
        lignes.append(f"<li class='{classe}'><b>{_e(ligne['titre'])}</b> : {_e(ligne['texte'])}{pas_sur}{sources}</li>")
    prepare = resume.get("prepare") or {}
    quand = f"{'Refait' if resume.get('refait') else 'Préparé'} : {_e(prepare.get('texte', '?'))}"
    if resume.get("fige"):  # pendant la panne du cerveau : ce qui est vieux se voit
        quand += f". <b style='background:#ffd54a'>{_e(resume['fige'])}</b>"
    return (f"<article class='resume'><h3>Résumé — {_e(resume['nom'])}</h3>"
            f"<p class='ou'>Version : {_e(resume['version'])}. {quand}. Il recopie ses sources, il ne conclut pas.</p>"
            f"<ul class='points'>{''.join(lignes)}</ul></article>")


def dessiner_source(source: dict[str, Any]) -> str:
    return (f"<article><h3>{_e(source['titre'])}</h3><p class='ou'>{_e(source['genre'])} · {_e(source['nom'])} · "
            f"référence {_e(source['ref'])}</p><pre style='white-space:pre-wrap;font:inherit'>{_e(source['texte'])}</pre></article>")


def brancher_resume(app: FastAPI, clinique: Clinique, badge_de) -> None:
    def page(titre: str, badge: Badge, milieu: str) -> str:
        entete = (f"<h1>{_e(titre)}</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                  f"<span>Badge : <b>{_e(badge.libelle)}</b></span>"
                  f"<a class='bouton' href=\"/clinique/medecin?badge={_e(badge.id)}\">Retour</a>")
        return _page(f"Clinique — {titre}", entete, milieu)

    @app.get("/clinique/medecin/source", response_class=HTMLResponse)
    async def page_source(patient: str, ref: str, badge: str | None = None):
        b = badge_de("medecin", badge)
        try:
            milieu = dessiner_source(clinique.resume.source(b, patient, ref))
        except AccesRefuse as refus:
            milieu = f"<p class='refus'>Accès refusé : {_e(refus)}. Ce refus est noté au journal des accès.</p>"
        return page("Source", b, milieu)

    @app.get("/clinique/medecin/recherche", response_class=HTMLResponse)
    async def page_recherche(q: str = "", badge: str | None = None):
        b = badge_de("medecin", badge)
        try:
            trouve = clinique.resume.chercher(b, q)
        except AccesRefuse as refus:
            return page("Recherche", b, f"<p class='refus'>Accès refusé : {_e(refus)}. Ce refus est noté au journal des accès.</p>")
        milieu = dessiner_recherche(b.id, q) + f"<p class='dit'>{_e(trouve['dit'])}</p>"
        if trouve["trouve"]:
            milieu += dessiner_source(trouve["document"])
        for candidat in trouve.get("candidats") or ():
            milieu += (f"<p><a class='bouton' href=\"{_lien_source(b.id, trouve['patient'], candidat['ref'])}\">"
                       f"{_e(candidat['genre'])} : {_e(candidat['titre'])}</a></p>")
        return page("Recherche", b, milieu)

    @app.get("/api/clinique/resume")
    async def api_resume(badge: str, patient: str):
        try:
            return clinique.resume.resume(badge_de("medecin", badge), patient)
        except AccesRefuse as refus:
            return {"refuse": True, "raison": str(refus), "marque": "données inventées"}


# ---------------------------------------------------------------------- la grande répétition
# H04 (réponse de Hiba à Q11) : les deux demandes dites sur scène. La seconde n'a pas de réponse : Madame B. n'a pas de
# rapport de radiologie dans le faux dossier. Le prototype doit le dire, et ne rien ouvrir.
DEMANDE_QUI_S_OUVRE = "la lettre du médecin de Madame B."
DEMANDE_SANS_DOCUMENT = "le dernier rapport de radiologie de Madame B."
REPONSE_VRAIE = "Je ne trouve pas ce document"


def etape_10():
    """Étape 10 : le lendemain, le résumé, chaque ligne avec sa source. Par la vraie page, demandée par le programme."""
    import asyncio
    import re

    from fastapi.testclient import TestClient

    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture
    from .repetition import Resultat

    horloge = HorlogeDeDemonstration()
    asyncio.run(horloge.sauter("le lendemain matin"))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    medecin = clinique.badges["medecin-exemple"]
    resumes = clinique.resume.preparer(medecin)
    lignes = [l for r in resumes for l in r["lignes"]]
    dites = [l for l in lignes if l["texte"] != RIEN]
    sans_source = [l["titre"] for l in dites if not l["sources"]]
    client = TestClient(app)
    page = client.get("/clinique/medecin", params={"badge": medecin.id})
    liens = sorted(set(re.findall(r'href="(/clinique/medecin/source\?[^"]+)"', page.text)))
    fermees = []
    for lien in liens:  # une page de refus répond aussi « 200 » : on regarde ce qu'elle dit
        ouverte = client.get(lien.replace("&amp;", "&"))
        if ouverte.status_code != 200 or "Accès refusé" in ouverte.text or "référence " not in ouverte.text:
            fermees.append(lien)
    giulia = next((r for r in resumes if r["patient"] == "p01"), None)
    # H04 : les deux demandes de la scène, par la vraie page de recherche
    lettre = client.get("/clinique/medecin/recherche", params={"badge": medecin.id, "q": DEMANDE_QUI_S_OUVRE}).text
    radio = client.get("/clinique/medecin/recherche", params={"badge": medecin.id, "q": DEMANDE_SANS_DOCUMENT}).text
    lettre_ouverte = "référence " in lettre and REPONSE_VRAIE not in lettre
    radio_vraie = REPONSE_VRAIE in radio and "référence " not in radio
    reussie = (page.status_code == 200 and giulia is not None and "Madame Giulia B." in page.text and bool(dites)
               and not sans_source and bool(liens) and not fermees and all(len(r["lignes"]) <= 5 for r in resumes)
               and horloge.etat()["jour"] == 2 and lettre_ouverte and radio_vraie)
    return Resultat(reussie, "SIMULÉ",
                    f"page demandée par le programme, pas sur une tablette ; version simple, sans modèle ; jour "
                    f"{horloge.etat()['jour']} ; {len(dites)} lignes avec leur source, {len(lignes) - len(dites)} « {RIEN} » ; "
                    f"{len(liens)} sources ouvertes"
                    + (f" ; recherche : {DEMANDE_QUI_S_OUVRE} s'ouvre" if lettre_ouverte
                       else f" ; RATÉ : « {DEMANDE_QUI_S_OUVRE} » (la lettre du médecin) ne s'ouvre pas")
                    + (f" ; le rapport de radiologie, qu'elle n'a pas : « {REPONSE_VRAIE} », rien ne s'ouvre" if radio_vraie
                       else " ; RATÉ : la demande du rapport de radiologie n'a pas reçu la réponse vraie, ou un document s'est ouvert")
                    + (f" ; sans source : {sans_source}" if sans_source else "")
                    + (f" ; sources qui ne s'ouvrent pas : {fermees}" if fermees else ""),
                    {"phrases_retirees": sum(r.get("retirees", 0) for r in resumes)})
