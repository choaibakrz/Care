"""Brique 13 (version minimale de l'étape 1) — le serveur de l'écran, sur le Wi-Fi local.

- GET  /                 la page (aucun fichier venu d'Internet)
- GET  /jury             l'écran du jury (étape 4) ; ses routes sont dans jury.py
- WS   /ws               les événements en direct (aussi pour le motion design)
- GET  /api/flux         la même chose, en texte simple (une ligne JSON par événement)
- POST /api/dire         taper une phrase (le « bouton tablette », en attendant la voix)          [protégé]
- POST /api/arret_urgence  OUVERT À TOUS, toujours
- POST /api/rearmer, /api/panne, /api/reparer                                                 [protégé]

[protégé] = permis depuis l'ordinateur-cerveau lui-même, ou depuis le Wi-Fi avec le code d'équipe
(en-tête « X-Code-Equipe », réglé dans reglages.yaml). Une page venue d'un autre site est toujours refusée.
- GET  /api/carte, /api/etat, /api/fiche, /api/monde
- Étape 4 (gardien, main levée) : /api/gardien/…, /api/aides, /api/aide/… — voir routes_confiance.py
- Brique 11 (la main humaine) : /api/main_humaine/… — voir briques/b11_main_humaine/routes.py
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import hmac
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from briques.b13_ecran.routes_confiance import ajouter_routes_confiance
from commun.evenements import Evenement
from commun.systeme import Systeme

STATIQUE = Path(__file__).with_name("static")
LOCAUX = {"127.0.0.1", "::1", "localhost"}
NOMS_LOCAUX = {"127.0.0.1", "localhost", "::1"}  # noms d'hôte acceptés sans code (contre le « rebond DNS »)


def code_equipe_de(reglages: dict) -> str:
    """Le code d'équipe : la variable d'environnement LEUKERBAD_CODE_EQUIPE d'abord (hors des fichiers qu'un agent
    pourrait lire), sinon reglages.yaml → ecran.code_equipe."""
    import os

    return os.environ.get("LEUKERBAD_CODE_EQUIPE") or str((reglages.get("ecran") or {}).get("code_equipe") or "")


def controle_acces(code_equipe: str, local_sans_code: bool = True):
    """Fabrique la vérification des boutons protégés. `local_sans_code=False` : même sur cet ordinateur, le code est
    exigé (porte des agents : un agent qui tourne ici ne doit pas pouvoir appuyer sur les boutons des humains)."""

    def verifier(request: Request) -> None:
        origine = request.headers.get("origin")
        if origine and urlparse(origine).netloc != request.headers.get("host"):
            raise HTTPException(403, "Requête venue d'un autre site : refusée.")
        client = request.client.host if request.client else ""
        nom_hote = urlparse("//" + (request.headers.get("host") or "")).hostname or ""
        if local_sans_code and client in LOCAUX and nom_hote in NOMS_LOCAUX:
            return
        donne = request.headers.get("x-code-equipe", "")
        if code_equipe and hmac.compare_digest(donne, code_equipe):
            return
        raise HTTPException(403, "Code d'équipe manquant ou faux (voir reglages.yaml → ecran.code_equipe).")

    return verifier


class Phrase(BaseModel):
    texte: str
    langue: str | None = None


class Panne(BaseModel):
    nom: str


class JeParle(BaseModel):
    appui: bool


def creer_app(systeme: Systeme, conversation=None) -> FastAPI:
    @asynccontextmanager
    async def cycle(_app: FastAPI):
        await systeme.demarrer()
        yield
        await systeme.arreter()

    app = FastAPI(title="Carnaval — écran", docs_url="/api/docs", lifespan=cycle)
    abonnes: set[asyncio.Queue] = set()
    ecran = systeme.reglages.get("ecran") or {}
    protege = [Depends(controle_acces(code_equipe_de(systeme.reglages), bool(ecran.get("local_sans_code", True))))]

    async def diffuser(ev: Evenement) -> None:
        for q in list(abonnes):
            if q.qsize() < 1000:
                q.put_nowait(ev.model_dump(mode="json"))

    systeme.bus.abonner(diffuser)
    ajouter_routes_confiance(app, systeme, protege)  # étape 4 : gardien et main levée (fichier à part)
    from briques.b11_main_humaine.routes import ajouter_routes_main_humaine
    ajouter_routes_main_humaine(app, systeme, protege)  # brique 11 : la main humaine (fichier à part)

    app.mount("/static", StaticFiles(directory=STATIQUE), name="static")

    # Étape 4 : l'écran du jury (/jury, Internet coupé, mode silence, deuxième langue, flux simple). Voir jury.py.
    from briques.b13_ecran.jury import brancher_jury
    brancher_jury(app, systeme, protege, abonnes, conversation)

    @app.get("/")
    async def page():
        return FileResponse(STATIQUE / "index.html")

    @app.get("/api/carte")
    async def carte():
        c = systeme.prise.carte()
        return {**c.model_dump(), "resume": c.resume(), "mention": c.mention_test()}

    @app.get("/api/monde")
    async def monde():
        return systeme.monde.vue()

    @app.get("/api/etat")
    async def etat():
        e = await systeme.prise.etat()
        return {**e.model_dump(), "trace": systeme.simulation.trace() if systeme.simulation else []}

    @app.get("/api/fiche")
    async def fiche():
        return systeme.compteur.fiche().model_dump()

    @app.post("/api/dire", dependencies=protege)
    async def dire(p: Phrase):
        r = await systeme.chaine.traiter(p.texte, p.langue, source="clavier", attendre_fin=False)
        return r.model_dump()

    @app.post("/api/je_parle", dependencies=protege)
    async def je_parle(p: JeParle):
        """Bouton « je parle » : appuyer pour parler, relâcher quand on a fini."""
        if conversation is None:
            return {"ok": False, "erreur": "pas de micro branché (lancer : python3 lancer.py micro)"}
        conversation.appuyer() if p.appui else conversation.relacher()
        return {"ok": True}

    @app.get("/api/micro")
    async def micro_present():
        return {"micro": conversation is not None}

    @app.post("/api/arret_urgence")
    async def arret():
        await systeme.prise.arret_urgence(raison="bouton_ecran")
        return {"ok": True}

    @app.post("/api/rearmer", dependencies=protege)
    async def rearmer():
        return {"ok": await systeme.prise.rearmer()}

    @app.post("/api/panne", dependencies=protege)
    async def panne(p: Panne):
        if not systeme.simulation:
            return {"ok": False, "erreur": "seulement pour le faux robot"}
        try:
            systeme.simulation.provoquer_panne(p.nom)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await systeme.bus.emettre("panne", "ecran", robot=systeme.prise.robot, quoi=p.nom, provoquee=True)
        return {"ok": True}

    @app.post("/api/reparer", dependencies=protege)
    async def reparer():
        if systeme.simulation:
            systeme.simulation.reparer()
        await systeme.bus.emettre("reparation", "ecran", robot=systeme.prise.robot, quoi="tout")
        return {"ok": True}

    @app.get("/api/flux")
    async def flux():
        q: asyncio.Queue = asyncio.Queue()
        abonnes.add(q)

        async def lignes():
            try:
                while True:
                    yield json.dumps(await q.get(), ensure_ascii=False) + "\n"
            finally:
                abonnes.discard(q)

        return StreamingResponse(lignes(), media_type="application/x-ndjson")

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        q: asyncio.Queue = asyncio.Queue()
        abonnes.add(q)
        try:
            for ev in systeme.bus.historique[-200:]:
                await socket.send_json(ev.model_dump(mode="json"))
            while True:
                await socket.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            abonnes.discard(q)

    return app
