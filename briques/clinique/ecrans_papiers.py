"""Les papiers à l'écran de l'accueil (cahier 5.4 et 5.8, tâche T09) : les propositions, un doigt pour valider, « à trier ».

    /clinique/accueil/papiers?badge=accueil     les papiers du jour, chacun avec sa proposition de rangement
    POST /api/clinique/papiers/valider          un doigt : la proposition validée va au carnet

Tout passe par la pièce papiers.py, donc par la porte de lecture. Rien n'entre au faux dossier.
Un refus dit pourquoi : 403 quand le badge n'a pas le droit, 400 quand le rangement n'est pas possible.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .ecrans import Clinique, _e, _heure_html, _page, script_de_mise_a_jour
from .ecrans_listes import Court, _du_meme_site, _essayer
from .papiers import PAS_SUR
from .porte import AccesRefuse, Badge


class Rangement(BaseModel):
    badge: Court
    papier: Court
    type: Annotated[str, Field(max_length=60)] | None = None


SCRIPT_PAPIERS = """<script>
const ici = new URLSearchParams(location.search);
function dire(texte) { document.getElementById('dit').textContent = texte; }
document.addEventListener('click', async e => {
  const b = e.target.closest('button[data-valider]');
  if (!b) return;
  try {
    const r = await fetch('/api/clinique/papiers/valider', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({badge: ici.get('badge'), papier: b.dataset.valider, type: b.dataset.type || null})});
    const j = await r.json();
    if (!r.ok) { dire('Refusé : ' + (j.detail || '')); return; }
    dire('Rangé : ' + j.type + ' → ' + j.endroit + ' (' + j.valide + ')');
    rafraichir();
  } catch (erreur) { dire('Connexion perdue : le rangement n\\'est pas enregistré.'); }
});
</script>"""


def dessiner_lien_papiers(pile: dict[str, Any], badge: str) -> str:
    """Sur l'écran de l'accueil : le bouton qui mène aux papiers."""
    return (f"<p><a class='bouton' href=\"/clinique/accueil/papiers?badge={_e(badge)}\">Papiers à valider "
            f"({len(pile['a_valider'])})</a> · à trier : {len(pile['a_trier'])} · validés : {len(pile['valides'])}</p>")


def _papier(papier: dict[str, Any], types: list[str]) -> str:
    p = papier["proposition"]
    rien = "non trouvé dans le texte"
    lignes = [f"<li>Type : <b>{_e(p['type'] or 'non reconnu')}</b></li>",
              f"<li>Patient : <b>{_e(p['nom_du_patient'] or 'aucun patient ne correspond')}</b></li>",
              f"<li>Endroit du dossier : <b>{_e(p['endroit'] or '—')}</b></li>",
              f"<li>Date : {_e(p['date'] or rien)}</li>", f"<li>Auteur : {_e(p['auteur'] or rien)}</li>",
              f"<li>Confiance : {_e(p['confiance'])}"
              + (f" — « {_e(PAS_SUR)} » ({_e(' ; '.join(p['raisons'] or []))})" if p["confiance"] != "haute" else "") + "</li>"]
    if papier["etat"] == "validé":
        boutons = f"<p class='fait'>{_e(papier['valide'])}" + (" — type choisi par un humain" if papier["choisi_par_un_humain"] else "") + "</p>"
    elif papier["etat"] == "à trier":
        boutons = "<p class='rien'>Ce papier n'est pas rangé : il attend qu'un humain le trie.</p>"
    elif p["confiance"] == "haute":
        boutons = f"<button data-valider=\"{_e(papier['id'])}\">Valider ce rangement</button>"
    else:  # le prototype n'est pas sûr : l'humain choisit le type
        boutons = "<p>Choisissez le type :</p>" + "".join(
            f"<button data-valider=\"{_e(papier['id'])}\" data-type=\"{_e(t)}\">{_e(t)}</button>" for t in types)
    return (f"<article><h3>{_e(p['type'] or 'Papier à trier')}</h3>"
            f"<p class='ou'>Papier {_e(papier['id'])} · langue : {_e(papier['langue'] or '?')} · écriture : {_e(papier['ecriture'])}</p>"
            f"<p class='ou'>Le texte du papier n'est pas affiché ici : l'accueil ne lit pas un document qui peut être médical. "
            f"Vous avez le papier en main.</p>"
            f"<h4>Proposition de rangement</h4><ul>{''.join(lignes)}</ul>{boutons}</article>")


def _lien_pre_admission(pile: dict[str, Any]) -> str:
    from .ecrans_pre_admission import lien_dans_a_trier  # avenant 4, L04 : « Préparer une pré-admission »

    return lien_dans_a_trier(pile, "accueil")


def dessiner_papiers(pile: dict[str, Any]) -> str:
    def groupe(titre: str, papiers: list[dict[str, Any]], vide: str) -> str:
        return f"<h2>{_e(titre)} ({len(papiers)})</h2>" + ("".join(_papier(p, pile["types"]) for p in papiers)
                                                          or f"<p class='rien'>{_e(vide)}</p>")
    return (f"<p class='ou'>Proposition faite par : {_e(pile['version'])}. Rien n'entre au faux dossier : "
            f"un rangement validé est une ligne du carnet.</p>"
            + groupe("À valider", pile["a_valider"], "Rien à valider.")
            + groupe("À trier", pile["a_trier"], "Rien à trier.") + _lien_pre_admission(pile)
            + groupe("Validés", pile["valides"], "Aucun pour l'instant."))


def brancher_papiers(app: FastAPI, clinique: Clinique, badge_de) -> None:
    def contenu(badge: Badge) -> str:
        try:
            return dessiner_papiers(clinique.papiers.pile(badge))
        except AccesRefuse as refus:
            return f"<p class='refus'>Accès refusé : {_e(refus)}. Ce refus est noté au journal des accès.</p>"

    @app.get("/clinique/accueil/papiers", response_class=HTMLResponse)
    async def page_papiers(badge: str | None = None):
        b = badge_de("accueil", badge)
        entete = (f"<h1>Papiers</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                  f"<span>Badge : <b>{_e(b.libelle)}</b></span>"
                  f"<a class='bouton' href=\"/clinique/accueil?badge={_e(b.id)}\">Retour</a>"
                  f"<div class='dit' id='dit' role='status'></div>")
        return _page("Clinique — Papiers", entete, contenu(b),
                     script_de_mise_a_jour(f"/clinique/accueil/papiers/contenu?badge={b.id}") + SCRIPT_PAPIERS)

    @app.get("/clinique/accueil/papiers/contenu", response_class=HTMLResponse)
    async def page_papiers_contenu(badge: str | None = None):
        return contenu(badge_de("accueil", badge))

    @app.get("/api/clinique/papiers")
    async def api_papiers(badge: str):
        return _essayer(lambda: clinique.papiers.pile(badge_de("accueil", badge)))

    @app.post("/api/clinique/papiers/valider", dependencies=[Depends(_du_meme_site)])
    async def api_valider(r: Rangement):
        badge = badge_de("accueil", r.badge)
        rangement = _essayer(lambda: clinique.papiers.valider(badge, r.papier, r.type))
        bus = getattr(clinique.horloge, "bus", None)
        if bus is not None:  # qui a donné l'accord (avenant 2, K03) : le badge et l'heure, dans la boîte noire ; pas de nom
            etat = clinique.horloge.etat()
            await bus.emettre("note", "clinique", quoi="accord_d_un_humain", pour="papier rangé", badge=badge.id,
                              heure=f"jour {etat['jour']}, {etat['heure']}", papier=r.papier)
        return rangement


# ---------------------------------------------------------------------- la grande répétition
def _jouer():
    """Les papiers du jour 1, par la vraie page et le vrai bouton, demandés par le programme."""
    from fastapi.testclient import TestClient

    from . import dossier as faux_dossier
    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    clinique = brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                               carnet=Carnet(horloge=horloge))
    return TestClient(app), clinique, faux_dossier


def etape_4():
    """Étape 4 : les trois papiers sont proposés au bon endroit, puis validés."""
    from .repetition import Resultat

    client, clinique, faux_dossier = _jouer()
    avant = faux_dossier.empreinte()
    attendus = {d["id"]: d["genre"] for d in faux_dossier.charger().patient("p01")["DocumentReference"]}
    pile = client.get("/api/clinique/papiers", params={"badge": "accueil"}).json()
    proposes = {p["id"]: p["proposition"] for p in pile.get("a_valider", [])}
    endroits_attendus = {"lettre du médecin traitant": "Courrier médical", "liste de médicaments": "Médicaments",
                         "carte d'assurance": "Assurance et administratif"}  # écrit ici, à part des règles
    bons = [i for i, genre in attendus.items() if i in proposes and proposes[i]["type"] == genre
            and proposes[i]["patient"] == "p01" and proposes[i]["endroit"] == endroits_attendus.get(genre)]
    reponses = [client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": i}) for i in attendus]
    valides = [l for l in clinique.carnet.lignes("rangement de papier")
               if l["donnees"]["etat"] == "validé" and l["valide_par_un_humain"]
               and str(l["donnees"].get("valide", "")).startswith("validée par Accueil, à Jour 1")]
    reussie = (len(attendus) == 3 and len(bons) == 3 and all(r.status_code == 200 for r in reponses) and len(valides) == 3
               and faux_dossier.empreinte() == avant)
    endroits = " ; ".join(f"{proposes[i]['type']} → {proposes[i]['endroit']}" for i in bons)
    return Resultat(reussie, "SIMULÉ",
                    f"à partir du texte de référence, pas d'une image ; par des règles, sans modèle ; validés par le "
                    f"programme avec le badge de l'accueil, pas par une personne ; {len(bons)} papiers sur 3 au bon endroit "
                    f"({endroits}) ; {len(valides)} validations au carnet ; faux dossier inchangé")


def etape_5():
    """Étape 5 : la feuille sans nom n'est pas rangée."""
    from .repetition import Resultat

    client, clinique, _ = _jouer()
    pile = client.get("/api/clinique/papiers", params={"badge": "accueil"}).json()
    a_trier = [p["id"] for p in pile.get("a_trier", [])]
    refus = client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": "f-01"})
    force = client.post("/api/clinique/papiers/valider", json={"badge": "accueil", "papier": "f-01", "type": "carte d'assurance"})
    apres = [p["id"] for p in client.get("/api/clinique/papiers", params={"badge": "accueil"}).json().get("a_trier", [])]
    ranges = [l for l in clinique.carnet.lignes("rangement de papier")
              if l["donnees"]["papier"] == "f-01" and l["donnees"]["etat"] == "validé"]
    reussie = a_trier == ["f-01"] and refus.status_code == 400 and force.status_code == 400 and apres == ["f-01"] and not ranges
    return Resultat(reussie, "SIMULÉ",
                    f"à partir du texte de référence, pas d'une image ; la feuille reste dans « à trier » ({apres}) ; "
                    f"deux essais de la ranger refusés ({refus.status_code}, {force.status_code})")
