"""L'accueil du hall à l'écran (cahier 5.4 et 5.9, tâche T10) : la phrase tapée, la réponse du robot, le chemin.

    /clinique/hall                         l'écran du robot du hall : on tape la phrase d'arrivée, il répond
    POST /api/clinique/hall/entendre       {texte} → ce que le robot dit, le chemin, ce qu'il a transmis

Le message à l'étage s'affiche sur l'écran du soignant ; l'appel d'un humain, sur l'écran de l'accueil.
Aucun robot ne bouge, aucune voix : étiquette SIMULÉ.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .ecrans import Clinique, _e, _heure_html, _page
from .ecrans_listes import _du_meme_site, _heure_courte


class Phrase(BaseModel):
    texte: Annotated[str, Field(max_length=200)]
    langue: Annotated[str, Field(max_length=5)] | None = None


SCRIPT_HALL = """<script>
function mettre(id, texte) { document.getElementById(id).textContent = texte; }
document.getElementById('hall').addEventListener('submit', async e => {
  e.preventDefault();
  const texte = document.getElementById('phrase').value;
  if (!texte) return;
  try {
    const r = await fetch('/api/clinique/hall/entendre', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({texte})});
    const j = await r.json();
    if (!r.ok) { mettre('dit', 'Refusé.'); return; }
    mettre('dit', j.dit);
    mettre('chemin', j.chemin.length ? 'Le chemin : ' + j.chemin.map(p => p.lieu + (p.metres ? ' (' + p.metres + ' m)' : '')).join(' → ') : '');
    mettre('suite', 'Langue : ' + j.langue + (j.langue_sure ? '' : ' (pas reconnue : français par défaut)') + ' · cas : ' + j.cas
      + (j.etage_prevenu ? ' · étage prévenu' : '') + (j.appel ? ' · un humain est appelé : ' + j.appel.raison : ''));
  } catch (erreur) { mettre('dit', 'Connexion perdue.'); }
});
</script>"""


def dessiner_messages(messages: list[dict[str, Any]]) -> str:
    """Sur l'écran du soignant : ce que le robot du hall a transmis à l'étage."""
    if not messages:
        return ""
    lignes = "".join(f"<li>{_e(_heure_courte(m.get('quand')))} — {_e(m['texte'])}</li>" for m in messages)
    return f"<article><h2>Messages du hall ({len(messages)})</h2><ul>{lignes}</ul></article>"


def dessiner_appels(appels: list[dict[str, Any]]) -> str:
    """Sur l'écran de l'accueil : le robot du hall demande un humain."""
    lignes = "".join(f"<li>{_e(_heure_courte(a.get('quand')))} — {_e(a['ou'])} : {_e(a['raison'])} "
                     f"(langue : {_e(a.get('langue', '?'))})</li>" for a in appels)
    return f"<article><h2>Appels du hall ({len(appels)})</h2><p>Le robot du hall demande une personne.</p><ul>{lignes}</ul></article>"


def brancher_accueil(app: FastAPI, clinique: Clinique) -> None:
    @app.get("/clinique/hall", response_class=HTMLResponse)
    async def page_hall():
        entete = (f"<h1>Hall</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                  f"<span>Badge : <b>{_e(clinique.accueil.robot.libelle)}</b></span>")
        milieu = ("<p class='ou'><b>SIMULÉ</b> : la phrase est tapée au clavier, la réponse s'affiche. "
                  "Pas de voix, aucun robot ne bouge.</p>"
                  "<form id='hall'><label>La personne dit : <input id='phrase' size='34' maxlength='200' "
                  "placeholder=\"Buongiorno, sono Giulia B.\"></label> <button>Dire</button></form>"
                  "<div class='dit' id='dit' role='status'></div><p id='chemin'></p><p class='ou' id='suite'></p>")
        return _page("Clinique — Hall", entete, milieu, SCRIPT_HALL)

    @app.post("/api/clinique/hall/entendre", dependencies=[Depends(_du_meme_site)])
    async def api_entendre(p: Phrase):
        return clinique.accueil.entendre(p.texte, p.langue)


# ---------------------------------------------------------------------- la grande répétition
def _jouer():
    from fastapi.testclient import TestClient

    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique


SIMULE = "phrase tapée par le programme, pas dite ; pas de voix, aucun robot"


ARRIVEES = {  # la même arrivée, dans les quatre langues du cahier ; ce que le robot doit répondre au début
    "it": ("Buongiorno, sono Giulia B.", "italien", ("Buongiorno, Giulia.", "camera è la numero 12", "piano 2",
                                                     "comincia alle 10:00", "Non la accompagno")),
    "de": ("Guten Tag, ich bin Giulia B.", "allemand", ("Guten Tag, Giulia.", "12", "10:00")),
    "fr": ("Bonjour, je suis Giulia B.", "français", ("Bonjour, Giulia.", "12", "10:00")),
    "en": ("Hello, I am Giulia B.", "anglais", ("Hello, Giulia.", "12", "10:00")),
}


def etape_1():
    """Étape 1 : l'arrivée en italien reçoit une réponse en italien, avec la chambre et le programme.
    Dans un essai compté, la langue change (it, de, fr, en) : la réponse doit être dans la langue de l'arrivée."""
    from .repetition import Resultat, changement

    langue = changement("langue", "it")
    phrase, nom, attendus = ARRIVEES[langue]
    client, _ = _jouer()
    r = client.post("/api/clinique/hall/entendre", json={"texte": phrase}).json()
    manquent = [a for a in attendus if a not in r.get("dit", "")]
    chemin = [pas.get("lieu") for pas in r.get("chemin", [])]
    reussie = (r.get("cas") == "arrivée" and r.get("langue") == langue and not manquent and chemin[:1] == ["Hall"]
               and chemin[-1:] == ["Chambre 12"])
    return Resultat(reussie, "SIMULÉ", f"{SIMULE} ; arrivée tapée : « {phrase} » ; langue reconnue : {nom} ({r.get('langue')}) ; "
                    f"réponse : « {r.get('dit')} »" + (f" ; il manque : {manquent}" if manquent else ""))


def etape_2():
    """Étape 2 : dans le hall, le robot refuse de parler de santé."""
    from .repetition import Resultat

    client, clinique = _jouer()
    r = client.post("/api/clinique/hall/entendre", json={"texte": "Pourquoi Madame B. est-elle ici ?"}).json()
    fuites = [f for f in ("Giulia", "12", "hanche", "réadaptation") if f in str(r)]
    appels = clinique.carnet.lignes("appel d'un humain")
    reussie = (r.get("cas") == "santé" and not fuites and "Je transmets à l'équipe" in r.get("dit", "") and len(appels) == 1
               and not clinique.carnet.lignes("message pour l'étage"))
    return Resultat(reussie, "SIMULÉ", f"{SIMULE} ; question de santé refusée : « {r.get('dit')} » ; un humain est appelé ; "
                    f"règle écrite dans accueil_hall.yaml (pas dans le gardien de l'ossature)"
                    + (f" ; fuites : {fuites}" if fuites else ""))


def etape_3():
    """Étape 3 : l'étage est prévenu."""
    from .repetition import Resultat

    client, _ = _jouer()
    avant = "Messages du hall" in client.get("/clinique/soignant/contenu", params={"badge": "soignant-etage-2"}).text
    client.post("/api/clinique/hall/entendre", json={"texte": "Buongiorno, sono Giulia B."})
    page = client.get("/clinique/soignant/contenu", params={"badge": "soignant-etage-2"}).text
    reussie = not avant and "Messages du hall (1)" in page and "Madame Giulia B. arrive. Chambre 12." in page
    return Resultat(reussie, "SIMULÉ", f"{SIMULE} ; le message s'affiche sur l'écran du soignant de l'étage 2 "
                    f"(page demandée par le programme, pas sur une tablette)")
