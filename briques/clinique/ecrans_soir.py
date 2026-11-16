"""Le soir et la dictée à l'écran (cahier 4.2, 5.4 ; tâche T11b). Version simple : tout est tapé.

    /clinique/patient/soir?badge=…                 la patiente : la question du soir, dans sa langue, et un champ
    /clinique/medecin/dictee?badge=…&patient=…     le médecin : il tape sa phrase (la voix : tâche T18)
    POST /api/clinique/soir/question   {badge, texte}
    POST /api/clinique/dictee          {badge, patient, texte}

Sur l'écran de la patiente, le soir : la question et un bouton. Sur l'écran du thérapeute : les tâches pour lui.
Aucune voix, aucun modèle, aucun robot : étiquette SIMULÉ.
"""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .ecrans import Clinique, _e, _heure_html, _page
from .ecrans_listes import _du_meme_site, _essayer, _heure_courte
from .porte import AccesRefuse, Badge
from .soir import MENTION_BROUILLON, phrases

Court = Annotated[str, Field(max_length=60)]


class Question(BaseModel):
    badge: Court
    texte: Annotated[str, Field(max_length=400)]


class Dictee(BaseModel):
    badge: Court
    patient: Court
    texte: Annotated[str, Field(max_length=400)]


def _script(adresse: str, corps_fixe: dict[str, Any]) -> str:
    """Un champ, un bouton : on envoie le texte, on affiche ce que le prototype dit, puis la page se recharge."""
    return f"""<script>
document.getElementById('saisie').addEventListener('submit', async e => {{
  e.preventDefault();
  const texte = document.getElementById('texte').value;
  const dit = document.getElementById('dit');
  try {{
    const r = await fetch({json.dumps(adresse)}, {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(Object.assign({json.dumps(corps_fixe)}, {{texte}}))}});
    const j = await r.json();
    dit.textContent = r.ok ? j.dit : ('Refusé : ' + (j.detail || ''));
    if (r.ok) {{ document.getElementById('texte').value = ''; setTimeout(() => location.reload(), 2500); }}
  }} catch (erreur) {{ dit.textContent = 'Connexion perdue.'; }}
}});
</script>"""


# ---------------------------------------------------------------------- les morceaux dessinés sur les autres écrans
def dessiner_invitation(invitation: dict[str, Any], badge: str) -> str:
    """Sur l'écran de la patiente, le soir seulement : la question, dans sa langue, et le bouton pour répondre."""
    if not invitation.get("a_poser"):
        return ""
    mots = phrases(invitation["langue"])
    return (f"<article><p class='dit'>{_e(invitation['phrase'])}</p>"
            f"<a class='bouton' href=\"/clinique/patient/soir?badge={_e(badge)}\">{_e(mots['bouton'])}</a>"
            f"{_deja(invitation, mots)}</article>")


def _deja(invitation: dict[str, Any], mots: dict[str, str]) -> str:
    if not invitation.get("deja"):
        return ""
    return f"<h4>{_e(mots['deja'])}</h4><ul>" + "".join(f"<li>{_e(q)}</li>" for q in invitation["deja"]) + "</ul>"


def dessiner_taches_pour_moi(taches: list[dict[str, Any]]) -> str:
    """Sur l'écran du thérapeute : ce qu'un collègue lui demande. Sur celui du médecin (H02) : les questions du soir de
    ses patients, à qui il doit répondre. Rien si rien."""
    if not taches:
        return ""
    lignes = "".join(
        f"<li><b>{_e(t['quoi'])}</b> — {_e(t['nom_du_patient'])}, {_e(t['ou'])} — pour : {_e(t['pour_quand'])} — "
        f"demandé par {_e(t['qui_demande'])} ({_e(_heure_courte(t.get('quand')))}) — <b>{_e(t['etat'])}</b>"
        f"{' — ' + _e(t['mention']) if t.get('mention') else ''}</li>" for t in taches)
    return f"<article><h2>Tâches pour moi ({len(taches)})</h2><ul>{lignes}</ul></article>"


def lien_dictee(badge: str, patient: str) -> str:
    return (f"<p><a class='bouton' href=\"/clinique/medecin/dictee?badge={_e(badge)}&amp;patient={_e(patient)}\">"
            f"Demander quelque chose à l'équipe</a></p>")


# ---------------------------------------------------------------------- brancher
def brancher_soir(app: FastAPI, clinique: Clinique) -> None:
    du_meme_site = [Depends(_du_meme_site)]

    def badge_connu(identifiant: str | None, role: str) -> Badge:
        if identifiant is None:
            du_metier = [b for b in clinique.badges.values() if b.role == role]
            if not du_metier:
                raise HTTPException(404, "Aucun badge pour cet écran dans badges.yaml")
            return du_metier[0]
        if identifiant not in clinique.badges:
            raise HTTPException(404, "Ce badge n'existe pas")
        return clinique.badges[identifiant]

    def entete(titre: str, badge: Badge, retour: str) -> str:
        return (f"<h1>{_e(titre)}</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                f"<span>Badge : <b>{_e(badge.libelle)}</b></span><a class='l' href=\"{retour}\">← Retour</a>")

    def refus(raison: Any) -> str:
        return f"<p class='refus'>Accès refusé : {_e(raison)}. Ce refus est noté au journal des accès.</p>"

    @app.get("/clinique/patient/soir", response_class=HTMLResponse)
    async def page_soir(badge: str | None = None):
        b = badge_connu(badge, "patient")
        retour = f"/clinique/patient?badge={_e(b.id)}"
        try:
            invitation = clinique.soir.invitation(b)
        except AccesRefuse as non:
            return _page("Clinique — Le soir", entete("Le soir", b, retour), refus(non))
        mots = phrases(invitation["langue"])
        note = "<p class='ou'><b>SIMULÉ</b> : la question est tapée, pas dite. Elle part chez le médecin dans sa langue. Seules les deux questions du scénario ont une traduction, fixe, écrite d'avance ; les autres arrivent « non traduites ».</p>"
        if not invitation["a_poser"]:
            return _page("Clinique — Le soir", entete("Le soir", b, retour),
                         note + "<p class='rien'>Ce n'est pas encore le soir.</p>")
        milieu = (f"{note}<p class='dit'>{_e(invitation['phrase'])}</p>"
                  f"<form id='saisie'><input id='texte' size='34' maxlength='200' lang=\"{_e(invitation['langue'])}\"> "
                  f"<button>{_e(mots['envoyer'])}</button></form><div class='dit' id='dit' role='status'></div>"
                  f"{_deja(invitation, mots)}")
        return _page("Clinique — Le soir", entete("Le soir", b, retour), milieu,
                     _script("/api/clinique/soir/question", {"badge": b.id}))

    @app.get("/clinique/medecin/dictee", response_class=HTMLResponse)
    async def page_dictee(patient: str, badge: str | None = None):
        b = badge_connu(badge, "médecin")
        retour = f"/clinique/medecin?badge={_e(b.id)}"
        try:
            if b.role != "médecin":
                clinique.porte.refuser(b, "dictée", "seul le médecin dicte")
            personne = clinique.porte.patient(b, patient)
        except AccesRefuse as non:
            return _page("Clinique — Dictée", entete("Dictée", b, retour), refus(non))
        milieu = (f"<p class='ou'><b>SIMULÉ</b> : la phrase est tapée, pas dictée à la voix. Elle devient un "
                  f"brouillon (« {_e(MENTION_BROUILLON)} ») et une tâche pour un humain.</p>"
                  f"<h3>{_e(personne['nom'])}</h3>"
                  f"<form id='saisie'><input id='texte' size='34' maxlength='200' "
                  f"placeholder=\"Physio, évaluer la marche demain.\"> <button>Noter</button></form>"
                  f"<div class='dit' id='dit' role='status'></div>")
        return _page("Clinique — Dictée", entete("Dictée", b, retour), milieu,
                     _script("/api/clinique/dictee", {"badge": b.id, "patient": patient}))

    @app.post("/api/clinique/soir/question", dependencies=du_meme_site)
    async def api_question(q: Question):
        b = badge_connu(q.badge, "patient")
        return _essayer(lambda: clinique.soir.poser(b, q.texte))

    @app.post("/api/clinique/dictee", dependencies=du_meme_site)
    async def api_dictee(d: Dictee):
        b = badge_connu(d.badge, "médecin")
        # Micro en panne (J02) : la phrase arrive comme du bruit, avec une confiance très basse : rien n'est noté.
        texte, confiance = clinique.pannes.entendre(d.texte) if clinique.pannes is not None else (d.texte, 1.0)
        return _essayer(lambda: clinique.soir.dicter(b, d.patient, texte, confiance))


# ---------------------------------------------------------------------- la grande répétition
QUESTIONS_DU_SCENARIO = ("Quando potrò camminare senza deambulatore?", "Mia figlia può venire domenica?")
DICTEE_DU_SCENARIO = "Physio, évaluer la marche demain."


def _jouer(*sauts: str):
    import asyncio

    from fastapi.testclient import TestClient

    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture

    horloge = HorlogeDeDemonstration()
    for saut in sauts:
        asyncio.run(horloge.sauter(saut))
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique, horloge


def etape_9():
    """Étape 9 : le soir, les deux questions de la patiente arrivent chez le médecin."""
    import asyncio

    from .repetition import Resultat

    client, clinique, horloge = _jouer("le soir")
    patiente, medecin = "patient-p01", "medecin-exemple"
    ecran = client.get("/clinique/patient", params={"badge": patiente}).text
    posee = "Ha domande per il medico domani?" in ecran
    reponses = [client.post("/api/clinique/soir/question", json={"badge": patiente, "texte": q}) for q in QUESTIONS_DU_SCENARIO]
    transmises = all(r.status_code == 200 and "trasmessa al medico" in r.json().get("dit", "") for r in reponses)
    asyncio.run(horloge.sauter("le lendemain matin"))
    page = client.get("/clinique/medecin", params={"badge": medecin}).text
    resume = clinique.resume.resume(clinique.badges[medecin], "p01")
    ligne = next((l for l in resume["lignes"] if l["point"] == "questions"), {"texte": "", "sources": []})
    arrivees = [q for q in QUESTIONS_DU_SCENARIO if q in ligne["texte"] and _e(q) in page]
    reussie = (posee and transmises and len(arrivees) == 2 and len(ligne["sources"]) == 2
               and horloge.etat()["jour"] == 2 and len(clinique.carnet.lignes("question du soir")) == 2)
    return Resultat(reussie, "SIMULÉ",
                    f"questions tapées par le programme, pas par une patiente, sans voix ; à 19 h l'écran de la patiente "
                    f"{'pose' if posee else 'NE pose PAS'} la question en italien ; {len(arrivees)} questions sur 2 dans le "
                    f"résumé du médecin au jour {horloge.etat()['jour']}, avec {len(ligne['sources'])} sources ; "
                    f"{sum(1 for l in clinique.carnet.lignes('question du soir') if l['donnees'].get('traduction'))} traduites par "
                    f"les traductions fixes du scénario (un fichier, pas un modèle), texte d'origine à côté ; le prototype "
                    f"transmet et ne répond pas")


def etape_11():
    """Étape 11 : la dictée devient une tâche pour le thérapeute."""
    from .repetition import Resultat

    client, clinique, horloge = _jouer("le soir", "le lendemain matin", "visite")
    from . import dossier

    medecin, therapeute = "medecin-exemple", "therapeute-exemple"
    empreinte = dossier.empreinte()
    avant = client.get("/clinique/therapeute", params={"badge": therapeute}).text
    r = client.post("/api/clinique/dictee", json={"badge": medecin, "patient": "p01", "texte": DICTEE_DU_SCENARIO})
    reponse = r.json() if r.status_code == 200 else {}
    tache, brouillon = reponse.get("tache", {}), reponse.get("brouillon", {})
    page = client.get("/clinique/therapeute", params={"badge": therapeute}).text
    visible = "évaluer la marche demain" in page and "évaluer la marche demain" not in avant
    reussie = (visible and tache.get("pour") == "thérapeute" and tache.get("sorte") == "humain"
               and brouillon.get("mention") == MENTION_BROUILLON and len(clinique.carnet.lignes("brouillon")) == 1)
    inchange = dossier.empreinte() == empreinte
    reussie = reussie and inchange
    return Resultat(reussie, "SIMULÉ",
                    f"phrase tapée par le programme, pas dictée à la voix (la voix : tâche T18) ; « {DICTEE_DU_SCENARIO} » → "
                    f"brouillon « {brouillon.get('mention', '?')} » ; tâche pour un humain ({tache.get('pour', '?')}, "
                    f"{tache.get('pour_quand', '?')}) {'visible' if visible else 'ABSENTE'} sur l'écran du thérapeute "
                    f"(page demandée par le programme) ; empreinte du faux dossier "
                    f"{'inchangée' if inchange else 'CHANGÉE'} avant et après")
