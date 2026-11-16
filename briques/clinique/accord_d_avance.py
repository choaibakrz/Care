"""Un accord humain donné D'AVANCE pour quelques gestes d'un robot précis. Éteint par défaut.

NON TESTÉ SUR VRAI ROBOT (cette pièce) : testé sur faux robot.

Décision de Hiba du 15.11.2026, pour la main Leadtron DH116 : « personne ne s'approche de la main, il n'y aura que des
objets en contact avec elle » ; à la question « la main doit-elle bouger sans "oui" sur l'écran à chaque geste ? »,
elle a répondu : « Oui, sans accord ».

Ce que cette pièce fait, et rien d'autre :
- elle ne change AUCUNE règle du gardien. Le gardien continue de demander un humain (« je ne sais pas où sont les
  personnes », « ce geste n'est pas dans la carte de rôle »), et c'est écrit dans le journal comme d'habitude ;
- quand la chaîne a bien enregistré cette demande, la pièce y répond « oui » à la place de l'humain, par le chemin de
  tout le monde (la même réponse que le bouton « oui » de l'écran). Le gardien REVÉRIFIE alors tout, puis délivre le
  ticket ; la prise fait le reste. Le journal dit qui a répondu : « accord d'avance », avec le nom et la date ;
- seulement pour le robot nommé dans le réglage, seulement pour l'action « rejouer_geste », seulement pour les gestes
  listés, et seulement si TOUTES les raisons du gardien sont de celles qu'un accord d'avance peut couvrir (personnes ou
  position inconnues, geste hors de la carte de rôle). Une autre raison (objet fragile, personne trop près…) : la
  pièce ne répond pas, un humain décide.
- jamais pendant un arrêt d'urgence.

Le réglage (reglages.yaml, propre à chaque ordinateur) :
  interrupteurs:
    accord_d_avance: {actif: true, robot: leadtron-dh116, gestes: [preparer_la_main, …], qui: "Hiba (accord d'avance…)"}
"""
from __future__ import annotations

import asyncio
from typing import Any

RAISONS_COUVERTES = frozenset({"humain_requis", "personnes_inconnues", "position_inconnue"})


class AccordDAvance:
    def __init__(self, bus: Any, chaine: Any, prise: Any, reglage: dict | None = None) -> None:
        reglage = reglage if isinstance(reglage, dict) else {}
        self.bus, self.chaine, self.prise = bus, chaine, prise
        self.robot = str(reglage.get("robot") or "")
        self.gestes = frozenset(str(g) for g in (reglage.get("gestes") or []) if isinstance(g, str))
        self.qui = str(reglage.get("qui") or "accord d'avance")
        # Allumé seulement si le réglage le dit ET nomme un robot et au moins un geste : jamais « pour tout ».
        self.actif = reglage.get("actif") is True and bool(self.robot) and bool(self.gestes)
        self.donnes = 0  # combien d'accords d'avance ont été donnés (pour la fiche de vérité et les essais)
        self._demandes: dict[str, bool] = {}  # numéro de demande → couverte par l'accord d'avance ?
        self._taches: set[asyncio.Task] = set()
        bus.abonner(self._sur_demande, "aide_demandee")
        bus.abonner(self._sur_main_levee, "reponse_dite")

    def _couverte(self, ev: Any) -> bool:
        d = ev.donnees
        action = d.get("action") or {}
        codes = {str((r or {}).get("code")) for r in (d.get("raisons") or [])}
        return bool(self.actif and d.get("raison") == "gardien" and ev.robot == self.robot
                    and self.prise.carte().id == self.robot
                    and action.get("nom") == "rejouer_geste"
                    and (action.get("parametres") or {}).get("nom") in self.gestes
                    and codes and codes <= RAISONS_COUVERTES)

    def _sur_demande(self, ev: Any) -> None:
        """Le gardien demande un humain. On note seulement si la demande est de celles que l'accord d'avance couvre."""
        numero = ev.donnees.get("numero")
        if isinstance(numero, str):
            if len(self._demandes) > 200:
                self._demandes.clear()
            self._demandes[numero] = self._couverte(ev)

    def _sur_main_levee(self, ev: Any) -> None:
        """La chaîne vient de dire « je lève la main » : la demande est ENREGISTRÉE chez elle. C'est seulement là
        qu'on peut y répondre (répondre plus tôt ferait perdre la demande)."""
        if ev.donnees.get("genre") != "main_levee":
            return
        numero = ev.donnees.get("numero_demande")
        if not isinstance(numero, str) or not self._demandes.pop(numero, False):
            return
        if self.prise.arret_urgence_actif:
            return
        tache = asyncio.get_running_loop().create_task(self._repondre(numero))
        self._taches.add(tache)
        tache.add_done_callback(self._taches.discard)

    async def _repondre(self, numero: str) -> None:
        await asyncio.sleep(0)  # laisser la chaîne finir sa phrase : la réponse arrive après, comme celle d'un humain
        self.donnes += 1
        await self.bus.emettre("note", "accord_d_avance", robot=self.prise.robot,
                               texte=f"accord donné d'avance pour la demande {numero} : {self.qui}")
        await self.chaine.reponse_humaine(numero, True, qui=self.qui)

    async def attendre(self) -> None:
        """Pour les essais : attendre que les réponses en cours soient données."""
        while self._taches:
            await asyncio.gather(*list(self._taches), return_exceptions=True)
