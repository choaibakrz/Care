"""Brique 4 — La conversation à voix haute.

micro → fin de parole → écoute (texte + langue + confiance) → chaîne (cerveau, gardien, robot) → voix → haut-parleur

- Trois façons de commencer : « toujours » (le robot écoute tout), « mot_d_appel » (il faut dire « robot »…),
  « bouton » (on appuie sur « je parle », utile dans une halle bruyante). Le bouton marche dans tous les modes.
- Interruption : si la personne parle pendant que le robot parle, le robot se tait et écoute.
- Temps de réponse : mesuré entre la fin réelle de la phrase et le début du son de la réponse (événement `voix_debut`).
- « Stop » passe toujours, dans tous les modes, même sans mot d'appel ni bouton.
- Les phrases sont traitées dans l'ordre où elles ont été dites ; un « stop » annule les phrases plus anciennes
  pas encore traitées.
- Écho : le robot ignore ce qui ressemble à ce qu'il vient de dire (sinon il pourrait se répondre « oui » à lui-même).
- La réponse vient dans la langue de la personne (en allemand pour le suisse allemand, et le robot le dit).
"""
from __future__ import annotations

import asyncio
import difflib
import re
import time
import uuid
from collections import deque

import numpy as np

from commun.evenements import Evenement
from commun.phrases import dire, est_ordre_arret, langue_de_reponse
from commun.systeme import Systeme

from .ecoute import Ecoute
from .fin_de_parole import DetecteurParole, Enonce
from .peripheriques import HautParleur, Micro
from .voix import Voix


class Conversation:
    def __init__(self, systeme: Systeme, ecoute: Ecoute, voix: Voix, haut_parleur: HautParleur,
                 reglages_voix: dict | None = None, vitesse_micro: float = 1.0) -> None:
        r = reglages_voix or systeme.reglages.get("voix", {})
        self.s, self.ecoute, self.voix, self.hp = systeme, ecoute, voix, haut_parleur
        self.mode = r.get("declenchement", "toujours")
        self.mots_d_appel = [m.lower() for m in r.get("mots_d_appel", ["robot"])]
        self.fenetre_s = float(r.get("fenetre_apres_appel_s", 20))
        self.interruption_ms = float(r.get("interruption_ms", 300))
        self.interruption_active = bool(r.get("interruption", True))
        self.lent = bool(r.get("lent", False))
        self.langue_forcee: str | None = r.get("langue_forcee") or None
        self.garder_langue_s = float(r.get("garder_langue_s", 30))  # 0 : reconnaître la langue à chaque phrase
        self.detecteur = DetecteurParole(silence_fin_ms=int(r.get("silence_fin_ms", 600)))
        self.vitesse_micro = vitesse_micro
        self._ouverte_jusqua = 0.0
        self._bouton = False
        self._tampon_bouton: list[np.ndarray] = []
        self._fin_parole: dict[str, float] = {}
        self._a_dire: asyncio.Queue = asyncio.Queue()
        self._taches: set[asyncio.Task] = set()
        self._parleur: asyncio.Task | None = None
        self._derniere_langue: tuple[str, float] | None = None  # (langue, quand) de la dernière phrase comprise
        self.duree_max_bouton_s = float(r.get("duree_max_bouton_s", 15))
        self._appui_depuis = 0.0
        self._seq = 0  # numéro de chaque phrase, dans l'ordre où elle a été dite
        self._finies: dict[int, asyncio.Event] = {}
        self._dernier_stop = 0
        self._dits: deque = deque(maxlen=10)  # (texte normalisé, quand) : ce que le robot a dit récemment
        self._parle_debut: float | None = None
        self.transcriptions: list = []
        systeme.bus.abonner(self._reponse, "reponse_dite")

    # ---------------------------------------------------------------- entrées
    async def ecouter(self, micro: Micro) -> None:
        """Boucle principale : lit le micro jusqu'à la fin (ou pour toujours avec le vrai micro)."""
        async for morceau in micro.morceaux():
            await self.recevoir(morceau)
        await self.attendre_calme()

    async def prechauffer(self) -> None:
        """Charger l'écoute et la voix avant la première phrase (appelé au démarrage)."""
        await asyncio.to_thread(self.ecoute.prechauffer)
        if hasattr(self.voix, "prechauffer"):
            await asyncio.to_thread(self.voix.prechauffer)

    def _assurer_voix(self) -> None:
        """La boucle qui fait parler le robot tourne dès qu'on en a besoin."""
        if self._parleur is None or self._parleur.done():
            self._parleur = asyncio.create_task(self._boucle_voix(), name="boucle_voix")

    def fermer(self) -> None:
        if self._parleur:
            self._parleur.cancel()
        self.s.bus.desabonner(self._reponse)

    async def recevoir(self, morceau: np.ndarray) -> None:
        self._assurer_voix()
        if self._bouton:
            self._tampon_bouton.append(morceau)
            if time.monotonic() - self._appui_depuis > self.duree_max_bouton_s:
                # Bouton jamais relâché (écran tactile, réseau…) : on relâche nous-mêmes, le micro ne reste pas sourd.
                await self.s.bus.emettre("note", "oreilles", texte="bouton « je parle » relâché automatiquement")
                self.relacher()
            return
        finies = self.detecteur.ajouter(morceau)
        if self.interruption_active and self.hp.parle and self.detecteur.parle_depuis_ms >= self.interruption_ms:
            await self._interrompre()
        maintenant = time.monotonic()
        for e in finies:
            fin_reelle = maintenant - (e.detection_s - e.fin_parole_s) / self.vitesse_micro
            debut_reel = maintenant - (e.detection_s - e.debut_s) / self.vitesse_micro
            pendant_que_robot_parle = self._parle_debut is not None and debut_reel >= self._parle_debut - 0.2
            self._lancer(self._traiter(e, fin_reelle, ecouter_seulement_stop=pendant_que_robot_parle))

    def appuyer(self) -> None:
        """Bouton « je parle » appuyé : on enregistre tout jusqu'au relâchement."""
        self._bouton = True
        self._appui_depuis = time.monotonic()
        self._tampon_bouton = []
        self.hp.couper()

    def relacher(self) -> None:
        self._assurer_voix()
        self._bouton = False
        if self._tampon_bouton:
            son = np.concatenate(self._tampon_bouton)
            e = Enonce(son=son, debut_s=0.0, fin_parole_s=len(son) / 16000, detection_s=len(son) / 16000)
            self._ouverte_jusqua = time.monotonic() + self.fenetre_s  # le bouton vaut mot d'appel
            self._lancer(self._traiter(e, time.monotonic(), par_bouton=True))
        self._tampon_bouton = []

    async def attendre_calme(self, delai_max_s: float = 60.0) -> None:
        """Attendre que tout soit traité et dit (pour les tests et le banc d'essai)."""
        self._assurer_voix()
        fin = time.monotonic() + delai_max_s
        while time.monotonic() < fin:
            occupees = [t for t in self._taches if not t.done() and t.get_name() != "boucle_voix"]
            if not occupees and self._a_dire.empty() and not self.hp.parle:
                await asyncio.sleep(0.3)  # une réponse « c'est fait » peut encore arriver
                occupees = [t for t in self._taches if not t.done() and t.get_name() != "boucle_voix"]
                if not occupees and self._a_dire.empty() and not self.hp.parle:
                    return
            await asyncio.sleep(0.05)

    # ---------------------------------------------------------------- traitement
    async def _traiter(self, e: Enonce, fin_reelle: float, par_bouton: bool = False,
                       ecouter_seulement_stop: bool = False) -> None:
        self._seq += 1
        seq = self._seq
        self._finies[seq] = asyncio.Event()
        try:
            await self._traiter_dans_l_ordre(seq, e, fin_reelle, par_bouton, ecouter_seulement_stop)
        finally:
            self._finies[seq].set()
            self._finies.pop(seq - 5, None)

    async def _traiter_dans_l_ordre(self, seq: int, e: Enonce, fin_reelle: float, par_bouton: bool,
                                    ecouter_seulement_stop: bool) -> None:
        bus = self.s.bus
        await bus.emettre("parole_finie", "oreilles", duree_s=round(len(e.son) / 16000, 2),
                          attente_fin_ms=round((e.detection_s - e.fin_parole_s) * 1000), coupee=e.coupee, bouton=par_bouton)
        probable = None
        if self._derniere_langue and time.monotonic() - self._derniere_langue[1] < self.garder_langue_s:
            probable = self._derniere_langue[0]
        tr = await asyncio.to_thread(self.ecoute.transcrire, e.son, self.langue_forcee, probable)
        self.transcriptions.append(tr)
        await bus.emettre("transcription", "oreilles", texte=tr.texte, langue=tr.langue, langue_proba=tr.langue_proba,
                          confiance=tr.confiance, calcul_ms=tr.duree_calcul_ms, moteur=tr.moteur, langue_moteur=tr.langue_moteur,
                          langue_verifiee=tr.langue_verifiee)
        texte = tr.texte
        if not texte:
            return
        stop = est_ordre_arret(texte)
        if stop:
            # « Stop » : tout de suite, sans attendre les phrases d'avant, et il les annule.
            self._dernier_stop = max(self._dernier_stop, seq)
            await self._envoyer(texte, tr, fin_reelle)
            return
        # Sinon : attendre que les phrases dites avant soient traitées (l'ordre compte).
        precedente = self._finies.get(seq - 1)
        if precedente is not None:
            await precedente.wait()
        if seq < self._dernier_stop:
            await bus.emettre("note", "oreilles", texte=f"phrase annulée par un « stop » plus récent : {texte}")
            return
        if self._est_un_echo(texte) or ecouter_seulement_stop:
            await bus.emettre("note", "oreilles", texte=f"écho de la voix du robot ignoré : {texte}")
            return
        if tr.texte and tr.confiance >= 0.5:
            self._derniere_langue = (tr.langue, time.monotonic())
        if self.mode == "bouton" and not par_bouton:
            return  # mode bouton : on n'écoute que pendant l'appui (sauf « stop », traité plus haut)
        if self.mode == "mot_d_appel" and not par_bouton:
            if time.monotonic() > self._ouverte_jusqua:
                reste = self._apres_mot_d_appel(texte)
                if reste is None:
                    return  # on ignore ce qui n'est pas adressé au robot
                await bus.emettre("mot_d_appel", "oreilles", texte=texte, langue=tr.langue)
                self._ouverte_jusqua = time.monotonic() + self.fenetre_s
                if not reste:
                    conv = uuid.uuid4().hex[:10]
                    self._fin_parole[conv] = fin_reelle
                    await self.s.chaine.repondre(dire("je_vous_ecoute", tr.langue), tr.langue, conv, genre="ecoute",
                                                 cle="je_vous_ecoute")
                    return
                texte = reste
            self._ouverte_jusqua = time.monotonic() + self.fenetre_s
        await self._envoyer(texte, tr, fin_reelle)

    async def _envoyer(self, texte: str, tr, fin_reelle: float) -> None:
        conv = uuid.uuid4().hex[:10]
        self._fin_parole[conv] = fin_reelle
        await self.s.chaine.traiter(texte, tr.langue, confiance_ecoute=tr.confiance, source="micro",
                                    attendre_fin=False, conversation=conv)

    def _est_un_echo(self, texte: str) -> bool:
        """Ce que le micro entend ressemble-t-il à ce que le robot a dit dans les 10 dernières secondes ?"""
        t = re.sub(r"[^\w]", "", texte.lower())
        maintenant = time.monotonic()
        for dit, quand in self._dits:
            if maintenant - quand < 10 and t and difflib.SequenceMatcher(None, t, dit).ratio() >= 0.6:
                return True
        return False

    def _apres_mot_d_appel(self, texte: str) -> str | None:
        t = texte.lower()
        for mot in self.mots_d_appel:
            if re.search(r"[\u4e00-\u9fff]", mot):  # chinois : pas d'espaces entre les mots
                i = t.find(mot)
                if i >= 0:
                    return texte[i + len(mot):].strip(" ,.!?;:，。！？")
                continue
            m = re.search(rf"(^|\W){re.escape(mot)}(\W|$)", t)
            if m:
                return texte[m.end():].strip(" ,.!?;:，。！？")
        return None

    async def _interrompre(self) -> None:
        self._parle_debut = None  # la personne a pris la parole : ce qu'elle dit maintenant compte
        self.hp.couper()
        while not self._a_dire.empty():
            self._a_dire.get_nowait()
        await self.s.bus.emettre("interruption", "oreilles", parle_depuis_ms=round(self.detecteur.parle_depuis_ms))

    # ---------------------------------------------------------------- sortie : la voix
    def _reponse(self, ev: Evenement) -> None:
        self._a_dire.put_nowait((ev.donnees.get("texte", ""), ev.donnees.get("langue_entendue") or ev.donnees.get("langue"),
                                 ev.conversation))

    async def _boucle_voix(self) -> None:
        while True:
            texte, langue, conv = await self._a_dire.get()
            son = await asyncio.to_thread(self.voix.synthetiser, texte, langue_de_reponse(langue), self.lent)
            maintenant = time.monotonic()
            self._dits.append((re.sub(r"[^\w]", "", texte.lower()), maintenant + (son.duree_s if son else 0)))
            fin = self._fin_parole.pop(conv, None) if conv else None
            await self.s.bus.emettre(
                "voix_debut", "voix", conversation=conv, texte=texte, langue=langue_de_reponse(langue),
                latence_ms=round((maintenant - fin) * 1000) if fin else None,
                calcul_voix_ms=son.duree_calcul_ms if son else None, moteur=son.moteur if son else "texte (écran seulement)",
                sous_titres_seulement=son is None)
            if son is not None and len(son.echantillons):
                self._parle_debut = time.monotonic()
                try:
                    complet = await self.hp.jouer(son.echantillons, son.taux)
                finally:
                    self._parle_debut = None
                if not complet:
                    await self.s.bus.emettre("note", "voix", texte="réponse coupée par une interruption", conversation=conv)

    def _lancer(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._taches.add(t)
        t.add_done_callback(self._taches.discard)
        return t
