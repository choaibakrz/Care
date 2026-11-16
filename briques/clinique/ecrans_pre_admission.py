"""La pré-admission à l'écran (avenant 4, L04 ; seconde moitié) : les boutons, la proposition, la phrase fixe.

    GET  /clinique/pre-admission?badge=accueil      la proposition, ses sources, corriger, valider
    POST /api/clinique/pre-admission/arriver        le bouton du chef : « Faire arriver deux papiers » (code d'équipe)
    POST /api/clinique/pre-admission/preparer       « Préparer une pré-admission » (badge accueil)
    POST /api/clinique/pre-admission/corriger       corriger un champ (badge accueil)
    POST /api/clinique/pre-admission/valider        valider d'un doigt : alors seulement, le message part (badge accueil)

« L'assistant prépare. Une personne décide. » La porte décide qui a le droit : seul le badge « accueil ».
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .porte import AccesRefuse
from .pre_admission import CHAMPS, ETIQUETTE, IDS_DES_PAPIERS, PHRASE, Refus

Court = Annotated[str, Field(max_length=80)]
NOMS = {"nom": "Nom", "prenom": "Prénom", "date_naissance": "Date de naissance", "langue": "Langue", "assurance": "Assurance",
        "date_arrivee_prevue": "Date d'arrivée prévue"}


class Demande(BaseModel):
    badge: Court


class Correction(BaseModel):
    badge: Court
    numero: Court
    champ: Court
    valeur: Court = ""


class Validation(BaseModel):
    badge: Court
    numero: Court


SCRIPT = """<script>
const badge = new URLSearchParams(location.search).get('badge') || 'accueil';
const dit = document.getElementById('dit');
async function envoyer(chemin, corps, code) {
  const tete = {'Content-Type': 'application/json'};
  if (code) tete['X-Code-Equipe'] = code;
  const r = await fetch('/api/clinique/pre-admission/' + chemin, {method: 'POST', headers: tete, body: JSON.stringify(corps)});
  const j = await r.json();
  if (!r.ok) { dit.textContent = 'Refusé : ' + (j.detail || r.status); return; }
  location.reload();
}
const par = (id, f) => { const e = document.getElementById(id); if (e) e.onclick = f; };
par('arriver', () => envoyer('arriver', {}, document.getElementById('code').value));
par('preparer', () => envoyer('preparer', {badge}));
document.querySelectorAll('button[data-champ]').forEach(b => b.onclick = () =>
  envoyer('corriger', {badge, numero: b.dataset.numero, champ: b.dataset.champ, valeur: document.getElementById('v-' + b.dataset.champ).value}));
par('valider', () => envoyer('valider', {badge, numero: document.getElementById('valider').dataset.numero}));
</script>"""


def lien_dans_a_trier(pile: dict[str, Any], badge: str) -> str:
    """Dans « à trier » : si les deux papiers de la pré-admission attendent, le bouton « Préparer une pré-admission »."""
    from .ecrans import _e

    if not set(IDS_DES_PAPIERS) <= {p["id"] for p in pile.get("a_trier", [])}:
        return ""
    return (f"<p><a class='bouton' href=\"/clinique/pre-admission?badge={_e(badge)}\">Préparer une pré-admission</a> "
            f"à partir des deux papiers qui attendent. {_e(PHRASE)}</p>")


def _proposition(p: dict[str, Any]) -> str:
    from .ecrans import _e

    ouverte = p["etat"] == "proposée"
    rangs = []
    for champ in CHAMPS:
        c = p["champs"][champ]
        etat = f"confiance : {c['confiance']}" if c["confiance"] else c["dit"]
        corriger = (f"<input id='v-{champ}' size='22' maxlength='80' value=\"{_e(c['valeur'])}\"> "
                    f"<button data-champ='{champ}' data-numero=\"{_e(p['numero'])}\">Corriger</button>") if ouverte else ""
        rangs.append(f"<tr><th>{_e(NOMS[champ])}</th><td><b>{_e(c['valeur'] or '—')}</b></td>"
                     f"<td>{_e(', '.join(c['sources']) or 'aucun papier')}</td><td>{_e(etat)}</td><td>{corriger}</td></tr>")
    if ouverte:
        suite = (f"<p><button class='bouton' id='valider' data-numero=\"{_e(p['numero'])}\">Valider et envoyer la pré-admission</button></p>"
                 "<p class='ou'>Rien n'est encore parti vers le logiciel administratif. Le message part seulement après ce bouton.</p>")
    elif p["etat"] == "validée":
        v = p["valide"]
        suite = (f"<p class='dit'>Validée par {_e(v['par'])}, jour {_e(v['quand']['jour'])}, {_e(v['quand']['heure'])}. "
                 f"Le message est parti ({_e(p.get('fichier', ''))}). Le logiciel administratif n'a pas encore admis la personne.</p>")
    else:
        a = p.get("admise") or {}
        suite = (f"<p class='dit'>La personne est admise par le logiciel administratif : numéro de patient {_e(a.get('numero_patient', '?'))}. "
                 "La boucle est fermée.</p>")
    return (f"<article><h2>Pré-admission {_e(p['numero'])} — {_e(p['etat'])}</h2>"
            f"<table><tr><th>Champ</th><th>Valeur</th><th>Papier d'où il vient</th><th>Confiance</th><th></th></tr>{''.join(rangs)}</table>"
            f"{suite}</article>")


def dessiner(clinique, badge) -> str:
    from .ecrans import _e

    tete = (f"<p class='dit'><b>{_e(PHRASE)}</b></p><p class='ou'>{ETIQUETTE} — données inventées. L'assistant remplit la "
            "pré-admission à partir de deux papiers ; une personne de l'accueil corrige et valide. Avant, rien ne part.</p>")
    try:
        propositions = clinique.pre_admissions().propositions(badge)
    except AccesRefuse as refus:
        return tete + f"<p class='refus'>Refus : {_e(refus)}. Ce refus est noté au journal des accès.</p>"
    chef = ("<p class='ou'>Chef de démonstration : <label>code d'équipe <input id='code' size='10' type='password' autocomplete='off'></label> "
            "<button id='arriver'>Faire arriver deux papiers</button></p>")
    preparer = "<p><button class='bouton' id='preparer'>Préparer une pré-admission</button></p>" if not propositions else ""
    return (tete + chef + preparer + "<div class='dit' id='dit' role='status'></div>"
            + "".join(_proposition(p) for p in propositions))


def brancher_pre_admission(app, clinique, protege: list) -> None:
    from .ecrans import _page

    def badge_de(identifiant: str):
        badge = clinique.badges.get(identifiant)
        if badge is None:
            raise HTTPException(403, "badge inconnu")
        return badge

    def essayer(geste) -> Any:
        try:
            return geste()
        except AccesRefuse as refus:
            raise HTTPException(403, str(refus))
        except Refus as refus:
            raise HTTPException(400, str(refus))

    @app.get("/clinique/pre-admission", response_class=HTMLResponse)
    async def page_pre_admission(badge: str = "accueil"):
        return _page("Clinique — Pré-admission", "<h1>Pré-admission</h1>", dessiner(clinique, badge_de(badge)), SCRIPT)

    @app.get("/api/clinique/pre-admission")
    async def api_lire(badge: str):
        return {"marque": "données inventées", "phrase": PHRASE,
                "propositions": essayer(lambda: clinique.pre_admissions().propositions(badge_de(badge)))}

    @app.post("/api/clinique/pre-admission/arriver", dependencies=protege)
    async def api_arriver():
        return {"papiers": clinique.pre_admissions().faire_arriver()}

    @app.post("/api/clinique/pre-admission/preparer")
    async def api_preparer(d: Demande):
        return {"proposition": essayer(lambda: clinique.pre_admissions().preparer(badge_de(d.badge)))}

    @app.post("/api/clinique/pre-admission/corriger")
    async def api_corriger(c: Correction):
        return {"proposition": essayer(lambda: clinique.pre_admissions().corriger(badge_de(c.badge), c.numero, c.champ, c.valeur))}

    @app.post("/api/clinique/pre-admission/valider")
    async def api_valider(v: Validation):
        try:
            return {"proposition": await clinique.pre_admissions().valider(badge_de(v.badge), v.numero)}
        except AccesRefuse as refus:
            raise HTTPException(403, str(refus))
        except Refus as refus:
            raise HTTPException(400, str(refus))
