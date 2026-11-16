"""Étape 4 — « la confiance » : les boutons de l'écran pour le gardien (brique 7) et la main levée (brique 8).

Dans un fichier à part, pour toucher le moins possible serveur.py (l'écran du jury se construit en même temps).
[protégé] = comme les autres boutons : sur l'ordinateur-cerveau, ou avec le code d'équipe (en-tête X-Code-Equipe).

- GET  /api/gardien/regles     les règles, en phrases (ouvert : tout le monde peut les lire)
- POST /api/gardien/regle      changer une règle en direct : {id, active?, valeurs?, qui}                 [protégé]
- POST /api/gardien/recharger  relire briques/b07_gardien/regles.yaml : {qui}                            [protégé]
                               (ce qui a été rendu plus strict en direct est gardé : réponse « gardees »)
- POST /api/gardien/vote       idée 9, le vote du public : {vote, resultats: {choix: voix}, qui}          [protégé]
- GET  /api/aides              la main levée : demandes qui attendent un humain, et mots appris
- POST /api/aide/repondre      accepter ou refuser une demande du gardien : {numero, accepte, qui}       [protégé]
- POST /api/aide/apprendre     « quand on dit X, cela veut dire Y » : {mot, langue, sens, qui}            [protégé]

`qui` est écrit dans la boîte noire. Il n'est pas vérifié : c'est un prénom ou un rôle, pas un mot de passe.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from briques.b07_gardien.regles import ReglesInvalides
from briques.b07_gardien.vote import appliquer_vote

Court = Annotated[str, Field(max_length=40)]


class ChangementRegle(BaseModel):
    id: Court
    active: bool | None = None
    valeurs: dict[str, Any] | None = None
    qui: Court = "écran"


class Rechargement(BaseModel):
    qui: Court = "écran"


class ResultatVote(BaseModel):
    vote: Court
    resultats: dict[str, int]
    qui: Court = "vote du public"


class ReponseHumaine(BaseModel):
    numero: Court
    accepte: bool
    qui: Court = "écran"


class MotAApprendre(BaseModel):
    mot: Court
    langue: Annotated[str, Field(max_length=5)]
    sens: Court
    qui: Court = "écran"


def ajouter_routes_confiance(app: FastAPI, systeme, protege: list) -> None:
    @app.get("/api/gardien/regles")
    async def regles():
        return {"regles": systeme.gardien.regles_lisibles(), "plafonds": systeme.gardien.plafonds(),
                "votes": [v.model_dump() for v in systeme.gardien.regles.votes]}

    @app.post("/api/gardien/regle", dependencies=protege)
    async def changer_regle(c: ChangementRegle):
        try:
            r = await systeme.gardien.changer_regle(c.id, active=c.active, valeurs=c.valeurs, qui=c.qui)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "regle": r.lisible()}

    @app.post("/api/gardien/recharger", dependencies=protege)
    async def recharger(c: Rechargement):
        try:
            res = await systeme.gardien.recharger(qui=c.qui)
        except ReglesInvalides as e:  # le fichier est faux : les règles d'avant restent en place
            raise HTTPException(400, {"erreur": "regles.yaml à corriger ; les règles d'avant restent en place",
                                      "problemes": e.problemes})
        # « gardees » : ce qui avait été rendu plus strict en direct reste en place (jamais annulé en silence).
        message = "fichier relu" if not res["gardees"] else (
            "fichier relu ; ATTENTION : des changements faits en direct, plus stricts que le fichier, sont gardés "
            "(voir « gardees ») ; pour revenir au fichier tel quel : redémarrer le programme")
        return {"ok": True, **res, "message": message}

    @app.post("/api/gardien/vote", dependencies=protege)
    async def vote(v: ResultatVote):
        interrupteur = (systeme.reglages.get("interrupteurs") or {}).get("vote_public") or {}
        if not interrupteur.get("actif", False):
            raise HTTPException(400, "Le vote du public est éteint (reglages.yaml → interrupteurs → vote_public).")
        try:
            return {"ok": True, **await appliquer_vote(systeme.gardien, v.vote, v.resultats, qui=v.qui)}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/aides")
    async def aides():
        return {"en_attente": systeme.gardien.demandes_en_attente(), "mots_appris": systeme.doute.aides.liste()}

    @app.post("/api/aide/repondre", dependencies=protege)
    async def repondre(r: ReponseHumaine):
        res = await systeme.chaine.reponse_humaine(r.numero, r.accepte, qui=r.qui)
        return {"ok": res is not None, "resultat": res.model_dump() if res else None}

    @app.post("/api/aide/apprendre", dependencies=protege)
    async def apprendre(m: MotAApprendre):
        try:
            return {"ok": True, "mot": await systeme.doute.apprendre(m.mot, m.langue, m.sens, qui=m.qui)}
        except ValueError as e:
            raise HTTPException(400, str(e))
