"""Brique 6 — La cascade : Apertus 8B d'abord, Apertus 4B en secours, cerveau à règles en dernier recours.

- Chaque cerveau a un délai. Trop lent, éteint, ou réponse hors formulaire : on passe au suivant, et c'est noté
  dans la boîte noire (événement `cerveau_secours`).
- Un cerveau qui vient d'échouer est mis de côté un moment (pour ne pas payer son délai à chaque phrase),
  puis réessayé.
- Le dernier (à règles) ne dépend de rien : il répond toujours.
- Un cerveau de secours peut être démarré à la demande (`au_besoin`), pour ne pas occuper la mémoire tant qu'il ne sert pas.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from briques.b01_prise.carte import CarteIdentite
from commun.bus import Bus
from commun.monde import Monde

from ..prise_cerveau import Cerveau, Decision

log = logging.getLogger("cerveau")


@dataclass
class Etage:
    cerveau: Cerveau
    delai_s: float = 6.0
    pause_apres_echec_s: float = 30.0
    serveur: object | None = None  # le serveur de CE cerveau sur cet ordinateur (briques/b06_cerveau/serveurs.py)
    demarrage: str = "jamais"  # toujours / au_besoin / jamais
    echecs: int = 0
    en_pause_jusqua: float = 0.0
    reussites: int = 0
    temps_ms: list[float] = field(default_factory=list)


class CerveauCascade(Cerveau):
    def __init__(self, etages: list[Etage], bus: Bus | None = None) -> None:
        if not etages:
            raise ValueError("cascade vide")
        self.etages = etages
        self.bus = bus
        self.nom = " > ".join(e.cerveau.nom for e in etages)
        self._taches: set[asyncio.Task] = set()  # arrêts de secours en cours (jamais attendus avant de répondre)

    async def demarrer(self) -> None:
        for e in self.etages:
            await e.cerveau.demarrer()

    async def arreter(self) -> None:
        if self._taches:
            await asyncio.wait(set(self._taches), timeout=20)
        for e in self.etages:
            await e.cerveau.arreter()

    async def _note(self, **d) -> None:
        if self.bus:
            await self.bus.emettre("cerveau_secours", "cerveau", **d)

    async def _note_serveur(self, **d) -> None:
        """Un secours lancé ou arrêté : ce n'est PAS une panne (autre type d'événement que cerveau_secours)."""
        if self.bus:
            await self.bus.emettre("cerveau_serveur", "cerveau", **d)

    async def decider(self, texte: str, langue: str | None, carte: CarteIdentite, monde: Monde) -> Decision:
        from .llm import HorsFormulaire

        derniere_erreur = None
        for i, etage in enumerate(self.etages):
            dernier = i == len(self.etages) - 1
            if not dernier:
                if time.monotonic() < etage.en_pause_jusqua:
                    continue
                if etage.serveur is not None:
                    if etage.demarrage == "au_besoin" and not etage.serveur.tourne():
                        continue  # secours pas lancé (on ne le lance que si le cerveau d'avant TOMBE)
                    if await asyncio.to_thread(etage.serveur.en_chargement):
                        continue  # il se charge : ce n'est pas un échec, on passe sans le mettre de côté
            t0 = time.perf_counter()
            try:
                d = await asyncio.wait_for(etage.cerveau.decider(texte, langue, carte, monde),
                                           None if dernier else etage.delai_s)
                etage.echecs, etage.reussites = 0, etage.reussites + 1
                etage.temps_ms.append(round((time.perf_counter() - t0) * 1000, 1))
                d.cerveau = etage.cerveau.nom
                if any(e.serveur is not None and e.demarrage == "au_besoin" for e in self.etages[i + 1:]):
                    t = asyncio.create_task(self._eteindre_les_secours_apres(i))  # la réponse n'attend pas l'arrêt
                    self._taches.add(t)
                    t.add_done_callback(self._taches.discard)
                return d
            except Exception as e:  # trop lent, éteint, hors formulaire : au suivant
                if dernier:
                    raise
                derniere_erreur = e
                hors_formulaire = isinstance(e, HorsFormulaire)
                if not hors_formulaire:  # le modèle marche quand il répond hors formulaire : pas de mise de côté
                    etage.echecs += 1
                    etage.en_pause_jusqua = time.monotonic() + etage.pause_apres_echec_s
                raison = "trop lent" if isinstance(e, asyncio.TimeoutError) else f"{e.__class__.__name__}: {e}"[:160]
                log.warning("Cerveau %s : %s → suivant", etage.cerveau.nom, raison)
                await self._note(de=etage.cerveau.nom, vers=self.etages[i + 1].cerveau.nom, raison=raison,
                                 delai_s=etage.delai_s, attente_ms=round((time.perf_counter() - t0) * 1000),
                                 mis_de_cote=not hors_formulaire)
                if not hors_formulaire:
                    await self._lancer_le_secours_apres(i)
        raise RuntimeError(f"aucun cerveau n'a répondu ({derniere_erreur})")

    async def _lancer_le_secours_apres(self, i: int) -> None:
        """Le cerveau i est tombé : on lance le serveur « au besoin » suivant (s'il ne tourne pas déjà)."""
        for e in self.etages[i + 1:]:
            if e.serveur is not None and e.demarrage == "au_besoin":
                if not e.serveur.tourne():
                    try:
                        await asyncio.to_thread(e.serveur.lancer)
                        await self._note_serveur(de=self.etages[i].cerveau.nom, vers=e.cerveau.nom, quoi="lance",
                                                 raison="secours lancé au besoin")
                    except Exception:
                        log.exception("Lancement au besoin impossible")
                return

    async def _eteindre_les_secours_apres(self, i: int) -> None:
        """Le cerveau i répond : les secours lancés « au besoin » après lui sont arrêtés (mémoire rendue)."""
        for e in self.etages[i + 1:]:
            if e.serveur is not None and e.demarrage == "au_besoin" and e.serveur.tourne():
                try:
                    await asyncio.to_thread(e.serveur.eteindre)
                except Exception:
                    log.exception("Arrêt du secours impossible")
                    continue
                await self._note_serveur(de=e.cerveau.nom, vers=self.etages[i].cerveau.nom, quoi="arrete",
                                         raison="le cerveau principal répond : secours arrêté")
