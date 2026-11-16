"""Brique 13 — L'écran du jury (étape 4). serveur.py appelle `brancher_jury(...)`, qui ajoute :

- GET  /jury                    la page du jury (grand écran ; tout est servi par cet ordinateur, rien d'Internet)
- GET  /api/jury/etat           Internet coupé ? mode silence ? traducteur ? langues, pictogrammes
- POST /api/internet_coupe      {"coupe": true | false} : coupe ou rétablit les sorties vers Internet      [protégé]
- POST /api/mode_silence        {"actif": true | false} : voix en sous-titres seulement, pictos en grand  [protégé]
- GET  /api/traduire/{id}?langue=de   une réponse du robot (ou une phrase de la personne) dans une autre langue
- GET  /api/flux_simple         une ligne JSON courte par événement (motion design) :
                                ?types=a,b  ?sans=a,b  ?historique=N (les N derniers d'abord)  ?max=N (puis s'arrête)
                                ?direct=0 (seulement l'historique, puis s'arrête)
- WS   /ws_simple               la même chose en WebSocket ; ?complet=1 ajoute l'événement entier (utilisé par /jury)

[protégé] = même règle que les autres boutons (voir `controle_acces` dans serveur.py). L'arrêt d'urgence reste ouvert.
Rien ici ne parle au robot : l'écran lit les événements et ne touche ni au gardien ni à la prise.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from commun.phrases import langue_de_reponse, langues

from .flux_simple import PICTOS, filtre, ligne_simple
from .internet import Coupure, EtagesEteints, limites_de_la_coupure
from .traduction import INDISPONIBLE, Traducteur, TraducteurAbsent

STATIQUE = Path(__file__).with_name("static")
HISTORIQUE_MAX = 5000
DELAI_TRADUCTION_S = 5.0


class ChoixInternet(BaseModel):
    coupe: bool


class ChoixSilence(BaseModel):
    actif: bool


class Jury:
    """L'état de l'écran du jury : Internet coupé, mode silence, traducteur."""

    def __init__(self, systeme: Any, conversation: Any = None, traducteur: Traducteur | None = None) -> None:
        self.s = systeme
        self.conversation = conversation
        self.traducteur: Traducteur = traducteur or TraducteurAbsent()
        # reglages.yaml → ecran → internet_coupe → toujours_permis : le robot et l'autre Mac (noms ou adresses).
        coupure = (systeme.reglages.get("ecran") or {}).get("internet_coupe")
        coupure = coupure if isinstance(coupure, dict) else {}
        self.coupure = Coupure(toujours_permis=coupure.get("toujours_permis") or [])
        self.etages = EtagesEteints()
        self.preuve: str | None = None
        self.silence = False
        self._voix_normale: Any = None
        interrupteur = (systeme.reglages.get("interrupteurs") or {}).get("mode_silence") or {}
        if interrupteur.get("actif"):
            self._appliquer_silence(True)  # reglages.yaml → interrupteurs.mode_silence.actif

    # ------------------------------------------------------------ état
    def etat(self) -> dict:
        tout = langues()["langues"]
        return {
            "internet_coupe": self.coupure.coupe, "depuis": self.coupure.depuis, "preuve": self.preuve,
            "connexions_refusees": self.coupure.refusees, "dernieres_refusees": list(self.coupure.dernieres),
            "etages_eteints": self.etages.noms, "limites": limites_de_la_coupure(),
            "mandataires_coupes": sorted(f"{h}:{p}" for h, p in self.coupure.mandataires) if self.coupure.coupe else [],
            "toujours_permis": list(self.coupure.toujours_permis),
            "silence": self.silence, "micro": self.conversation is not None,
            "traducteur": {"nom": self.traducteur.nom, "disponible": bool(self.traducteur.disponible)},
            "langues": {code: info["nom"] for code, info in tout.items()},
            "langues_reponse": sorted({info["reponse"] for info in tout.values()}),
            "pictos": PICTOS,
        }

    # ------------------------------------------------------------ Internet coupé
    async def internet(self, coupe: bool) -> dict:
        robot = self.s.prise.robot
        if coupe and not self.coupure.coupe:
            self.coupure.couper()
            self.preuve = self.coupure.essai()
            eteints = await self.etages.eteindre(self.s.cerveau, self.coupure.toujours)
            await self.s.bus.emettre("internet_coupe", "ecran", robot=robot, coupe=True, preuve=self.preuve,
                                     etages_eteints=eteints, limites=limites_de_la_coupure())
        elif not coupe and self.coupure.coupe:
            refusees = self.coupure.refusees
            self.coupure.retablir()
            rallumes = self.etages.rallumer()
            self.preuve = None
            await self.s.bus.emettre("internet_coupe", "ecran", robot=robot, coupe=False, etages_rallumes=rallumes,
                                     connexions_refusees=refusees)
        return self.etat()

    # ------------------------------------------------------------ mode silence
    def _appliquer_silence(self, actif: bool) -> None:
        self.silence = actif
        c = self.conversation
        if c is None:
            return  # pas de micro ni de voix : seul l'écran change
        if actif and self._voix_normale is None:
            from briques.b04_oreilles_voix.voix import VoixTexte

            self._voix_normale = c.voix
            c.voix = VoixTexte()  # plus de son : les réponses s'affichent seulement
            c.hp.couper()  # et s'il parlait, il se tait tout de suite
        elif not actif and self._voix_normale is not None:
            c.voix = self._voix_normale
            self._voix_normale = None

    async def mode_silence(self, actif: bool) -> dict:
        if actif != self.silence:
            self._appliquer_silence(actif)
            await self.s.bus.emettre("mode_silence", "ecran", robot=self.s.prise.robot, actif=actif,
                                     voix="sous-titres seulement" if actif else "voix normale",
                                     micro=self.conversation is not None)
        return self.etat()

    # ------------------------------------------------------------ deuxième langue
    async def traduire(self, ident: str, langue: str, de: str | None = None) -> dict:
        if langue not in langues()["langues"]:
            raise HTTPException(400, f"Langue inconnue : {langue}")
        ev = next((e for e in reversed(self.s.bus.historique) if e.id == ident), None)
        if ev is None:
            raise HTTPException(404, "Événement inconnu (trop ancien ?)")
        d = ev.donnees
        vers = langue_de_reponse(langue)
        if ev.type == "reponse_dite":
            if d.get("langue") == vers:
                return _rendu(d.get("texte") or "", vers, "meme_langue")
            if d.get("cle"):
                return _rendu(self.s.chaine.redire(d["cle"], d.get("valeurs"), vers), vers, "phrase_connue")
            texte, de = d.get("texte") or "", de or d.get("langue")  # écrite par un modèle : à traduire
        elif ev.type in ("parole_entendue", "transcription", "mot_d_appel"):
            texte, de = d.get("texte") or "", de or d.get("langue")
            if de == langue:
                return _rendu(texte, langue, "meme_langue")
        else:
            raise HTTPException(400, "Seulement les phrases : parole_entendue, transcription, reponse_dite.")
        return await self._traduire_libre(texte, de, vers)

    async def _traduire_libre(self, texte: str, de: str | None, vers: str) -> dict:
        if not texte.strip():
            return _rendu("", vers, "vide")
        if not self.traducteur.disponible:
            return {"ok": False, "texte": None, "langue": vers, "comment": "indisponible", "message": INDISPONIBLE}
        try:
            r = await asyncio.wait_for(self.traducteur.traduire(texte, de, vers), DELAI_TRADUCTION_S)
        except Exception:  # noqa: BLE001 - un traducteur en panne ne doit jamais casser l'écran
            r = None
        if r:
            return {"ok": True, "texte": r, "langue": vers, "comment": f"traduit par {self.traducteur.nom}"}
        return {"ok": False, "texte": None, "langue": vers, "comment": "echec",
                "message": f"traduction impossible pour l'instant ({self.traducteur.nom})"}


def _rendu(texte: str, langue: str, comment: str) -> dict:
    return {"ok": True, "texte": texte, "langue": langue, "comment": comment}


def brancher_jury(app: FastAPI, systeme: Any, protege: list, abonnes: set, conversation: Any = None,
                  traducteur: Traducteur | None = None) -> Jury:
    """Ajoute les routes du jury. `abonnes` : les files du serveur, qui reçoivent chaque événement (en JSON)."""
    jury = Jury(systeme, conversation, traducteur)
    app.state.jury = jury  # pour brancher plus tard un traducteur : app.state.jury.traducteur = ...

    def passes(n: int) -> list[dict]:
        n = max(0, min(int(n), HISTORIQUE_MAX))
        return [ev.model_dump(mode="json") for ev in systeme.bus.historique[-n:]] if n else []

    @app.get("/jury")
    async def page_jury():
        return FileResponse(STATIQUE / "jury.html")

    @app.get("/api/jury/etat")
    async def etat_jury():
        return jury.etat()

    @app.post("/api/internet_coupe", dependencies=protege)
    async def internet_coupe(c: ChoixInternet):
        return await jury.internet(c.coupe)

    @app.post("/api/mode_silence", dependencies=protege)
    async def mode_silence(m: ChoixSilence):
        return await jury.mode_silence(m.actif)

    @app.get("/api/traduire/{ident}")
    async def traduire(ident: str, langue: str, de: str | None = None):
        return await jury.traduire(ident, langue, de or None)

    @app.get("/api/flux_simple")
    async def flux_simple(types: str = "", sans: str = "", historique: int = 0, nombre_max: int = Query(0, alias="max"),
                          direct: int = 1):
        accepte = filtre(types, sans)
        q: asyncio.Queue = asyncio.Queue()
        abonnes.add(q)  # d'abord s'abonner, puis copier l'historique : rien ne se perd, rien n'est en double
        anciens = passes(historique)

        async def lignes():
            n = 0
            try:
                for e in anciens:
                    if accepte(e):
                        yield json.dumps(ligne_simple(e), ensure_ascii=False) + "\n"
                        n += 1
                        if nombre_max and n >= nombre_max:
                            return
                if not direct:
                    return  # direct=0 : seulement l'historique (une photo du moment), puis on s'arrête
                while True:
                    e = await q.get()
                    if accepte(e):
                        yield json.dumps(ligne_simple(e), ensure_ascii=False) + "\n"
                        n += 1
                        if nombre_max and n >= nombre_max:
                            return
            finally:
                abonnes.discard(q)

        return StreamingResponse(lignes(), media_type="application/x-ndjson")

    @app.websocket("/ws_simple")
    async def ws_simple(socket: WebSocket, types: str = "", sans: str = "", historique: int = 50, complet: int = 0):
        await socket.accept()
        accepte = filtre(types, sans)
        q: asyncio.Queue = asyncio.Queue()
        abonnes.add(q)
        anciens = passes(historique)

        def message(e: dict) -> dict:
            return {**e, "simple": ligne_simple(e)} if complet else ligne_simple(e)

        try:
            for e in anciens:
                if accepte(e):
                    await socket.send_json(message(e))
            while True:
                e = await q.get()
                if accepte(e):
                    await socket.send_json(message(e))
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            abonnes.discard(q)

    return jury
