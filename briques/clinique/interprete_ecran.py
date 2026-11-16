"""H10b — Le mode interprète sur l'écran de régie (message de Hiba, 12.11.2026).

    /clinique/regie                                 la page : le bouton à tenir, l'anglais en grand, les réponses préparées
    POST /api/clinique/interprete/phrase            le son enregistré pendant que le bouton était tenu (un fichier son)
    GET  /api/clinique/interprete/preparee/{id}     la version anglaise préparée d'une réponse

- Tant que le bouton « Interprète » est tenu, la page enregistre le micro de CET ordinateur. Quand on le relâche, le son
  part au programme, sur cet ordinateur : l'écoute écrit le français, le vrai Apertus le traduit avec les mots fixés, les
  contrôles comptent les erreurs, la voix du Mac dit l'anglais, et la page l'affiche en grand, avec l'étiquette
  « TRADUCTION AUTOMATIQUE EN DIRECT ». C'est le chemin « en deux temps », le meilleur à la mesure du 12.11.
- Le deuxième bouton affiche l'anglais écrit d'avance d'une réponse : « TRADUCTION PRÉPARÉE ».
- Chaque phrase est notée avec son délai dans `journal/clinique/interprete.jsonl` (jamais envoyé). Les erreurs sont
  affichées telles quelles : une phrase fausse n'est pas corrigée en cachette.
- Rien ne sort de l'ordinateur. Il faut que le cerveau tourne (`python3 lancer.py cerveau`) ; sinon la page le dit, et
  seules les réponses préparées servent.
- Un navigateur ne donne le micro qu'à une page ouverte sur cet ordinateur même (adresse locale) : la régie est sur l'iMac.
"""
from __future__ import annotations

import io
import json
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from . import interprete

FICHIER = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "interprete.jsonl"
DOSSIER_SONS = Path(__file__).resolve().parents[2] / "journal" / "clinique" / "sons_interprete"
PLUS_GROS_SON = 2_200_000  # environ une minute de son (16 000 points par seconde, 16 bits, une voie)
PLUS_COURT_S = 0.3


class PasPret(RuntimeError):
    """Une pièce manque (le cerveau ne tourne pas, l'écoute ou la voix ne sont pas là). Le message dit quoi faire."""


class Interprete:
    """Le mode interprète de la séance : ses pièces, son fichier de délais. Les vraies pièces se créent au premier besoin."""

    def __init__(self, dossier: str | Path | None = None, ecouter: Callable | None = None, traduire: Callable | None = None,
                 dire: Callable | None = None, pret: Callable[[], tuple[bool, str]] | None = None,
                 montre: Callable[[], float] = time.perf_counter, fichier: str | Path | None = None) -> None:
        self.dossier = Path(dossier) if dossier else DOSSIER_SONS
        self.fichier = Path(fichier) if fichier else (self.dossier / "interprete.jsonl" if dossier else FICHIER)
        self._ecouter, self._traduire, self._dire, self._pret, self.montre = ecouter, traduire, dire, pret, montre
        self._verrou = threading.Lock()

    # ------------------------------------------------------------------ les vraies pièces, sur cet ordinateur
    def _serveur(self):
        from commun.systeme import charger_reglages, creer_serveurs

        return creer_serveurs(charger_reglages()).get("apertus_8b")

    def pret(self) -> tuple[bool, str]:
        if self._pret is not None:
            return self._pret()
        from . import accueil_voix, ecoute

        for oui, raison in (ecoute.disponible(), accueil_voix.voix_disponible()):
            if not oui:
                return False, raison
        serveur = self._serveur()
        if serveur is None or not serveur.en_marche():
            return False, "le cerveau ne tourne pas : lancer « python3 lancer.py cerveau » dans un terminal, puis réessayer"
        return True, ""

    def _pieces(self) -> tuple[Callable, Callable, Callable]:
        if self._ecouter and self._traduire and self._dire:
            return self._ecouter, self._traduire, self._dire
        import shutil
        import subprocess

        from . import accueil_voix, ecoute

        def dire(texte: str, langue: str, sortie: Any) -> Any:
            """La voix du Mac fabrique le son, puis le haut-parleur le joue à côté (on n'attend pas la fin pour afficher)."""
            son = accueil_voix.dire(texte, langue, sortie)
            if shutil.which("afplay"):
                subprocess.Popen(["afplay", str(son)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return son

        return (self._ecouter or ecoute.ecouter, self._traduire or interprete.traduire_avec_apertus(self._serveur().url),
                self._dire or dire)

    # ------------------------------------------------------------------ une phrase
    def lignes(self) -> list[dict[str, Any]]:
        if not self.fichier.exists():
            return []
        return [json.loads(l) for l in self.fichier.read_text(encoding="utf-8").splitlines() if l.strip()]

    def redire(self, son: bytes) -> dict[str, Any]:
        """Le son d'une phrase française → l'anglais, dit et rendu ; une ligne de plus dans le fichier des délais."""
        oui, raison = self.pret()
        if not oui:
            raise PasPret(raison)
        with self._verrou:  # une phrase à la fois
            numero = len(self.lignes()) + 1
            self.dossier.mkdir(parents=True, exist_ok=True)
            fichier_son = self.dossier / f"phrase_{numero:03d}.wav"
            fichier_son.write_bytes(son)
            ecouter, traduire, dire = self._pieces()
            r = interprete.interpreter(fichier_son, self.dossier, ecouter, traduire, dire, self.montre, nom=f"reponse_{numero:03d}")
            ligne = {"numero": numero, "quand": datetime.now().astimezone().isoformat(timespec="seconds"),
                     **{cle: r[cle] for cle in ("etiquette", "fr", "en", "erreurs", "panne", "ecoute_ms", "traduction_ms", "voix_ms", "total_ms")}}
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            with open(self.fichier, "a", encoding="utf-8") as f:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            return ligne


def duree_du_son(son: bytes) -> float:
    """La durée d'un fichier son (WAV). Lève ValueError si ce n'en est pas un."""
    try:
        with wave.open(io.BytesIO(son)) as lu:
            return lu.getnframes() / float(lu.getframerate())
    except (wave.Error, EOFError, ZeroDivisionError) as erreur:
        raise ValueError("ce n'est pas un fichier son lisible") from erreur


SCRIPT = """<script>
const bouton = document.getElementById('interprete'), etat = document.getElementById('etat');
let flux = null, contexte = null, noeud = null, morceaux = [], tenu = false;
// Demander le micro dès l'ouverture de la page, pour que la première phrase ne soit pas perdue (le navigateur demande l'accord).
if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia({audio: true}).then(f => {
  if (!flux) { flux = f; etat.textContent = 'Micro prêt. Tenir le bouton pendant toute la phrase, puis le relâcher.'; }
}).catch(() => {});
function montrer(d) {
  document.getElementById('etiquette').textContent = d.etiquette || '';
  document.getElementById('anglais').textContent = d.en || '—';
  document.getElementById('francais').textContent = d.fr ? '« ' + d.fr + ' »' : '';
  const e = d.erreurs || [];
  const zone = document.getElementById('erreurs');
  zone.textContent = e.length ? 'Erreurs comptées : ' + e.join(' ; ') : '';
  zone.hidden = !e.length;  // vu dans le navigateur (N01c) : vide, la zone restait affichée, une barre jaune sans texte
}
async function preparer() {  // le micro et l'enregistreur, une seule fois ; ils restent prêts entre deux phrases
  if (!contexte) contexte = new (window.AudioContext || window.webkitAudioContext)();  // créé pendant le geste : il a le droit de tourner
  if (contexte.state === 'suspended') contexte.resume();
  if (!flux) flux = await navigator.mediaDevices.getUserMedia({audio: true});
  if (!noeud) {
    noeud = contexte.createScriptProcessor(4096, 1, 1);
    noeud.onaudioprocess = e => { if (tenu) morceaux.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
    contexte.createMediaStreamSource(flux).connect(noeud);
    noeud.connect(contexte.destination);  // il ne joue rien : il ne fait qu'écouter
  }
}
async function commencer(evenement) {
  evenement.preventDefault();
  if (tenu) return;
  tenu = true; morceaux = [];
  etat.textContent = 'J\\'écoute… (relâcher pour traduire)';
  try { await preparer(); }
  catch (erreur) { tenu = false; etat.textContent = 'Pas de micro : ' + erreur.message + '. Les réponses préparées marchent quand même.'; }
}
function enSon(points, frequence) {  // un fichier son simple : une voie, 16 000 points par seconde, 16 bits
  const pas = frequence / 16000, n = Math.floor(points.length / pas), vue = new DataView(new ArrayBuffer(44 + 2 * n));
  const ecrire = (o, t) => { for (let i = 0; i < t.length; i++) vue.setUint8(o + i, t.charCodeAt(i)); };
  ecrire(0, 'RIFF'); vue.setUint32(4, 36 + 2 * n, true); ecrire(8, 'WAVEfmt '); vue.setUint32(16, 16, true);
  vue.setUint16(20, 1, true); vue.setUint16(22, 1, true); vue.setUint32(24, 16000, true); vue.setUint32(28, 32000, true);
  vue.setUint16(32, 2, true); vue.setUint16(34, 16, true); ecrire(36, 'data'); vue.setUint32(40, 2 * n, true);
  for (let i = 0; i < n; i++) { const v = Math.max(-1, Math.min(1, points[Math.floor(i * pas)])); vue.setInt16(44 + 2 * i, v * 32767, true); }
  return vue.buffer;
}
async function finir() {
  if (!tenu) return;
  tenu = false;
  const frequence = contexte ? contexte.sampleRate : 16000;
  const total = morceaux.reduce((n, m) => n + m.length, 0), points = new Float32Array(total);
  let o = 0; for (const m of morceaux) { points.set(m, o); o += m.length; }
  if (total < frequence * 0.3) {
    etat.textContent = flux ? 'Trop court : tenir le bouton pendant toute la phrase.'
                            : 'Le micro n\\'était pas encore prêt : recommencer en tenant le bouton.';
    return;
  }
  etat.textContent = 'Je traduis…';
  const entetes = {'Content-Type': 'audio/wav'}, code = document.getElementById('code').value;
  if (code) entetes['X-Code-Equipe'] = code;
  try {
    const r = await fetch('/api/clinique/interprete/phrase', {method: 'POST', headers: entetes, body: enSon(points, frequence)});
    const d = await r.json();
    if (!r.ok) { etat.textContent = 'Pas de traduction : ' + (d.detail || r.status); return; }
    montrer(d);
    etat.textContent = 'Phrase ' + d.numero + ' — délai : ' + (d.total_ms === null ? 'rien n\\'a été dit' : d.total_ms + ' ms');
  } catch (erreur) { etat.textContent = 'Connexion perdue : rien n\\'a été traduit.'; }
}
bouton.addEventListener('pointerdown', commencer);
for (const fin of ['pointerup', 'pointerleave', 'pointercancel']) bouton.addEventListener(fin, finir);
for (const b of document.querySelectorAll('[data-preparee]')) b.onclick = async () => {
  const r = await fetch('/api/clinique/interprete/preparee/' + encodeURIComponent(b.dataset.preparee));
  if (r.ok) { montrer(await r.json()); etat.textContent = 'Réponse préparée : ' + b.textContent; }
};
</script>"""


def brancher_interprete(app: FastAPI, clinique, protege: list) -> None:
    from .ecrans import _e, _heure_html, _page

    if getattr(clinique, "interprete", None) is None:
        clinique.interprete = Interprete()

    def historique() -> str:
        lignes = clinique.interprete.lignes()
        erreurs = sum(len(l["erreurs"]) for l in lignes)
        n = len(lignes)
        compte = (f"{n} phrase{'s' if n > 1 else ''}, {erreurs} erreur{'s' if erreurs > 1 else ''} comptée{'s' if erreurs > 1 else ''}"
                  if n else "Aucune phrase traduite pour l'instant.")
        corps = "".join(
            f"<li>{l['numero']}. « {_e(l['fr'] or '?')} » → <b>{_e(l['en'] or '—')}</b> — "
            f"{'délai ' + str(l['total_ms']) + ' ms' if l['total_ms'] is not None else 'rien n’a été dit'}"
            f"{' — erreurs : ' + _e(' ; '.join(l['erreurs'])) if l['erreurs'] else ''}</li>" for l in reversed(lignes[-20:]))
        return f"<article><h2>Les phrases traduites</h2><p class='ou'>{_e(compte)}</p><ul>{corps}</ul></article>"

    @app.get("/clinique/regie", response_class=HTMLResponse)
    async def page_regie():
        oui, raison = clinique.interprete.pret()
        tete = f"<h1>Régie — interprète</h1><span class='heure' id='heure'>{_heure_html(clinique.horloge.etat())}</span>"
        preparees = "".join(f"<button data-preparee=\"{_e(r['id'])}\">{_e(r['titre'])}</button> " for r in interprete.reponses_preparees())
        alerte = "" if oui else f"<p class='refus'>Le bouton « Interprète » ne peut pas traduire maintenant : {_e(raison)}.</p>"
        milieu = (
            "<p class='ou'>La personne répond en français. La boîte redit la phrase en anglais, à voix haute, et l'affiche ici. "
            "Tout se passe sur cet ordinateur, sans Internet. Une traduction automatique peut se tromper : les erreurs que le "
            "programme sait voir sont comptées et affichées.</p>" + alerte +
            "<p><b id='etiquette' style='letter-spacing:.04em'>TRADUCTION AUTOMATIQUE EN DIRECT</b></p>"
            "<p id='anglais' style='font-size:2.6rem;line-height:1.2;font-weight:700;margin:.3rem 0'>—</p>"
            "<p class='ou' id='francais'></p><p class='refus' id='erreurs' hidden></p>"
            "<p><button id='interprete' style='font-size:1.4rem;padding:1rem 1.6rem;touch-action:none'>Interprète</button> "
            "<span id='etat' role='status'>Tenir le bouton pendant toute la phrase, puis le relâcher.</span></p>"
            "<p class='ou'>Tenir le bouton : la boîte écoute. Le relâcher : elle traduit, dit la phrase en anglais, et l'affiche en grand.</p>"
            f"<article><h2>Réponses préparées</h2><p class='ou'>L'anglais est écrit d'avance : étiquette <b>TRADUCTION PRÉPARÉE</b>. "
            f"Fichier : <code style='overflow-wrap:anywhere'>briques/clinique/interprete_reponses.yaml</code>.</p><p>{preparees}</p></article>"
            "<p class='ou'>Mots fixés d'avance (toujours traduits de la même façon) : <code style='overflow-wrap:anywhere'>briques/clinique/interprete_mots.yaml</code>. "
            "<label>Code d'équipe (depuis un autre ordinateur) <input id='code' size='12' type='password' autocomplete='off'></label></p>"
            + historique())
        return _page("Clinique — Régie, interprète", tete, milieu, SCRIPT)

    @app.post("/api/clinique/interprete/phrase", dependencies=protege)
    async def api_phrase(requete: Request):
        son = await requete.body()
        if len(son) > PLUS_GROS_SON:
            raise HTTPException(413, "le son est trop long : une phrase à la fois (une minute au plus)")
        try:
            duree = duree_du_son(son)
        except ValueError as erreur:
            raise HTTPException(400, str(erreur))
        if duree < PLUS_COURT_S:
            raise HTTPException(400, "le son est trop court : tenir le bouton pendant toute la phrase")
        import asyncio

        try:
            return await asyncio.to_thread(clinique.interprete.redire, son)  # à côté : les autres écrans restent vivants
        except PasPret as erreur:
            raise HTTPException(503, str(erreur))

    @app.get("/api/clinique/interprete/preparee/{ident}")
    async def api_preparee(ident: str):
        for reponse in interprete.reponses_preparees():
            if reponse["id"] == ident:
                return {"etiquette": reponse["etiquette"], "titre": reponse["titre"], "fr": reponse["fr"], "en": reponse["en"], "erreurs": []}
        raise HTTPException(404, "cette réponse préparée n'existe pas")

    @app.get("/api/clinique/interprete/historique")
    async def api_historique():
        return {"marque": "données inventées", "lignes": clinique.interprete.lignes()}
