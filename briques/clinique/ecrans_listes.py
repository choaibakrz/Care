"""Les listes de soin à l'écran (cahier 5.4 et 5.5) : ouvrir une liste, cocher au doigt, « je sors », la fin de
poste, le point de prise de poste, et la page de la direction. Ajouté aux écrans par brancher_ecrans (ecrans.py).

- GET  /clinique/soignant/liste?badge=…&patient=…&liste=…   une liste, avec les habitudes de la personne
- GET  /clinique/soignant/fin-de-poste?badge=…               tout ce qui reste ; trois choix par point
- GET  /clinique/direction                                   des comptes par étage, aucun nom
- POST /api/clinique/liste/cocher    {badge, patient, liste, numero}
- POST /api/clinique/liste/choisir   {badge, patient, liste, numero, choix, raison}
- POST /api/clinique/je_sors         {badge, patient}
- GET  /api/clinique/liste, /api/clinique/fin_de_poste, /api/clinique/prise_de_poste, /api/clinique/comptes

Règles :
- Tout est lu par la porte ; tout ce qui s'écrit va dans le carnet, jamais dans le faux dossier.
- Un refus dit pourquoi : 403 quand le badge n'a pas le droit, 400 quand le geste n'est pas possible.
- Une page venue d'un autre site ne peut pas cocher à notre place. Mais sur le même Wi-Fi, n'importe qui peut prendre
  un badge et cocher : le badge n'est pas un contrôle d'identité (NON_TESTE.md).
- EXEMPLES INVENTÉS, NON MÉDICAUX. Pas d'alarme, pas de reproche.
"""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .ecrans import Clinique, _e, _heure_html, _page, script_de_mise_a_jour
from .listes import A_FAIRE, CHOIX, FAIT, REPORTE, ChoixRefuse
from .paroles import mention_hypothese
from .porte import AccesRefuse, Badge
from .taches import mots_partages

Court = Annotated[str, Field(max_length=60)]
TITRE_AVANT = "Ce que le poste d'avant n'a pas fini"


class Point(BaseModel):
    badge: Court
    patient: Court
    liste: Court
    numero: int
    # l'heure de la tablette, si la coche a été faite sans lien puis renvoyée (« 2026-11-14T10:02:00 »)
    hors_ligne_a: Annotated[str, Field(max_length=40, pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?[0-9.:+Zz-]*$")] | None = None


class Voix(BaseModel):
    badge: Court
    patient: Court
    liste: Court
    phrase: Annotated[str, Field(max_length=200)]


class Choix(Point):
    choix: Court
    raison: Annotated[str, Field(max_length=200)] | None = None


class Confirmation(BaseModel):
    badge: Court
    tache: Court


class Demande(BaseModel):
    badge: Court
    patient: Court
    texte: Annotated[str, Field(max_length=200)]
    choix: Court | None = None
    liste: Court | None = None
    numero: int | None = None


class Sortie(BaseModel):
    badge: Court
    patient: Court


def _du_meme_site(request: Request) -> None:
    origine = request.headers.get("origin")
    if origine and urlparse(origine).netloc != request.headers.get("host"):
        raise HTTPException(403, "Requête venue d'un autre site : refusée.")


def _essayer(geste):
    """Fait le geste ; change un refus en réponse claire."""
    try:
        return geste()
    except AccesRefuse as refus:
        raise HTTPException(403, str(refus))
    except ChoixRefuse as refus:
        raise HTTPException(400, str(refus))


def _heure_courte(quand: dict[str, Any] | None) -> str:
    if not quand or not quand.get("heure"):
        return ""
    return f"jour {quand['jour']}, {int(quand['heure'][:2])} h {quand['heure'][3:]}"


# ---------------------------------------------------------------------- dessiner
def dessiner_prise_de_poste(point: dict[str, Any], badge: str) -> str:
    change = "".join(f"<li>{_e(c['nom'])}, chambre {_e(c['chambre'])} : {_e(c['quoi'])}</li>" for c in point["ce_qui_a_change"])
    avant = "".join(
        f"<li>{_e(p['nom_du_patient'])}, chambre {_e(p['chambre'])} — {_e(p['nom'])} : {_e(p['etat'])}"
        f"{' (' + _e(p['raison']) + ')' if p.get('raison') else ''} "
        f"<a class='bouton' href=\"/clinique/soignant/liste?badge={_e(badge)}&amp;patient={_e(p['patient'])}&amp;liste={_e(p['liste'])}\">Ouvrir</a></li>"
        for p in point["du_poste_d_avant"])
    rien = "<p class='rien'>Rien.</p>"
    return ("<article><h2>Point de prise de poste</h2>"
            f"<p>Mes patients : <b>{point['mes_patients']}</b> · Points qui restent : <b>{point['ce_qui_reste']}</b> "
            f"<a class='bouton' href=\"/clinique/soignant/fin-de-poste?badge={_e(badge)}\">Fin de poste</a></p>"
            f"<h4>Ce qui a changé</h4>{'<ul>' + change + '</ul>' if change else rien}"
            f"<h4>{_e(TITRE_AVANT)}</h4>{'<ul>' + avant + '</ul>' if avant else rien}</article>")


def dessiner_liste(personne: dict[str, Any], vue: dict[str, Any], role: str) -> str:
    """Une liste, avec les habitudes en haut. Un bouton « Fait » par point qui n'est pas fait."""
    habitudes = "".join(f"<li>{_e(h)}</li>" for h in personne.get("habitudes") or [])
    points = []
    for p in vue["points"]:
        if p["etat"] == FAIT:
            points.append(f"<li class='fait'>✓ {_e(p['texte'])} <small>({_e(_heure_courte(p.get('quand')))})</small></li>")
            continue
        etat = "" if p["etat"] == A_FAIRE else f" — <b>{_e(p['etat'])}{' : ' + _e(p['raison']) if p.get('raison') else ''}</b>"
        bouton = f" <button data-cocher=\"{p['numero']}\">Fait</button>" if role in p["pour"] else f" <small>(pour : {_e(p['pour'])})</small>"
        points.append(f"<li>{_e(p['texte'])}{etat}{bouton}</li>")
    return (f"<article><h3>{_e(personne['nom'])}</h3><p class='ou'>Chambre {_e(personne['chambre'])}</p>"
            f"<h4>Habitudes</h4>{'<ul>' + habitudes + '</ul>' if habitudes else '<p class=rien>aucune</p>'}</article>"
            f"<h2>{_e(vue['titre'])}</h2><p class='rien'>{_e(vue['marque'])}</p>"
            f"<p class='rien'>{_e(mention_hypothese())}</p><ul class='points'>{''.join(points)}</ul>")


def dessiner_taches(taches: list[dict[str, Any]], robot_branche: bool = False, badge: str = "") -> str:
    """Les demandes en cours, sur l'écran du soignant. Rien si aucune demande."""
    if not taches:
        return ""
    lignes = "".join(
        f"<li><b>{_e(t['quoi'])}</b> → {_e(t['ou'])} ({_e(t['nom_du_patient'])}) — "
        f"pour un {'robot' if t['sorte'] == 'robot' else 'humain'}"
        f"{' (' + _e(t['pourquoi_un_humain']) + ')' if t.get('pourquoi_un_humain') else ''} — <b>{_e(t['etat'])}</b>"
        f"{' [' + _e(t['etiquette']) + ']' if t.get('etiquette') else ''}"
        f"{' — constaté : ' + _e(t['constate']) if t.get('constate') else ''}"
        + (f" <a href=\"/clinique/pourquoi?badge={_e(badge)}&amp;tache={_e(t['id'])}\">Pourquoi ?</a>" if t.get("regardes") and badge else "")
        + f"{' — ' + _e(t['pourquoi']) if t.get('pourquoi') else ''}"
        + (f" — <b>le robot attend : {_e(t['attend'])}</b> <form method='post' style='display:inline' "
           f"action=\"/clinique/soignant/tache/confirmer?badge={_e(badge)}&amp;tache={_e(t['id'])}\">"
           f"<button>C'est fait</button></form>" if t.get("attend") and badge else "")
        + (f" <form method='post' style='display:inline' "
           f"action=\"/clinique/soignant/tache/constater?badge={_e(badge)}&amp;tache={_e(t['id'])}\">"
           f"<button>Je l'ai vu</button></form>" if t.get("constate") == "pas encore" and badge else "")
        + (" — <b>phrase entendue, à confirmer</b>" + (
            f" <form method='post' style='display:inline' "
            f"action=\"/clinique/soignant/tache/c-est-bien-ca?badge={_e(badge)}&amp;tache={_e(t['id'])}\">"
            f"<button>C'est bien ça</button></form>" if badge and t.get("qui_demande") == badge else "")
           if t.get("phrase_confirmee") == "pas encore" else "") + "</li>"
        for t in taches)
    note = "" if robot_branche else "<p class='rien'>Aucun robot n'est branché : les demandes « pour un robot » attendent.</p>"
    return f"<article><h2>Demandes ({len(taches)})</h2><ul>{lignes}</ul>{note}</article>"


def dessiner_sorties_accueil(sorties: list[dict[str, Any]], badge: str = "") -> str:
    """H17 : sur l'écran de l'accueil, ses trois points de la liste de sortie (rien d'autre de la liste)."""
    if not sorties:
        return ""
    blocs = []
    for s in sorties:
        points = "".join(
            f"<li>{_e(pt['nom'])} <small>({_e(pt['texte'])})</small> — <b>{_e(pt['etat'])}</b>"
            + (f" <form method='post' style='display:inline' action=\"/clinique/accueil/sortie/cocher?badge={_e(badge)}"
               f"&amp;patient={_e(s['id'])}&amp;numero={int(pt['numero'])}\"><button>Fait</button></form>"
               if pt["etat"] != "fait" and badge else "") + "</li>"
            for pt in s["points"])
        blocs.append(f"<li><b>{_e(s['nom'])}</b> — chambre {_e(s['chambre'])} — sortie : jour {_e(s.get('sortie_jour'))}"
                     f"<ul>{points}</ul></li>")
    return (f"<article><h2>{_e(sorties[0]['titre'])} : les points de l'accueil</h2><ul>{''.join(blocs)}</ul>"
            "<p class='rien'>Seulement les points de l'accueil ; les autres points sont pour le médecin et le soignant. "
            "Données inventées.</p></article>")


def dessiner_pourquoi(tache: dict[str, Any], decisions: list[dict[str, Any]]) -> str:
    """Les robots que le répartiteur a regardés, son choix, le feu du gardien, et ce que le robot a annoncé. Aucun nom de patient."""
    rangs = "".join(
        f"<tr><td><b>{_e(r['nom'])}</b></td><td>{_e(r['carte'])}</td><td>{_e(r['etiquette'])}</td><td>{'oui' if r['libre'] else 'non'}</td>"
        f"<td>{_e('—' if r['metres'] is None else format(r['metres'], '.0f') + ' m')}</td><td>{_e(format(r['batterie'], '.0f'))} %</td>"
        f"<td>{'oui' if r['carte_permet'] else 'non'}</td><td><b>{'choisi' if r['id'] == tache.get('robot') else ('convient' if r['convient'] else 'écarté')}</b>"
        f"{' : ' + _e(r['raison']) if r['raison'] else ''}</td></tr>" for r in tache.get("regardes") or [])
    oui = sum(1 for d in decisions if d.get("verdict") == "oui")
    non = sum(1 for d in decisions if d.get("verdict") == "non")
    humain = sum(1 for d in decisions if d.get("verdict") == "humain")
    feu = "vert" if decisions and not non and not humain else ("rouge" if non else ("orange" if humain else "pas encore de geste"))
    return (f"<p class='ou'>Tâche {_e(tache['id'])} : {_e(tache['quoi'])} → {_e(tache['ou'])} — <b>{_e(tache['etat'])}</b>. Données inventées.</p>"
            f"<article><h2>Pourquoi ce robot</h2><p class='dit'>{_e(tache.get('pourquoi_ce_robot') or tache.get('pourquoi_un_humain') or '—')}</p>"
            "<table><tr><th>Robot</th><th>Carte</th><th>Étiquette</th><th>Libre</th><th>Distance</th><th>Batterie</th>"
            f"<th>Sa carte permet</th><th>Résultat</th></tr>{rangs}</table></article>"
            f"<article><h2>Le feu du gardien</h2><p>Feu <b>{feu}</b> : {oui} oui, {non} non, {humain} « demander à un humain », "
            "pour les gestes de cette tâche. Aucun geste ne part sans un « oui ».</p></article>"
            f"<article><h2>Ce que le robot a annoncé</h2><p class='dit'>{_e(tache.get('annonce') or 'rien pour l’instant')}</p>"
            "<p class='ou'>Le robot annonce ce qu'il va faire avant de partir : un texte à l'écran, écrit dans la boîte noire.</p></article>")


def dessiner_reserve(reserve: list[dict[str, Any]]) -> str:
    """« Il manque un objet » : un bouton par objet de la réserve, un bouton par mot flou, et une case pour autre chose."""
    boutons = "".join(f"<button data-objet=\"{_e(o['nom'])}\">{_e(o['nom'])}</button>" for o in reserve)
    flous = "".join(f"<button data-objet=\"{_e(mot)}\">{_e(mot)}…</button>" for mot in mots_partages(reserve))
    return (f"<article><h4>Il manque un objet</h4><p>{flous}{boutons}</p>"
            "<p><input id='autre-objet' placeholder='autre chose' maxlength='200'> <button id='demander-autre'>Demander</button></p></article>")


def dessiner_fin_de_poste(restants: list[dict[str, Any]]) -> str:
    if not restants:
        return "<h2>Fin de poste</h2><p class='rien'>Il ne reste rien.</p>"
    lignes = "".join(
        f"<li><b>{_e(r['nom_du_patient'])}</b>, chambre {_e(r['chambre'])} — {_e(r['titre'])}<br>{_e(r['texte'])}<br>"
        + "".join(f"<button data-choix=\"{_e(c)}\" data-patient=\"{_e(r['patient'])}\" data-liste=\"{_e(r['liste'])}\" "
                  f"data-numero=\"{r['numero']}\">{_e(c[0].upper() + c[1:])}</button>" for c in CHOIX) + "</li>"
        for r in restants)
    return (f"<h2>Fin de poste : {len(restants)} point{'s' if len(restants) > 1 else ''} qui reste{'nt' if len(restants) > 1 else ''}</h2>"
            f"<p class='rien'>Pour chaque point : le faire, le reporter avec une raison, ou le passer à la relève.</p>"
            f"<ul class='points'>{lignes}</ul>")


def dessiner_direction(patients: dict[str, Any], listes: dict[str, Any]) -> str:
    par_etage = {e["etage"]: e for e in listes["etages"]}
    rangs = ""
    for e in patients["etages"]:
        l = par_etage.get(e["etage"], {})
        etage = "non précisé" if e["etage"] is None else e["etage"]
        rangs += (f"<tr><td>{_e(etage)}</td><td>{e['patients']}</td><td>{e['arrivees_du_jour']}</td><td>{e['sorties_demain']}</td>"
                  f"<td>{l.get('faits', 0)}</td><td>{l.get('reportes', 0)}</td><td>{l.get('passes_a_la_releve', 0)}</td></tr>")
    return ("<h2>Des comptes par étage</h2><p class='rien'>Aucun nom de patient, aucun nom de soignant. Jamais par personne.</p>"
            "<table><tr><th>Étage</th><th>Patients</th><th>Arrivées du jour</th><th>Sorties demain</th>"
            f"<th>Points faits</th><th>Points reportés</th><th>Points passés à la relève</th></tr>{rangs}</table>")


SCRIPT_BOUTONS = """<script>
const ici = new URLSearchParams(location.search);
function dire(texte) { document.getElementById('dit').textContent = texte; }
async function envoyer(chemin, corps) {
  try {
    const r = await fetch(chemin, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corps)});
    const j = await r.json();
    if (!r.ok) { dire('Refusé : ' + (j.detail || '')); return null; }
    rafraichir();
    return j;
  } catch (erreur) { dire('Connexion perdue : le geste n\\'est pas enregistré.'); return null; }
}
const formulaireVoix = document.getElementById('voix');
if (formulaireVoix) formulaireVoix.addEventListener('submit', async e => {  // cocher à la voix : ici, la phrase est tapée
  e.preventDefault();
  const champ = document.getElementById('phrase-voix');
  if (!champ.value) return;
  const j = await envoyer('/api/clinique/liste/voix', {badge: ici.get('badge'), patient: ici.get('patient'),
                                                       liste: ici.get('liste'), phrase: champ.value});
  if (!j) return;
  dire(j.dit);
  champ.value = '';
  if (j.tache && j.tache.phrase_confirmee === 'pas encore') {  // H16 : la phrase entendue, confirmée d'un doigt
    const ok = document.createElement('button');
    ok.textContent = "C'est bien ça"; ok.dataset.confirmer = j.tache.id;
    document.getElementById('dit').append(' ', ok);
  }
  for (const choix of (j.choix || [])) {  // deux points possibles : un bouton par point, l'humain choisit au doigt
    if (!choix.nom) continue;  // une question du robot (« lequel ? ») : on y répond dans le champ, ou par les boutons d'objet
    const c = document.createElement('button');
    c.textContent = choix.nom; c.dataset.cocher = choix.numero;
    document.getElementById('dit').append(' ', c);
  }
});
document.addEventListener('click', async e => {
  const b = e.target.closest('button');
  if (!b || b.closest('#voix')) return;
  const badge = ici.get('badge');
  if (b.dataset.confirmer) {
    const j = await envoyer('/api/clinique/demande/c-est-bien-ca', {badge, tache: b.dataset.confirmer});
    if (j) dire('Confirmé : ' + j.quoi + '.');
  } else if (b.dataset.cocher) {
    await envoyer('/api/clinique/liste/cocher', {badge, patient: ici.get('patient'), liste: ici.get('liste'), numero: Number(b.dataset.cocher)});
  } else if (b.id === 'je-sors') {
    const j = await envoyer('/api/clinique/je_sors', {badge, patient: ici.get('patient')});
    if (j) dire(j.phrase || 'Aucune liste commencée.');
  } else if (b.dataset.objet || b.id === 'demander-autre') {
    const texte = b.dataset.objet ? 'il manque : ' + b.dataset.objet : document.getElementById('autre-objet').value;
    if (!texte) return;
    const j = await envoyer('/api/clinique/demande', {badge, patient: ici.get('patient'), texte, choix: b.dataset.precis || null});
    if (!j) return;
    dire(j.phrase);
    for (const choix of (j.choix || [])) {  // demande floue : un bouton par réponse possible
      const c = document.createElement('button');
      c.textContent = choix; c.dataset.objet = b.dataset.objet || texte; c.dataset.precis = choix;
      document.getElementById('dit').append(' ', c);
    }
  } else if (b.dataset.choix) {
    const corps = {badge, patient: b.dataset.patient, liste: b.dataset.liste, numero: Number(b.dataset.numero), choix: b.dataset.choix};
    if (b.dataset.choix === 'le reporter') {
      corps.raison = prompt('Pourquoi reporter ce point ?');
      if (!corps.raison) return;
    }
    await envoyer('/api/clinique/liste/choisir', corps);
  }
});
</script>"""


# La file des coches faites sans lien. Du JavaScript sans rien autour, pour pouvoir l'essayer seul (avec Node).
# `stockage` : le rangement du navigateur (il garde la file si la page est rechargée). Pas de doublon. On renvoie dans
# l'ordre ; au premier envoi qui ne part pas, on s'arrête et on garde le reste : rien n'est perdu.
FILE_HORS_LIGNE_JS = """
function fileHorsLigne(stockage, cle) {
  const nom = 'clinique-hors-ligne-' + cle;
  const lire = () => { try { return JSON.parse(stockage.getItem(nom) || '[]'); } catch (e) { return []; } };
  const ecrire = f => { try { stockage.setItem(nom, JSON.stringify(f)); } catch (e) {} };
  let file = lire();
  return {
    taille: () => file.length,
    contient: (patient, liste, numero) => file.some(c => c.patient === patient && c.liste === liste && c.numero === numero),
    ajouter(coche, heure) {
      if (this.contient(coche.patient, coche.liste, coche.numero)) return;
      file.push({patient: coche.patient, liste: coche.liste, numero: coche.numero, hors_ligne_a: heure});
      ecrire(file);
    },
    async vider(envoyer) {
      while (file.length) {
        let parti = false;
        try { parti = await envoyer(file[0]); } catch (e) { parti = false; }
        if (!parti) break;
        file.shift();
        ecrire(file);
      }
      return file.length;
    },
  };
}
"""

# La page de liste, côté tablette : chaque échange porte « X-Tablette » ; sans lien, on coche quand même.
SCRIPT_TABLETTE = "<script>" + FILE_HORS_LIGNE_JS + """
const iciTablette = new URLSearchParams(location.search);
const badgeTablette = iciTablette.get('badge');
let rangement; try { rangement = window.localStorage; } catch (e) { rangement = {getItem: () => null, setItem: () => {}}; }
const file = fileHorsLigne(rangement, badgeTablette);
const fetchDuNavigateur = window.fetch.bind(window);
function afficherHorsLigne(coupe) {
  const bandeau = document.getElementById('hors-ligne');
  bandeau.style.display = (coupe || file.taille()) ? 'block' : 'none';
  document.getElementById('hors-ligne-compte').textContent = file.taille() ? ' ' + file.taille() + ' coche(s) à envoyer.' : '';
}
window.fetch = async (adresse, options = {}) => {  // tous les échanges de cette page passent ici
  try {
    const r = await fetchDuNavigateur(adresse, {...options, headers: {...(options.headers || {}), 'X-Tablette': 'liste'}});
    afficherHorsLigne(r.status === 503);
    return r;
  } catch (erreur) { afficherHorsLigne(true); throw erreur; }
};
function corpsCoche(coche) {
  return {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({badge: badgeTablette, ...coche})};
}
document.addEventListener('click', async e => {  // avant les autres boutons : une coche ne se perd jamais
  const b = e.target.closest('button[data-cocher]');
  if (!b) return;
  e.stopPropagation();
  const coche = {patient: iciTablette.get('patient'), liste: iciTablette.get('liste'), numero: Number(b.dataset.cocher)};
  if (!file.taille()) {
    try {
      const r = await fetch('/api/clinique/liste/cocher', corpsCoche(coche));
      if (r.ok) { rafraichir(); return; }
      if (r.status !== 503) { const j = await r.json(); dire('Refusé : ' + (j.detail || '')); return; }
    } catch (erreur) { /* pas de lien : la coche va dans la file */ }
  }
  file.ajouter(coche, new Date().toISOString().slice(0, 19));
  const ligne = b.closest('li');
  b.remove();
  ligne.className = 'fait';
  ligne.append(' — coché hors ligne, sera envoyé au retour du lien');
  afficherHorsLigne(true);
}, true);
async function renvoyer() {
  if (!file.taille()) return;
  const reste = await file.vider(async coche => {
    const r = await fetch('/api/clinique/liste/cocher', corpsCoche(coche));
    if (r.status === 503) return false;
    if (!r.ok) dire('Une coche faite hors ligne a été refusée au retour du lien (point ' + coche.numero + ').');
    return true;
  });
  afficherHorsLigne(reste > 0);
  if (!reste) rafraichir();
}
setInterval(renvoyer, 1500);
afficherHorsLigne(false);
</script>"""

BANDEAU_HORS_LIGNE = ("<div id='hors-ligne' role='status' style='display:none;background:#b00020;color:#fff;padding:.5rem .9rem;"
                      "font-weight:700;flex-basis:100%'>HORS LIGNE : cette tablette n'a plus de lien avec le cerveau. Elle garde "
                      "la liste. Vous pouvez continuer à cocher : les coches partiront au retour du lien. « Je sors » et les "
                      "demandes au robot attendent le lien.<span id='hors-ligne-compte'></span></div>")


# ---------------------------------------------------------------------- brancher
def brancher_listes(app: FastAPI, clinique: Clinique, badge_de) -> None:
    listes, porte = clinique.listes, clinique.porte
    du_meme_site = [Depends(_du_meme_site)]

    def badge_connu(identifiant: str) -> Badge:
        if identifiant not in clinique.badges:
            raise HTTPException(404, "Ce badge n'existe pas")
        return clinique.badges[identifiant]

    def entete(titre: str, badge: Badge, retour: str) -> str:
        return (f"<h1>{_e(titre)}</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                f"<span>Badge : <b>{_e(badge.libelle)}</b></span><a class='bouton' href=\"{retour}\">Retour</a>")

    def page_avec_boutons(titre: str, badge: Badge, milieu: str, chemin_contenu: str, sous_le_titre: str = "",
                          tablette: bool = False) -> str:
        retour = f"/clinique/soignant?badge={_e(badge.id)}"
        scripts = script_de_mise_a_jour(chemin_contenu) + SCRIPT_BOUTONS
        if tablette:  # la page de liste : elle sait travailler sans lien (panne « lien_tablette »)
            sous_le_titre, scripts = sous_le_titre + BANDEAU_HORS_LIGNE, scripts + SCRIPT_TABLETTE
        return _page(f"Clinique — {titre}", entete(titre, badge, retour) + sous_le_titre, milieu, scripts)

    def contenu_liste(badge: Badge, patient: str, liste: str) -> str:
        def lire():
            return (dessiner_liste(porte.patient(badge, patient), listes.liste(badge, patient, liste), badge.role)
                    + dessiner_reserve(porte.reserve(badge)))
        try:
            return lire()
        except (AccesRefuse, ChoixRefuse) as refus:
            return f"<p class='refus'>Accès refusé : {_e(refus)}.</p>"

    def contenu_fin_de_poste(badge: Badge) -> str:
        try:
            return dessiner_fin_de_poste(listes.fin_de_poste(badge))
        except AccesRefuse as refus:
            return f"<p class='refus'>Accès refusé : {_e(refus)}.</p>"

    # ------------------------------------------------------------------ les pages
    @app.get("/clinique/soignant/liste", response_class=HTMLResponse)
    async def page_liste(patient: str, liste: str, badge: str | None = None):
        b = badge_de("soignant", badge)
        suite = f"?badge={b.id}&patient={patient}&liste={liste}"
        if not all(morceau.replace("_", "").replace("-", "").isalnum() for morceau in (patient, liste)):
            raise HTTPException(404, "Cette liste n'existe pas")
        je_sors = ("<button id='je-sors'>Je sors</button>"
                   "<form id='voix' style='flex-basis:100%'><label>La tablette a entendu : <input id='phrase-voix' size='22' "
                   "maxlength='200' placeholder=\"sonnette, fait\"></label> <button>Dire</button> "
                   "<small><b>SIMULÉ</b> : la phrase est tapée, pas de micro.</small></form>"
                   "<div class='dit' id='dit' role='status'></div>")
        return page_avec_boutons("Liste de soin", b, contenu_liste(b, patient, liste),
                                 "/clinique/soignant/liste/contenu" + suite, je_sors, tablette=True)

    @app.get("/clinique/soignant/liste/contenu", response_class=HTMLResponse)
    async def page_liste_contenu(patient: str, liste: str, badge: str | None = None):
        return contenu_liste(badge_de("soignant", badge), patient, liste)

    @app.get("/clinique/soignant/fin-de-poste", response_class=HTMLResponse)
    async def page_fin_de_poste(badge: str | None = None):
        b = badge_de("soignant", badge)
        return page_avec_boutons("Fin de poste", b, contenu_fin_de_poste(b),
                                 f"/clinique/soignant/fin-de-poste/contenu?badge={b.id}",
                                 "<div class='dit' id='dit' role='status'></div>")

    @app.get("/clinique/soignant/fin-de-poste/contenu", response_class=HTMLResponse)
    async def page_fin_de_poste_contenu(badge: str | None = None):
        return contenu_fin_de_poste(badge_de("soignant", badge))

    def direction() -> Badge:
        badges = [b for b in clinique.badges.values() if b.role == "direction"]
        if not badges:
            raise HTTPException(404, "Aucun badge « direction » dans badges.yaml")
        return badges[0]

    def contenu_direction() -> str:
        b = direction()
        return dessiner_direction(porte.comptes(b), listes.comptes(b))

    @app.get("/clinique/direction", response_class=HTMLResponse)
    async def page_direction():
        tete = (f"<h1>Direction</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
                f"<span>Badge : <b>{_e(direction().libelle)}</b></span>")
        return _page("Clinique — Direction", tete, contenu_direction(), script_de_mise_a_jour("/clinique/direction/contenu"))

    @app.get("/clinique/direction/contenu", response_class=HTMLResponse)
    async def page_direction_contenu():
        return contenu_direction()

    # ------------------------------------------------------------------ les données
    @app.get("/api/clinique/liste")
    async def api_liste(badge: str, patient: str, liste: str):
        return _essayer(lambda: listes.liste(badge_connu(badge), patient, liste))

    @app.get("/api/clinique/fin_de_poste")
    async def api_fin_de_poste(badge: str):
        return {"marque": "données inventées", "restants": _essayer(lambda: listes.fin_de_poste(badge_connu(badge)))}

    @app.get("/api/clinique/prise_de_poste")
    async def api_prise_de_poste(badge: str):
        return _essayer(lambda: listes.prise_de_poste(badge_connu(badge)))

    @app.get("/api/clinique/comptes")
    async def api_comptes(badge: str):
        b = badge_connu(badge)
        return _essayer(lambda: {"marque": "données inventées", "patients": porte.comptes(b), "listes": listes.comptes(b)})

    # ------------------------------------------------------------------ les gestes (ils écrivent dans le carnet)
    @app.post("/api/clinique/liste/cocher", dependencies=du_meme_site)
    async def api_cocher(p: Point):
        return _essayer(lambda: listes.cocher(badge_connu(p.badge), p.patient, p.liste, p.numero, p.hors_ligne_a))

    @app.post("/api/clinique/liste/voix", dependencies=du_meme_site)
    async def api_voix(v: Voix):
        """Cocher à la voix (T16) ou demander au robot à la voix (T17). Pas de micro ici : la phrase est tapée."""
        return _essayer(lambda: clinique.entendre(badge_connu(v.badge), v.patient, v.liste, v.phrase))

    @app.post("/api/clinique/liste/choisir", dependencies=du_meme_site)
    async def api_choisir(c: Choix):
        return _essayer(lambda: listes.choisir(badge_connu(c.badge), c.patient, c.liste, c.numero, c.choix, c.raison))

    @app.post("/api/clinique/demande", dependencies=du_meme_site)
    async def api_demande(d: Demande):
        reponse = _essayer(lambda: clinique.taches.demander(badge_connu(d.badge), d.patient, d.texte, d.choix, d.liste, d.numero))
        tache = reponse.get("tache")
        if clinique.coursier is not None and tache and tache["sorte"] == "robot":
            clinique.coursier.lancer(tache["id"])  # la course part ; chaque geste passera par le gardien
        return reponse

    @app.post("/api/clinique/demande/c-est-bien-ca", dependencies=du_meme_site)
    async def api_c_est_bien_ca(c: Confirmation):
        """H16 : « C'est bien ça » — la personne confirme d'un doigt la phrase que la tablette a entendue."""
        try:
            return _essayer(lambda: clinique.taches.c_est_bien_ca(badge_connu(c.badge), c.tache))
        except ValueError as inconnue:
            raise HTTPException(404, str(inconnue))

    @app.post("/clinique/soignant/tache/confirmer", dependencies=du_meme_site)
    async def confirmer_un_geste(badge: str, tache: str):
        """Robot sans bras : un humain de l'équipe dit « c'est fait » (l'objet est posé sur le plateau, ou repris)."""
        from fastapi.responses import RedirectResponse

        b = badge_connu(badge)
        if clinique.coursier is None:
            raise HTTPException(400, "Aucun robot n'est branché.")
        _essayer(lambda: clinique.coursier.confirmer(tache, b))
        return RedirectResponse(f"/clinique/soignant?badge={b.id}", status_code=303)

    @app.get("/clinique/pourquoi", response_class=HTMLResponse)
    async def page_pourquoi(badge: str, tache: str):
        """« Pourquoi ? » (avenant 2, K04) : les robots regardés, le choix, le feu du gardien, ce que le robot a annoncé."""
        b = badge_connu(badge)
        la_tache = next((t for t in _essayer(lambda: clinique.taches.tableau(b)) if t["id"] == tache), None)
        if la_tache is None:
            raise HTTPException(404, "Cette tâche n'est pas sur votre tableau.")
        decisions = []
        if clinique.coursier is not None:
            decisions = [e.donnees for e in clinique.coursier.systeme.bus.historique
                         if e.type == "gardien_decision" and e.conversation == f"clinique-{tache}"]
        return _page("Clinique — Pourquoi ce robot", "<h1>Pourquoi ce robot ?</h1>", dessiner_pourquoi(la_tache, decisions), "")

    @app.post("/clinique/soignant/tache/c-est-bien-ca", dependencies=du_meme_site)
    async def c_est_bien_ca_au_tableau(badge: str, tache: str):
        """H16 : le même « C'est bien ça », depuis le tableau des demandes (il reste là tant que ce n'est pas confirmé)."""
        from fastapi.responses import RedirectResponse

        b = badge_connu(badge)
        try:
            _essayer(lambda: clinique.taches.c_est_bien_ca(b, tache))
        except ValueError as inconnue:
            raise HTTPException(404, str(inconnue))
        return RedirectResponse(f"/clinique/soignant?badge={b.id}", status_code=303)

    @app.post("/clinique/accueil/sortie/cocher", dependencies=du_meme_site)
    async def cocher_un_point_de_sortie(badge: str, patient: str, numero: int):
        """H17 : l'accueil coche l'un de ses trois points de la liste de sortie."""
        from fastapi.responses import RedirectResponse

        b = badge_connu(badge)
        _essayer(lambda: listes.cocher_pour_l_accueil(b, patient, numero))
        return RedirectResponse(f"/clinique/accueil?badge={b.id}", status_code=303)

    @app.post("/clinique/soignant/tache/constater", dependencies=du_meme_site)
    async def constater_une_livraison(badge: str, tache: str):
        """« Je l'ai vu » : une personne constate une livraison (avenant 2, K03). Écrit CONSTATÉ dans la boîte noire."""
        from fastapi.responses import RedirectResponse

        b = badge_connu(badge)
        _essayer(lambda: clinique.taches.constater(b, tache))
        bus = getattr(clinique.horloge, "bus", None)
        if bus is not None:
            await bus.emettre("note", "clinique", quoi="temps_d_un_geste", temps="CONSTATÉ", tache=tache, par=b.id,
                              etiquette="constaté par une personne", comment=f"une personne l'a vu ({b.id})")
        return RedirectResponse(f"/clinique/soignant?badge={b.id}", status_code=303)

    @app.get("/api/clinique/taches")
    async def api_taches(badge: str):
        return {"marque": "données inventées", "taches": _essayer(lambda: clinique.taches.tableau(badge_connu(badge)))}

    @app.post("/api/clinique/je_sors", dependencies=du_meme_site)
    async def api_je_sors(s: Sortie):
        return _essayer(lambda: listes.je_sors(badge_connu(s.badge), s.patient))


# ---------------------------------------------------------------------- la grande répétition
def etape_6():
    """Étape 6 : la liste « installation » s'affiche avec les habitudes. Par la vraie page, demandée par le programme."""
    from fastapi.testclient import TestClient

    from .carnet import Carnet
    from .ecrans import brancher_ecrans
    from .horloge import HorlogeDeDemonstration
    from .porte import JournalDesAcces, PorteDeLecture
    from .repetition import Resultat

    horloge = HorlogeDeDemonstration()
    app = FastAPI()
    brancher_ecrans(app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), horloge=horloge,
                    carnet=Carnet(horloge=horloge))
    page = TestClient(app).get("/clinique/soignant/liste",
                               params={"badge": "soignant-etage-2", "patient": "p01", "liste": "installation"})
    attendus = ("Madame Giulia B.", "entend mal de l&#x27;oreille gauche", "Montrer la sonnette et la laisser à portée de main.",
                "Mettre le déambulateur à portée de main.", "DONNÉES INVENTÉES — DÉMONSTRATION")
    manquent = [a for a in attendus if a not in page.text]
    boutons = page.text.count("data-cocher=")
    return Resultat(page.status_code == 200 and not manquent and boutons == 6, "SIMULÉ",
                    f"page demandée par le programme, pas sur une tablette ; habitudes et {boutons} points affichés"
                    + (f" ; il manque : {manquent}" if manquent else ""))
