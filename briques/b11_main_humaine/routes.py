"""Brique 11 — Les routes de la main humaine. serveur.py (brique 13) appelle `ajouter_routes_main_humaine(...)`.

[protégé] = comme les autres boutons : sur l'ordinateur-cerveau, ou avec le code d'équipe (en-tête X-Code-Equipe).
L'arrêt d'urgence (/api/arret_urgence) reste ouvert à tous ; « stop » à la voix passe toujours.
[jeton] = en plus, le jeton remis par « prendre » à la tablette qui a pris la main (champ `jeton`).

- GET  /api/main_humaine           qui a la main, depuis quand, la demande du chef, les boutons possibles (actions de
                                   la carte), les demandes du gardien qui attendent un humain, les mots appris, les
                                   votes du public. ?court=1 : seulement qui, depuis, consigne (écran du jury).
                                   En-tête X-Jeton-Main (facultatif) : `a_moi` dit si cette tablette a la main.
- POST /api/main_humaine/prendre   {qui}                          « Je prends la main » → rend le `jeton`   [protégé]
- POST /api/main_humaine/rendre    {jeton, qui, fait?}            « Je rends la main »            [protégé] [jeton]
                                   {qui, forcer: true}            « Libérer la main » (autre tablette, noté) [protégé]
- POST /api/main_humaine/ordre     {jeton, nom, parametres, qui, langue?}  un bouton : vers le gardien [protégé] [jeton]
- GET  /main_humaine/…             le morceau de page de l'écran de l'équipe (main_humaine.js, main_humaine.css)

Les réponses aux demandes du gardien, les mots appris et le vote utilisent les routes qui existaient déjà
(/api/aide/repondre, /api/aide/apprendre, /api/gardien/vote : briques/b13_ecran/routes_confiance.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .main_humaine import MainHumaine, Refus

STATIQUE = Path(__file__).with_name("static")
Court = Annotated[str, Field(max_length=40)]
Jeton = Annotated[str, Field(max_length=64)]
Valeur = str | float | None  # une précision : un texte (lieu, objet, geste…) ou un nombre (dx, vitesse…)


class Qui(BaseModel):
    qui: Court = ""


class Rendu(BaseModel):
    jeton: Jeton = ""
    qui: Court = ""
    fait: bool | None = None  # seulement quand le chef de démonstration a demandé quelque chose
    forcer: bool = False  # « Libérer la main » depuis une autre tablette (noté dans la boîte noire)


class Ordre(BaseModel):
    jeton: Jeton = ""
    nom: Annotated[str, Field(max_length=30)]
    parametres: Annotated[dict[Annotated[str, Field(max_length=30)], Valeur], Field(max_length=8)] = Field(default_factory=dict)
    qui: Court = ""
    langue: Annotated[str, Field(max_length=5)] | None = None


def _texte_court(v: Any) -> Any:
    return v[:200] if isinstance(v, str) else v


def ajouter_routes_main_humaine(app: FastAPI, systeme: Any, protege: list) -> MainHumaine:
    main = MainHumaine(systeme)
    app.state.main_humaine = main  # pour le chef de démonstration (OperateurEcran) dans le même programme
    app.mount("/main_humaine", StaticFiles(directory=STATIQUE), name="main_humaine")

    @app.get("/api/main_humaine")
    async def etat(court: int = 0, x_jeton_main: Annotated[str | None, Header(max_length=64)] = None):
        return main.etat(court=bool(court), jeton=x_jeton_main)

    @app.post("/api/main_humaine/prendre", dependencies=protege)
    async def prendre(q: Qui):
        try:
            return await main.prendre(q.qui)
        except Refus as e:
            raise HTTPException(409, str(e))

    @app.post("/api/main_humaine/rendre", dependencies=protege)
    async def rendre(r: Rendu):
        try:
            return await main.rendre(r.jeton or None, r.qui or None, r.fait, forcer=r.forcer)
        except Refus as e:
            raise HTTPException(409, str(e))

    @app.post("/api/main_humaine/ordre", dependencies=protege)
    async def ordre(o: Ordre):
        try:
            return await main.ordre(o.nom, {k: _texte_court(v) for k, v in o.parametres.items()}, o.jeton or None,
                                    o.qui or None, o.langue or None)
        except Refus as e:
            raise HTTPException(409, str(e))

    return main
