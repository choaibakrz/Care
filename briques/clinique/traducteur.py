"""Le traducteur : lire les messages du faux logiciel administratif, tenir la vue administrative (avenant 4, L03a).

« J'admets un patient. Votre robot le sait-il ? » Le traducteur lit le dossier « du logiciel vers nous » (un fichier
texte par message) et tient à jour la vue administrative : les personnes arrivées par message, leur chambre, leurs
dates, leur état (attendu, présent, en congé, sorti).

    lecteur = Traducteur(dossier)
    lecteur.lire()            # lit ce qui est nouveau ; rend {"lus", "a_trier", "deja_lus", "de_nous"}
    lecteur.vue()             # les personnes ; lecteur.presents() : celles qui sont là
    lecteur.a_trier()         # les messages illisibles, avec leur heure et la raison

Sept règles de lecture :
1. un message se relie par les numéros (patient et séjour), jamais par le nom ;
2. un message lu deux fois ne compte qu'une fois, grâce à son numéro unique ;
3. des messages arrivés dans le désordre sont remis en ordre par leur heure, puis par leur numéro ;
4. une annulation défait l'événement ;
5. un message illisible va dans « messages à trier », et rien ne s'arrête ;
6. une ligne inconnue est ignorée ;
7. un message créé par notre propre système n'est pas lu comme une nouveauté.

Ce programme LIT seulement : il n'écrit rien dans le faux logiciel, ni ailleurs. La vue est refaite à partir des messages
gardés : elle ne dépend pas de l'ordre d'arrivée.
DIRE VRAI : SIMULÉ. Les messages sont fabriqués par notre faux logiciel ; jamais essayé avec un vrai logiciel de
clinique. Une personne arrivée par message n'a que des données administratives (ADMIN) : rien de médical.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

ETIQUETTE = "SIMULÉ"
_comptes_ouverts: list[dict[str, int]] = []


@contextmanager
def compter():
    """Le temps d'une répétition : combien de messages lus, combien à trier, par tous les traducteurs (pour la fiche de vérité)."""
    compte = {"lus": 0, "a_trier": 0}
    _comptes_ouverts.append(compte)
    try:
        yield compte
    finally:
        _comptes_ouverts.remove(compte)
SOURCE = "clinique"
NOTRE_SYSTEME = "CLINIQUE_EN_BOITE"
JOUR_1 = date(2026, 11, 14)  # la convention du faux logiciel : le jour 1 de l'horloge de démonstration (inventé)
SORTES = ("A05", "A01", "A02", "A03", "A08", "A11", "A13", "A21", "A22")


class Illisible(ValueError):
    """Ce message ne se lit pas. Le texte dit pourquoi."""


def _quand(ts: str) -> dict[str, Any] | None:
    """« 202611140910 » → la date, le jour de l'horloge de démonstration, l'heure. None si c'est vide."""
    if not ts:
        return None
    try:
        moment = datetime.strptime(ts[:12].ljust(12, "0"), "%Y%m%d%H%M")
    except ValueError:
        raise Illisible(f"heure illisible « {ts} »") from None
    return {"date": moment.date().isoformat(), "jour": (moment.date() - JOUR_1).days + 1, "heure": moment.strftime("%H:%M")}


def _champ(segment: list[str], numero: int) -> str:
    return segment[numero] if len(segment) > numero else ""


def dechiffrer(texte: str) -> dict[str, Any]:
    """Un message → ce qu'il dit. Les lignes inconnues sont ignorées. Lève `Illisible` avec la raison."""
    segments: dict[str, list[str]] = {}
    for ligne in texte.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        nom = ligne.split("|", 1)[0].strip()
        if nom in ("MSH", "EVN", "PID", "PV1", "IN1") and nom not in segments:
            segments[nom] = ligne.split("|")
    for nom in ("MSH", "PID", "PV1"):
        if nom not in segments:
            raise Illisible(f"il manque la ligne {nom}")
    msh, pid, pv1 = segments["MSH"], segments["PID"], segments["PV1"]
    sorte = (_champ(msh, 8).split("^") + [""])[1]
    if sorte not in SORTES:
        raise Illisible(f"sorte de message inconnue « {_champ(msh, 8)} »")
    numero_unique, heure = _champ(msh, 9), _champ(msh, 6)
    if not numero_unique or not heure:
        raise Illisible("il manque le numéro unique ou l'heure du message")
    patient, sejour = _champ(pid, 3).split("^")[0], _champ(pv1, 19)
    if not patient:
        raise Illisible("il manque le numéro du patient")
    if not sejour:
        raise Illisible("il manque le numéro du séjour")
    nom = (_champ(pid, 5).split("^") + [""] * 5)[:5]  # famille, prénom, …, civilité
    naissance = _champ(pid, 7)
    return {"sorte": sorte, "numero_unique": numero_unique, "ts": heure[:12], "quand": _quand(heure), "systeme": _champ(msh, 2),
            "numero_patient": patient, "numero_sejour": sejour, "prenom": nom[1],
            "nom": " ".join(m for m in (nom[4], nom[1], nom[0]) if m),
            "date_naissance": f"{naissance[:4]}-{naissance[4:6]}-{naissance[6:8]}" if len(naissance) >= 8 else "",
            "langue": _champ(pid, 15), "chambre": (_champ(pv1, 3).split("^") + [""])[1],
            "entree": _quand(_champ(pv1, 44)), "sortie": _quand(_champ(pv1, 45)),
            "assurance": _champ(segments["IN1"], 4) if "IN1" in segments else "", "pre_admission": _champ(pv1, 5)}


class Traducteur:
    def __init__(self, dossier: str | Path, montre: Callable[[], float] = time.time) -> None:
        self.dossier, self.montre = Path(dossier), montre
        self._vus: set[str] = set()  # les fichiers déjà regardés
        self._messages: dict[str, dict[str, Any]] = {}  # numéro unique → le message gardé
        self._a_trier: list[dict[str, Any]] = []
        self._journal: list[dict[str, Any]] = []  # tout ce qui a été lu, pour la boîte noire
        self._dernier_delai: float | None = None
        self._de_nous = 0

    # ------------------------------------------------------------------ lire
    def lire(self) -> dict[str, int]:
        """Lit les fichiers nouveaux du dossier. Rend ce qui vient d'arriver."""
        bilan = {"lus": 0, "a_trier": 0, "deja_lus": 0, "de_nous": 0}
        fichiers = sorted(self.dossier.glob("*.hl7")) if self.dossier.exists() else []
        if self._vus - {f.name for f in fichiers}:  # des messages déjà lus ont disparu (remise à zéro) : on relit tout
            dossier, montre = self.dossier, self.montre
            self.__init__(dossier, montre)
        for fichier in fichiers:
            if fichier.name in self._vus:
                continue
            self._vus.add(fichier.name)
            maintenant = self.montre()
            note = {"fichier": fichier.name, "etiquette": ETIQUETTE, "lu_a": datetime.fromtimestamp(maintenant).isoformat(timespec="seconds")}
            try:
                try:
                    texte = fichier.read_bytes().decode("utf-8")
                except (OSError, UnicodeDecodeError) as erreur:
                    raise Illisible(f"fichier illisible ({type(erreur).__name__})") from None
                message = dechiffrer(texte)
            except Illisible as raison:  # un message illisible n'arrête rien
                self._a_trier.append({"fichier": fichier.name, "heure": note["lu_a"], "raison": str(raison)})
                self._journal.append({**note, "issue": "à trier", "raison": str(raison)})
                bilan["a_trier"] += 1
                continue
            note.update(sorte=message["sorte"], numero_patient=message["numero_patient"], numero_sejour=message["numero_sejour"])
            if message["systeme"] == NOTRE_SYSTEME:  # créé par nous : pas une nouveauté
                self._de_nous += 1
                self._journal.append({**note, "issue": "de nous"})
                bilan["de_nous"] += 1
            elif message["numero_unique"] in self._messages:  # le même message, une deuxième fois
                self._journal.append({**note, "issue": "déjà lu"})
                bilan["deja_lus"] += 1
            else:
                self._messages[message["numero_unique"]] = message
                self._dernier_delai = max(0.0, maintenant - fichier.stat().st_mtime)
                self._journal.append({**note, "issue": "lu", "delai_s": round(self._dernier_delai, 2)})
                bilan["lus"] += 1
        for compte in _comptes_ouverts:  # T27 : la fiche de vérité compte ce qui est lu pendant une répétition
            compte["lus"] += bilan["lus"]
            compte["a_trier"] += bilan["a_trier"]
        return bilan

    def _en_ordre(self) -> list[dict[str, Any]]:
        return sorted(self._messages.values(), key=lambda m: (m["ts"], m["numero_unique"]))

    # ------------------------------------------------------------------ la vue
    def vue(self) -> list[dict[str, Any]]:
        """La vue administrative, refaite à partir des messages gardés, remis en ordre par leur heure puis leur numéro."""
        personnes: dict[tuple[str, str], dict[str, Any]] = {}
        for m in self._en_ordre():
            cle = (m["numero_patient"], m["numero_sejour"])  # par les numéros, jamais par le nom
            p = personnes.get(cle)
            if p is None:
                p = personnes[cle] = {"numero_patient": cle[0], "numero_sejour": cle[1], "chambre": "", "etat": "attendu",
                                      "entree": None, "sortie": None, "source": "ADMIN", "_pre_admis": False}
            p.update(nom=m["nom"], prenom=m["prenom"], langue=m["langue"], date_naissance=m["date_naissance"],
                     assurance=m["assurance"])
            if m["pre_admission"]:
                p["_pre_admission"] = m["pre_admission"]
            sorte = m["sorte"]
            if sorte == "A05":
                p.update(etat="attendu", chambre="", _pre_admis=True)
            elif sorte in ("A01", "A02", "A13", "A22"):  # admis, déplacé, sortie annulée, revenu : la personne est là
                p.update(etat="présent", chambre=m["chambre"] or p["chambre"], entree=m["entree"] or p["entree"], sortie=None)
            elif sorte == "A03":
                p.update(etat="sorti", sortie=m["sortie"] or m["quand"])
            elif sorte == "A21":
                p.update(etat="en congé")
            elif sorte == "A11":  # l'admission est défaite : de nouveau attendue si elle était pré-admise, sinon plus rien
                if p["_pre_admis"]:
                    p.update(etat="attendu", chambre="", entree=None, sortie=None)
                else:
                    del personnes[cle]
            # A08 : une correction ; les renseignements du message sont déjà pris ci-dessus
        self._par_pre_admission = {p["_pre_admission"]: {"numero_patient": p["numero_patient"], "numero_sejour": p["numero_sejour"],
                                                         "etat": p["etat"]} for p in personnes.values() if p.get("_pre_admission")}
        return [{c: v for c, v in p.items() if not c.startswith("_")} for p in personnes.values()]

    def par_pre_admission(self) -> dict[str, dict[str, str]]:
        """Numéro de pré-admission → la personne que le logiciel administratif a créée pour elle (L04 : la boucle fermée)."""
        self.vue()
        return dict(self._par_pre_admission)

    def presents(self) -> list[dict[str, Any]]:
        return [p for p in self.vue() if p["etat"] == "présent"]

    def a_trier(self) -> list[dict[str, Any]]:
        """Les messages à trier (illisibles), avec l'heure où ils ont été mis de côté. Pas la liste « à trier » des papiers."""
        return sorted(self._a_trier, key=lambda m: m["fichier"])

    def derniere_nouvelle(self) -> dict[str, Any] | None:
        """L'heure de la dernière nouvelle reçue (l'heure écrite dans le message). None : aucune nouvelle."""
        en_ordre = self._en_ordre()
        return dict(en_ordre[-1]["quand"], sorte=en_ordre[-1]["sorte"]) if en_ordre else None

    def dernier_delai_s(self) -> float | None:
        """Les secondes entre l'écriture du dernier message lu et sa lecture. None : rien de lu."""
        return self._dernier_delai

    def texte_du_delai(self) -> str:
        if self._dernier_delai is None:
            return f"aucun message lu [{ETIQUETTE}]"
        return f"dernier message lu en {self._dernier_delai:.1f} secondes [{ETIQUETTE}]".replace(".", ",", 1)

    def compte(self) -> dict[str, Any]:
        lus, a_trier = len(self._messages), len(self._a_trier)
        return {"lus": lus, "a_trier": a_trier, "de_nous": self._de_nous,
                "texte": f"logiciel administratif : {ETIQUETTE} ; messages lus : {lus} ; messages à trier : {a_trier}"}

    # ------------------------------------------------------------------ la boîte noire
    async def noter_dans_la_boite(self, bus) -> int:
        """Écrit dans la boîte noire chaque message lu qui n'y est pas encore (des numéros, jamais un nom). Rend leur nombre."""
        a_ecrire = [n for n in self._journal if not n.get("dans_la_boite")]
        for note in a_ecrire:
            note["dans_la_boite"] = True
            await bus.emettre("note", SOURCE, quoi="message_lu", **{c: v for c, v in note.items() if c != "dans_la_boite"})
        return len(a_ecrire)
