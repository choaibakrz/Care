"""La page du faux logiciel administratif — SIMULÉ (avenant 4, L02). Pour le chef de démonstration.

Ce n'est pas un écran de la clinique en boîte : cette page a son propre dossier et son propre style. Elle montre la
liste administrative, un bouton par sorte de message, et le bouton « Remettre le faux logiciel à zéro ».
Elle ne connaît pas la clinique en boîte : celui qui la branche lui donne
- `protege` : qui a le droit d'ouvrir la page et d'appuyer (la liste porte des noms inventés) ;
- `apres_message` : ce qu'il faut faire après chaque message écrit (la clinique le note dans sa boîte noire) ;
- `lien_assistant` : l'adresse de l'écran de la clinique. Le bouton « Ouvrir l'assistant » ne lui passe que le numéro
  du patient et le numéro du séjour, jamais un nom.
"""
from __future__ import annotations

import html
import inspect
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .logiciel import CORRIGEABLES, ETIQUETTE, LANGUES, SORTES, FauxLogiciel, Refus

STYLE = ("body{font-family:Georgia,serif;margin:0;background:#f3f0e8;color:#222}header{background:#3b3a36;color:#fff;padding:.6rem 1rem}"
         "main{padding:1rem}table{border-collapse:collapse;width:100%;background:#fff}td,th{border:1px solid #bbb;padding:.3rem .5rem;"
         "text-align:left;vertical-align:top}button{margin:.1rem;padding:.3rem .5rem}.marque{background:#ffd54d;color:#222;"
         "padding:.3rem 1rem;font-weight:bold}.gris{color:#666}#dit{margin:.6rem 0;font-weight:bold}")
SCRIPT = """<script>
const dit = document.getElementById('dit');
function tete() { const t = {'Content-Type': 'application/json'}; const c = document.getElementById('code').value;
  if (c) t['X-Code-Equipe'] = c; return t; }
async function envoyer(chemin, corps) {
  const r = await fetch(chemin, {method: 'POST', headers: tete(), body: JSON.stringify(corps || {})});
  const j = await r.json();
  if (!r.ok) { dit.textContent = 'Refusé : ' + (j.detail || r.status); return; }
  location.reload();
}
document.querySelectorAll('button[data-sorte]').forEach(b => b.onclick = () => {
  const rang = b.closest('tr');
  envoyer('/api/faux-logiciel/evenement', {sorte: b.dataset.sorte, numero_patient: rang.dataset.patient,
    chambre: rang.querySelector('.chambre').value, champ: rang.querySelector('.champ').value,
    valeur: rang.querySelector('.valeur').value});
});
document.querySelectorAll('button[data-pre]').forEach(b => b.onclick = () =>
  envoyer('/api/faux-logiciel/admettre', {numero: b.dataset.pre, chambre: b.closest('tr').querySelector('.chambre').value}));
document.getElementById('zero').onclick = () => envoyer('/api/faux-logiciel/zero');
</script>"""


class Admission(BaseModel):
    numero: str
    chambre: str | None = None


class Evenement(BaseModel):
    sorte: str
    numero_patient: str
    chambre: str | None = None
    champ: str | None = None
    valeur: str | None = None


def _e(texte: Any) -> str:
    return html.escape(str(texte if texte is not None else ""))


def _coquille(titre: str, milieu: str, script: str = "") -> str:
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, "
            f"initial-scale=1'><title>{_e(titre)}</title><style>{STYLE}</style></head><body>"
            f"<div class='marque'>{ETIQUETTE} — DONNÉES INVENTÉES — Ce n'est pas un vrai logiciel de clinique, et il n'est relié à aucun.</div>"
            f"<header><h1>{_e(titre)} — {ETIQUETTE}</h1></header><main>{milieu}</main>{script}</body></html>")


def _lien_assistant(lien: str, p: dict[str, Any]) -> str:
    return f"{lien}?patient={_e(p['numero_patient'])}&amp;sejour={_e(p['numero_sejour'])}"


def dessiner(faux: FauxLogiciel, lien_assistant: str) -> str:
    chambres = "".join(f"<option>{_e(c)}</option>" for c in faux.chambres)
    champs = "".join(f"<option>{_e(c)}</option>" for c in CORRIGEABLES)
    rangs = []
    for p in faux.liste():
        if p["verrouille"]:
            gestes = "<span class='gris'>verrouillé : personne du faux dossier, le faux logiciel ne la change pas</span>"
        else:
            boutons = "".join(f"<button data-sorte='{code}' title='{_e(s['nom'])} ({code})'>{_e(s['bouton'])}</button>"
                              for code, s in SORTES.items())
            gestes = (f"chambre <select class='chambre'>{chambres}</select> · corriger <select class='champ'>{champs}</select> "
                      f"<input class='valeur' size='10' maxlength='60' placeholder='{'/'.join(LANGUES)}…'><br>{boutons}")
        rangs.append(
            f"<tr data-patient='{_e(p['numero_patient'])}'><td>{_e(p['numero_patient'])}</td><td>{_e(p['numero_sejour'])}</td>"
            f"<td>{_e(p['nom'])}</td><td>{_e(p['date_naissance'])}</td><td>{_e(p['langue'])}</td><td>{_e(p['chambre'])}</td>"
            f"<td>{_e(p['jour_entree'] if p['jour_entree'] is not None else '')}</td>"
            f"<td>{_e(p['jour_sortie_prevue'] if p['jour_sortie_prevue'] is not None else '')}</td><td>{_e(p['assurance'])}</td>"
            f"<td><b>{_e(p['statut'])}</b></td><td>{gestes}</td>"
            f"<td><a href=\"{_lien_assistant(lien_assistant, p)}\">Ouvrir l'assistant</a></td></tr>")
    messages = "".join(f"<li>{_e(f.name)}</li>" for f in faux.messages()) or "<li class='gris'>aucun message écrit</li>"
    recues = "".join(
        f"<tr><td>{_e(r['numero'])}</td><td>{_e(r['prenom'])} {_e(r['nom'])}</td><td>{_e(r['date_naissance'])}</td><td>{_e(r['langue'])}</td>"
        f"<td>{_e(r['assurance'])}</td><td>{_e(r['date_arrivee_prevue'])}</td><td><b>{_e(r['statut'])}</b> {_e(r['numero_patient'])}</td>"
        + (f"<td>chambre <select class='chambre'>{chambres}</select> <button data-pre='{_e(r['numero'])}'>Admettre la pré-admission</button></td>"
           if r["statut"] == "reçue" else "<td></td>") + "</tr>"
        for r in faux.pre_admissions_recues()) or "<tr><td colspan='8' class='gris'>aucune pré-admission reçue</td></tr>"
    return ("<p>Pour le chef de démonstration. Chaque bouton écrit un message (un fichier texte) dans le dossier « du logiciel vers "
            "nous ». Les boutons n'agissent que sur les personnes en attente et sur celles admises par message.</p>"
            "<p><label>Code d'équipe (depuis un autre ordinateur) <input id='code' size='12' type='password' autocomplete='off'></label> "
            "<button id='zero'>Remettre le faux logiciel à zéro</button></p><div id='dit' role='status'></div>"
            "<table><tr><th>N° patient</th><th>N° séjour</th><th>Nom (inventé)</th><th>Naissance</th><th>Langue</th><th>Chambre</th>"
            "<th>Jour d'entrée</th><th>Jour de sortie prévue</th><th>Assurance</th><th>Statut</th><th>Événements</th><th></th></tr>"
            f"{''.join(rangs)}</table>"
            "<h2>Pré-admissions reçues (de l'autre système vers le logiciel)</h2>"
            "<table><tr><th>N° de pré-admission</th><th>Prénom, nom</th><th>Naissance</th><th>Langue</th><th>Assurance</th>"
            f"<th>Arrivée prévue</th><th>Statut</th><th></th></tr>{recues}</table>"
            f"<h2>Messages écrits (du logiciel vers nous)</h2><ul>{messages}</ul>"
            "<p class='gris'>Messages fabriqués par nous au standard HL7 version 2.5 ; jamais essayés avec un vrai logiciel de clinique.</p>")


def dessiner_fiche(faux: FauxLogiciel, numero: str, lien_assistant: str) -> str:
    p = next((x for x in faux.liste() if x["numero_patient"] == numero), None)
    if p is None:
        raise HTTPException(404, "numéro de patient inconnu dans le faux logiciel")
    lignes = [("Numéro du patient", p["numero_patient"]), ("Numéro du séjour", p["numero_sejour"]), ("Nom (inventé)", p["nom"]),
              ("Date de naissance", p["date_naissance"] or "(vide)"), ("Langue", p["langue"]), ("Chambre", p["chambre"] or "(aucune)"),
              ("Jour d'entrée", p["jour_entree"] if p["jour_entree"] is not None else "(pas encore)"),
              ("Jour de sortie prévue", p["jour_sortie_prevue"] if p["jour_sortie_prevue"] is not None else "(pas encore)"),
              ("Assurance", p["assurance"]), ("Statut", p["statut"])]
    rangs = "".join(f"<tr><th>{_e(c)}</th><td>{_e(v)}</td></tr>" for c, v in lignes)
    return (f"<table>{rangs}</table><p><a href=\"{_lien_assistant(lien_assistant, p)}\">Ouvrir l'assistant</a> · "
            "<a href='/faux-logiciel'>Toute la liste</a></p><p class='gris'>Fiche administrative seulement : rien de médical ici.</p>")


def brancher(app, logiciel: Callable[[], FauxLogiciel], protege: list, lien_assistant: str = "/clinique/ouvrir",
             apres_message: Callable[[dict[str, Any]], Any] | None = None, pied: Callable[[], str] | None = None,
             apres_zero: Callable[[], Any] | None = None) -> None:
    """Ajoute la page du faux logiciel à une application. `logiciel()` rend le faux logiciel à utiliser.
    `pied()` : une ligne que le système qui lit les messages veut montrer ici (le délai de lecture)."""

    @app.get("/faux-logiciel", response_class=HTMLResponse, dependencies=protege)
    async def page_faux_logiciel():
        bas = f"<p class='gris'>{_e(pied())}</p>" if pied is not None else ""
        return _coquille("Faux logiciel administratif", dessiner(logiciel(), lien_assistant) + bas, SCRIPT)

    @app.get("/faux-logiciel/fiche", response_class=HTMLResponse, dependencies=protege)
    async def page_fiche(patient: str):
        return _coquille("Faux logiciel administratif — fiche", dessiner_fiche(logiciel(), patient, lien_assistant))

    @app.get("/api/faux-logiciel", dependencies=protege)
    async def api_lire():
        faux = logiciel()
        return {"etiquette": ETIQUETTE, "marque": "données inventées", "liste": faux.liste(),
                "messages": [f.name for f in faux.messages()]}

    @app.post("/api/faux-logiciel/evenement", dependencies=protege)
    async def api_evenement(e: Evenement):
        try:
            message = logiciel().evenement(e.sorte, e.numero_patient, chambre=e.chambre, champ=e.champ, valeur=e.valeur)
        except Refus as refus:
            raise HTTPException(400, str(refus))
        if apres_message is not None:
            suite = apres_message(message)
            if inspect.isawaitable(suite):
                await suite
        return {"message": message}

    @app.post("/api/faux-logiciel/admettre", dependencies=protege)
    async def api_admettre(a: Admission):
        try:
            message = logiciel().admettre_pre_admission(a.numero, a.chambre)
        except Refus as refus:
            raise HTTPException(400, str(refus))
        if apres_message is not None:
            suite = apres_message(message)
            if inspect.isawaitable(suite):
                await suite
        return {"message": message}

    @app.post("/api/faux-logiciel/zero", dependencies=protege)
    async def api_zero():
        logiciel().remettre_a_zero()
        if apres_zero is not None:
            apres_zero()
        return {"fait": True, "liste": logiciel().liste()}
