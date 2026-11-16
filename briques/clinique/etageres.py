"""L'épreuve des étagères : dix minutes, tout est compté (avenant 3, tâche M02).

Pour l'équipe, avec un VRAI robot : en dix minutes, le robot porte des objets de trois niveaux d'étagère vers une table.
5 points pour un objet pris en haut, 8 au milieu, 10 en bas ; 3 en moins par objet tombé en route.

    epreuve = Epreuve(compteur)                       # compteur : le compteur d'essais réels (J01)
    epreuve.depart(carte="…", pilote="robot", saisit=True, note="…")   # dix minutes, à la VRAIE heure
    epreuve.appui("haut")        # ou "milieu", "bas", "tombé", "aide", "arrêt" ; en mode porteur : "arrivé", "tombé"
    epreuve.annuler_le_dernier()            # une erreur de doigt : l'appui et son annulation restent écrits tous les deux
    epreuve.resultat()           # une ligne complète, jamais le score seul

Chaque appui va dans le fichier des essais réels, avec l'heure. Un objet posé est un essai « réussi » ; un objet tombé
est un essai « raté ». Après « J'ai aidé », l'objet suivant compte « réussi avec aide ». Si une personne pilote, tous
les objets comptent « réussi avec aide », et l'essai porte « RÉEL · TÉLÉCOMMANDÉ ». Le mode « porteur » (le robot ne
saisit pas) compte les trajets, les objets arrivés, les objets tombés et les aides : aucun point.

DIRE VRAI : cette page n'a compté aucun essai sur un vrai robot. Je n'écris jamais un essai réel moi-même. L'essai en
cours vit dans la mémoire du programme : si le programme s'arrête, l'essai est fini (ses lignes restent dans le fichier).
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from .essais_reels import AUCUN, CompteurReel

DUREE_S = 600
POINTS = {"haut": 5, "milieu": 8, "bas": 10}
MALUS_TOMBE = 3
AVERTISSEMENT = "Ce score ne se compare qu'à nos propres essais."
PILOTES = {"robot": "le robot tout seul", "personne": "une personne"}
PROTOCOLE = Path(__file__).resolve().parents[2] / "docs/projet/EPREUVE_ETAGERES.md"


class Refus(ValueError):
    """Cet appui n'est pas possible maintenant. Le message dit pourquoi."""


def _court(texte: Any, longueur: int) -> str:
    return " ".join(str(texte or "").split())[:longueur]


class Epreuve:
    def __init__(self, compteur: CompteurReel, montre: Callable[[], float] = time.time) -> None:
        self.compteur, self.montre = compteur, montre  # la vraie heure, pas l'horloge de démonstration
        self._essai: dict[str, Any] | None = None  # l'essai en cours, ou le dernier fini
        self._numero = 0

    # ------------------------------------------------------------------ le départ
    def depart(self, carte: str, pilote: str, saisit: bool, note: str = "") -> dict[str, Any]:
        if self._essai is not None and not self._fini():
            raise Refus("un essai est déjà en cours : attendre sa fin, ou appuyer sur « Arrêt de sécurité »")
        if pilote not in PILOTES:
            raise Refus("qui pilote : « le robot tout seul » ou « une personne »")
        carte = _court(carte, 60)
        if not carte:
            raise Refus("il faut la carte du robot (son nom)")
        self._numero += 1
        debut = self.montre()
        ident = f"etageres-{datetime.fromtimestamp(debut).strftime('%Y%m%d-%H%M%S')}-{self._numero}"
        self._essai = {"id": ident, "debut": debut, "carte": carte, "pilote": pilote, "saisit": bool(saisit),
                       "mode": "étagères" if saisit else "porteur", "note": _court(note, 120), "appuis": [], "arret": None,
                       "fini": False, "etiquette": "RÉEL · TÉLÉCOMMANDÉ" if pilote == "personne" else "RÉEL",
                       "date": datetime.fromtimestamp(debut).strftime("%d.%m.%Y, %H:%M")}
        self.compteur.noter("départ", epreuve=ident, carte=carte, pilote=PILOTES[pilote], saisit=bool(saisit),
                            mode=self._essai["mode"], note=self._essai["note"], etiquette=self._essai["etiquette"])
        return self.etat()

    def _fini(self) -> bool:
        essai = self._essai
        if essai is None:
            return True
        if not essai["fini"] and self.montre() - essai["debut"] >= DUREE_S:
            essai["fini"] = True
            self.compteur.noter("fin", epreuve=essai["id"], raison="dix minutes")
        return essai["fini"]

    def _en_cours(self) -> dict[str, Any]:
        if self._essai is None:
            raise Refus("aucun essai en cours : appuyer d'abord sur « Départ »")
        deja = self._essai["fini"]
        if self._fini():
            raise Refus("l'essai est fini : cet appui n'est pas compté" + ("" if deja or self._essai["arret"] else " (dix minutes, pas une de plus)"))
        return self._essai

    def _valides(self) -> list[dict[str, Any]]:
        return [a for a in (self._essai["appuis"] if self._essai else []) if not a["annule"]]

    # ------------------------------------------------------------------ les appuis
    def appui(self, quoi: str, note: str = "") -> dict[str, Any]:
        essai = self._en_cours()
        porteur = essai["mode"] == "porteur"
        permis = ("arrivé", "tombé", "aide", "arrêt") if porteur else (*POINTS, "tombé", "aide", "arrêt")
        if quoi not in permis:
            raise Refus(f"appui inconnu « {quoi} » (possibles : {', '.join(permis)})")
        numero = len(essai["appuis"]) + 1
        appui = {"id": f"{essai['id']}-a{numero}", "quoi": quoi, "annule": False, "avec_aide": False}
        if quoi == "arrêt":
            essai["arret"], essai["fini"] = _court(note, 120) or "sans note", True
            self.compteur.noter("arrêt de sécurité", epreuve=essai["id"], note=essai["arret"], id=appui["id"])
        elif quoi == "aide":
            self.compteur.noter("aide", epreuve=essai["id"], id=appui["id"], note=_court(note, 120))
        else:
            valides = self._valides()
            aide_avant = bool(valides) and valides[-1]["quoi"] == "aide"
            appui["avec_aide"] = essai["pilote"] == "personne" or aide_avant
            if quoi == "tombé":
                geste = "porter" if porteur else "étagères, tombé en route"
            else:
                geste = "porter" if porteur else f"étagères, {quoi}"
            self.compteur.compter(essai["carte"], geste, quoi != "tombé", _court(note, 120), avec_aide=appui["avec_aide"],
                                  plus={"id": appui["id"], "epreuve": essai["id"], "etiquette": essai["etiquette"]})
        essai["appuis"].append(appui)
        return self.etat()

    def annuler_le_dernier(self) -> dict[str, Any]:
        """Annuler le dernier appui (erreur de doigt). L'appui et son annulation restent écrits tous les deux."""
        essai = self._en_cours()
        valides = self._valides()
        if not valides:
            raise Refus("il n'y a aucun appui à annuler")
        dernier = valides[-1]
        dernier["annule"] = True
        self.compteur.noter("annulation", epreuve=essai["id"], annule=dernier["id"], quoi=dernier["quoi"])
        return self.etat()

    # ------------------------------------------------------------------ lire
    def etat(self) -> dict[str, Any]:
        resume = self.compteur.resume()
        if self._essai is None:
            return {"essai": False, "fini": True, "reel": resume["texte"], "avertissement": AVERTISSEMENT}
        essai, fini = self._essai, self._fini()
        valides = self._valides()
        par_niveau = {n: sum(1 for a in valides if a["quoi"] == n) for n in POINTS}
        tombes = sum(1 for a in valides if a["quoi"] == "tombé")
        arrives = sum(1 for a in valides if a["quoi"] == "arrivé")
        aides = sum(1 for a in valides if a["quoi"] == "aide")
        porteur = essai["mode"] == "porteur"
        score = None if porteur else sum(POINTS[n] * k for n, k in par_niveau.items()) - MALUS_TOMBE * tombes
        reste = 0 if fini else max(0, int(round(DUREE_S - (self.montre() - essai["debut"]))))
        return {"essai": True, "id": essai["id"], "mode": essai["mode"], "fini": fini, "reste_s": reste, "score": score,
                "par_niveau": par_niveau, "tombes": tombes, "aides": aides, "trajets": arrives + tombes if porteur else None,
                "arrives": arrives if porteur else None, "pilote": PILOTES[essai["pilote"]], "carte": essai["carte"],
                "etiquette": essai["etiquette"], "arret": essai["arret"], "date": essai["date"], "note": essai["note"],
                "avec_aide": sum(1 for a in valides if a["avec_aide"] and a["quoi"] != "tombé"),
                "reel": resume["texte"], "avertissement": AVERTISSEMENT}

    def resultat(self) -> str:
        """La ligne complète : jamais le score seul."""
        e = self.etat()
        if not e["essai"]:
            return AUCUN
        if e["mode"] == "porteur":
            compte = f"mode porteur — trajets : {e['trajets']} — arrivés : {e['arrives']} — tombés : {e['tombes']}"
        else:
            niveaux = ", ".join(f"{n} : {k}" for n, k in e["par_niveau"].items())
            compte = f"score : {e['score']} — objets par niveau : {niveaux} — tombés : {e['tombes']}"
        arret = f" — arrêt de sécurité : {e['arret']}" if e["arret"] else ""
        return (f"{compte} — aides : {e['aides']} (objets comptés « avec aide » : {e['avec_aide']}) — pilote : {e['pilote']} — "
                f"carte du robot : {e['carte']} — {e['date']}{arret} — [{e['etiquette']}]")


# ---------------------------------------------------------------------- la page, lisible sur un téléphone
class Depart(BaseModel):
    carte: str
    pilote: str = "robot"
    saisit: bool = True
    note: str = ""


class Appui(BaseModel):
    quoi: str
    note: str = ""


STYLE = ("<style>.gros{font-size:1.6rem;padding:.9rem 1rem;margin:.3rem;min-width:9rem}.chiffre{font-size:2.6rem;font-weight:bold}"
         ".rouge{background:#b00020;color:#fff}</style>")
SCRIPT = """<script>
const tete = () => { const t = {'Content-Type': 'application/json'}; const c = document.getElementById('code').value;
  if (c) t['X-Code-Equipe'] = c; return t; };
const dit = document.getElementById('dit');
async function rafraichir() {
  const r = await fetch('/clinique/etageres/contenu', {cache: 'no-store'});
  document.getElementById('compte').innerHTML = await r.text();
}
async function envoyer(chemin, corps) {
  try {
    const r = await fetch('/api/clinique/etageres/' + chemin, {method: 'POST', headers: tete(), body: JSON.stringify(corps || {})});
    const j = await r.json();
    dit.textContent = r.ok ? 'Noté.' : 'Refusé : ' + (j.detail || r.status);
  } catch (e) { dit.textContent = 'Connexion perdue : rien n\\'a été compté.'; }
  rafraichir();
}
document.getElementById('depart').onclick = () => envoyer('depart', {
  carte: document.getElementById('carte').value, pilote: document.getElementById('pilote').value,
  saisit: document.getElementById('saisit').value === 'oui', note: document.getElementById('note').value});
document.querySelectorAll('button[data-appui]').forEach(b => b.onclick = () =>
  envoyer('appui', {quoi: b.dataset.appui, note: b.dataset.appui === 'arrêt' ? document.getElementById('note').value : ''}));
document.getElementById('annuler').onclick = () => envoyer('annuler');
setInterval(rafraichir, 1000);
</script>"""


def dessiner(epreuve: Epreuve) -> str:
    from .ecrans import _e

    e = epreuve.etat()
    if not e["essai"]:
        return f"<p class='dit'>{_e(e['reel'])}</p><p>Aucun essai lancé depuis le démarrage du programme.</p>"
    minutes, secondes = divmod(e["reste_s"], 60)
    temps = "essai fini" if e["fini"] else f"{minutes} min {secondes:02d} s"
    gros = "" if e["score"] is None else f" — score <span class='chiffre'>{e['score']}</span>"
    return (f"<p>Temps qui reste : <span class='chiffre'>{_e(temps)}</span>{gros}</p>"
            f"<p class='dit'>{_e(epreuve.resultat())}</p><p><b>{_e(AVERTISSEMENT)}</b></p>"
            f"<p class='dit'>{_e(e['reel'])}</p>")


def brancher_etageres(app, clinique, protege: list) -> None:
    from fastapi import HTTPException
    from fastapi.responses import HTMLResponse

    from .ecrans import _e, _heure_html, _page

    clinique.etageres = Epreuve(clinique.essais_reels)

    def epreuve() -> Epreuve:
        return clinique.etageres

    def essayer(geste: Callable[[], Any]) -> dict[str, Any]:
        try:
            geste()
        except Refus as refus:
            raise HTTPException(400, str(refus))
        return {"etat": epreuve().etat(), "resultat": epreuve().resultat(), "resume": clinique.essais_reels.resume()}

    @app.get("/clinique/etageres", response_class=HTMLResponse)
    async def page_etageres():
        tete = f"<h1>Étagères</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        milieu = (STYLE + "<p class='ou'>Pour l'équipe, avec un <b>vrai robot</b>. Dix minutes à la vraie heure. Chaque appui est écrit "
                  "avec l'heure dans le fichier des essais réels ; rien ne s'efface. 5 points en haut, 8 au milieu, 10 en bas ; "
                  "3 en moins par objet tombé. Ne comptez jamais ici un essai fait sur le faux robot. "
                  "<a href='/clinique/epreuve-etageres'>Le protocole de l'épreuve (à imprimer)</a> · "
                  "<a href='/clinique/essais-reels'>Le compteur d'essais réels</a></p>"
                  "<p><label>Carte du robot <input id='carte' size='18' maxlength='60'></label> "
                  "<label>Qui pilote <select id='pilote'><option value='robot'>le robot tout seul</option>"
                  "<option value='personne'>une personne</option></select></label> "
                  "<label>Le robot saisit lui-même <select id='saisit'><option value='oui'>oui</option>"
                  "<option value='non'>non (mode porteur)</option></select></label></p>"
                  "<p><label>Note courte <input id='note' size='30' maxlength='120'></label> "
                  "<label>Code d'équipe <input id='code' size='10' type='password' autocomplete='off'></label></p>"
                  "<p><button class='gros' id='depart'>Départ</button></p>"
                  "<p><button class='gros' data-appui='haut'>posé — haut</button>"
                  "<button class='gros' data-appui='milieu'>posé — milieu</button>"
                  "<button class='gros' data-appui='bas'>posé — bas</button></p>"
                  "<p><button class='gros' data-appui='arrivé'>arrivé (mode porteur)</button>"
                  "<button class='gros' data-appui='tombé'>tombé</button>"
                  "<button class='gros' data-appui='aide'>J'ai aidé</button></p>"
                  "<p><button class='gros rouge' data-appui='arrêt'>Arrêt de sécurité</button> "
                  "<button id='annuler'>Annuler le dernier appui</button></p>"
                  "<div class='dit' id='dit' role='status'></div>"
                  f"<div id='compte'>{dessiner(epreuve())}</div>")
        return _page("Clinique — Étagères", tete, milieu, SCRIPT)

    @app.get("/clinique/etageres/contenu", response_class=HTMLResponse)
    async def page_etageres_contenu():
        return dessiner(epreuve())

    @app.get("/clinique/epreuve-etageres", response_class=HTMLResponse)
    async def page_protocole():
        texte = PROTOCOLE.read_text(encoding="utf-8") if PROTOCOLE.exists() else "Le fichier docs/projet/EPREUVE_ETAGERES.md manque."
        lignes = "".join(f"<p>{_e(l)}</p>" for l in texte.splitlines() if l.strip() and not l.startswith("#"))
        return _page("Clinique — L'épreuve des étagères", "<h1>L'épreuve des étagères</h1>", lignes, "")

    @app.get("/api/clinique/etageres")
    async def api_lire():
        return {"etat": epreuve().etat(), "resultat": epreuve().resultat(), "resume": clinique.essais_reels.resume()}

    @app.post("/api/clinique/etageres/depart", dependencies=protege)
    async def api_depart(d: Depart):
        return essayer(lambda: epreuve().depart(d.carte, d.pilote, d.saisit, d.note))

    @app.post("/api/clinique/etageres/appui", dependencies=protege)
    async def api_appui(a: Appui):
        return essayer(lambda: epreuve().appui(a.quoi, a.note))

    @app.post("/api/clinique/etageres/annuler", dependencies=protege)
    async def api_annuler():
        return essayer(lambda: epreuve().annuler_le_dernier())
