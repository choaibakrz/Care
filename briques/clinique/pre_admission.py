"""L'assistant prépare, une personne valide : la pré-admission (avenant 4, tâche L04 ; première moitié : L04a).

« Votre assistant écrit-il dans le logiciel de la clinique ? » Jamais seul.

    pre = PreAdmissions(papiers, carnet, dossier_vers_le_logiciel, horloge, bus=bus)
    pre.faire_arriver()                         # le chef de démonstration : deux papiers inventés arrivent, « à trier »
    pre.preparer(badge_accueil)                 # la pré-admission déjà remplie, chaque champ avec son papier et sa confiance
    pre.corriger(badge_accueil, "PA-0001", "langue", "it")
    await pre.valider(badge_accueil, "PA-0001") # alors seulement, un message part dans « de nous vers le logiciel »

- Par des règles simples, sans modèle. Un champ que les papiers ne donnent pas, ou que deux papiers disent
  différemment, reste vide : « je ne suis pas sûr ».
- Aucune information médicale n'est reprise : ni le motif, ni le nom du médecin.
- La proposition vit dans le carnet. Seul le badge « accueil » prépare, corrige et valide. La validation écrit le
  badge et l'heure dans la boîte noire.
- C'est la SEULE chose qui part de notre système vers le faux logiciel : un fichier texte, après la validation d'une
  personne. Avant, rien ne part.

DIRE VRAI : SIMULÉ. Le message de pré-admission est fabriqué par nous au standard HL7 version 2.5 (A05) ; la place du
numéro de pré-admission (PV1-5), de la date d'arrivée prévue (PV2-8) et du numéro de carte (IN1-36) vient de ce que
nous savons du standard : à vérifier. Jamais essayé avec un vrai logiciel de clinique.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .carnet import Carnet
from .papiers import PAS_SUR, Papiers
from .porte import Badge
from .traducteur import JOUR_1, NOTRE_SYSTEME

GENRE = "pré-admission"
ETIQUETTE = "SIMULÉ"
SOURCE = "clinique"
PHRASE = "L'assistant prépare. Une personne décide."
FICHIER_PAPIERS = Path(__file__).resolve().parent / "papiers_pre_admission.yaml"
CHAMPS = ("nom", "prenom", "date_naissance", "langue", "assurance", "date_arrivee_prevue")
LANGUES = ("fr", "de", "it", "en", "pt")
DESTINATAIRE = "FAUX_LOGICIEL_ADMIN"
BADGE_DU_SUIVI = Badge(id="suivi-des-pre-admissions", role="assistant", libelle="Suivi des pré-admissions")


class Refus(ValueError):
    """Ce n'est pas possible maintenant. Le message dit pourquoi."""


def papiers_inventes() -> list[dict[str, Any]]:
    brut = yaml.safe_load(FICHIER_PAPIERS.read_text(encoding="utf-8"))
    if brut.get("marque") != "inventé":
        raise ValueError("papiers_pre_admission.yaml : la marque « inventé » manque")
    return [dict(p) for p in brut["papiers"]]


IDS_DES_PAPIERS = tuple(p["id"] for p in papiers_inventes())


def _date(texte: str) -> str:
    jour, mois, annee = texte.split(".")
    return f"{annee}-{int(mois):02d}-{int(jour):02d}"


def _lu(texte: str) -> dict[str, str]:
    """Ce qu'UN papier dit, par des règles simples. Jamais la ligne du motif, jamais le nom d'un médecin."""
    lu: dict[str, str] = {}
    personne = re.search(r"^Concerne : (?:Madame|Monsieur) (\S+) (\S+\.)\s*$", texte, re.MULTILINE)
    if personne:
        lu["prenom"], lu["nom"] = personne.group(1), personne.group(2)
    for champ, motif in (("nom", r"^Nom : (\S+)\s*$"), ("prenom", r"^Prénom : (\S+)\s*$")):
        trouve = re.search(motif, texte, re.MULTILINE)
        if trouve:
            lu[champ] = trouve.group(1)
    naissance = re.search(r"^Née? le (\d{1,2}\.\d{1,2}\.\d{4})\s*$", texte, re.MULTILINE)
    if naissance:
        lu["date_naissance"] = _date(naissance.group(1))
    arrivee = re.search(r"^Arrivée prévue le (\d{1,2}\.\d{1,2}\.\d{4})\.?\s*$", texte, re.MULTILINE)
    if arrivee:
        lu["date_arrivee_prevue"] = _date(arrivee.group(1))
    assurance = re.search(r"^(Assurance Exemple)\s*$", texte, re.MULTILINE)
    carte = re.search(r"^Numéro de carte : (EXEMPLE-\d{4})\s*$", texte, re.MULTILINE)
    if assurance and carte:
        lu["assurance"] = f"{assurance.group(1)} — {carte.group(1)}"
    langue = re.search(r"^Langue : (\w+)\s*$", texte, re.MULTILINE)
    if langue and langue.group(1) in LANGUES:
        lu["langue"] = langue.group(1)
    return lu


def proposer(papiers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Les champs de la pré-admission, chacun avec les papiers d'où il vient et un niveau de confiance."""
    lus = [(p["id"], _lu(p["texte"])) for p in papiers]
    champs: dict[str, dict[str, Any]] = {}
    for champ in CHAMPS:
        dits = [(ident, lu[champ]) for ident, lu in lus if champ in lu]
        valeurs = {valeur for _, valeur in dits}
        sources = [ident for ident, _ in dits]
        if len(valeurs) == 1:
            champs[champ] = {"valeur": valeurs.pop(), "sources": sources, "confiance": "haute" if len(dits) > 1 else "moyenne", "dit": ""}
        else:  # absent des papiers, ou deux papiers qui ne disent pas la même chose : on ne choisit pas
            champs[champ] = {"valeur": "", "sources": sources, "confiance": "", "dit": PAS_SUR}
    return champs


class PreAdmissions:
    def __init__(self, papiers: Papiers, carnet: Carnet, dossier: str | Path, horloge, bus=None) -> None:
        self.papiers, self.carnet, self.dossier, self.horloge, self.bus = papiers, carnet, Path(dossier), horloge, bus
        self._arrives = False

    # ------------------------------------------------------------------ les deux papiers
    def faire_arriver(self) -> list[str]:
        """Le bouton du chef de démonstration : les deux papiers inventés arrivent. Sans cela, rien ne change."""
        if not self._arrives:
            self.papiers.retires -= set(IDS_DES_PAPIERS)
            self.papiers.arrives += [{"id": p["id"], "texte": p["texte"], "langue": p.get("langue"),
                                      "ecriture": p.get("ecriture", "tapée")} for p in papiers_inventes()]
            self._arrives = True
        return list(IDS_DES_PAPIERS)

    def remettre_a_zero(self) -> None:
        """Retire les deux papiers de la pile. Le carnet garde ce qui s'est passé ; rien n'y est effacé."""
        self.papiers.arrives = [p for p in self.papiers.arrives if p["id"] not in IDS_DES_PAPIERS]
        self.papiers.retires |= set(IDS_DES_PAPIERS)
        self._arrives = False

    # ------------------------------------------------------------------ lire
    def _accueil(self, badge: Badge, quoi: str) -> None:
        if badge.role != "accueil":
            self.papiers.porte.refuser(badge, quoi, "la pré-admission se prépare et se valide à l'accueil, par une personne")

    def _etats(self) -> dict[str, dict[str, Any]]:
        # on ne croit que les lignes de l'accueil ; seule la marque « admise » vient du système (elle ne décide rien)
        return {l["donnees"]["numero"]: dict(l["donnees"]) for l in self.carnet.lignes(GENRE)
                if l["role"] == "accueil" or (l["qui"] == BADGE_DU_SUIVI.id and l["donnees"].get("etat") == "admise")}

    def marquer_les_admises(self, lecteur) -> list[str]:
        """La boucle fermée : quand le traducteur a lu l'admission qui porte le numéro d'une pré-admission validée, le
        carnet marque la proposition « admise ». Rend les numéros qui viennent de l'être."""
        admises = lecteur.par_pre_admission()
        faites = []
        for numero, proposition in self._etats().items():
            if proposition["etat"] == "validée" and numero in admises:
                proposition.update(etat="admise", admise=admises[numero])
                self.carnet.ecrire(BADGE_DU_SUIVI, GENRE, proposition, valide_par_un_humain=False)
                faites.append(numero)
        return faites

    def propositions(self, badge: Badge) -> list[dict[str, Any]]:
        self._accueil(badge, "pré-admissions")
        return list(self._etats().values())

    def _une(self, numero: str) -> dict[str, Any]:
        etats = self._etats()
        if numero not in etats:
            raise Refus(f"pré-admission inconnue « {numero} »")
        if etats[numero]["etat"] != "proposée":
            raise Refus(f"cette pré-admission est déjà {etats[numero]['etat']} : elle ne change plus")
        return etats[numero]

    # ------------------------------------------------------------------ préparer, corriger
    def preparer(self, badge: Badge) -> dict[str, Any]:
        """La pré-admission déjà remplie, à partir des deux papiers. Elle va au carnet. Rien ne part."""
        self._accueil(badge, "préparer une pré-admission")
        if not self._arrives:
            raise Refus("les deux papiers ne sont pas arrivés : il n'y a rien à préparer")
        numero = f"PA-{len(self._etats()) + 1:04d}"
        proposition = {"numero": numero, "etat": "proposée", "champs": proposer(papiers_inventes()), "papiers": list(IDS_DES_PAPIERS),
                       "phrase": PHRASE, "version": "règles simples, sans modèle", "etiquette": ETIQUETTE}
        return self.carnet.ecrire(badge, GENRE, proposition, valide_par_un_humain=False)["donnees"]

    def corriger(self, badge: Badge, numero: str, champ: str, valeur: str) -> dict[str, Any]:
        self._accueil(badge, "corriger une pré-admission")
        proposition = self._une(numero)
        if champ not in CHAMPS:
            raise Refus(f"champ inconnu « {champ} » (champs : {', '.join(CHAMPS)})")
        valeur = " ".join(str(valeur or "").split())[:80]
        if champ == "langue" and valeur and valeur not in LANGUES:
            raise Refus(f"langue inconnue « {valeur} » (langues : {', '.join(LANGUES)})")
        if champ in ("date_naissance", "date_arrivee_prevue") and valeur and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valeur):
            raise Refus("une date s'écrit AAAA-MM-JJ")
        proposition["champs"][champ] = ({"valeur": valeur, "sources": [f"corrigé par {badge.id}"], "confiance": "humain", "dit": ""}
                                        if valeur else {"valeur": "", "sources": [f"vidé par {badge.id}"], "confiance": "", "dit": PAS_SUR})
        return self.carnet.ecrire(badge, GENRE, proposition, valide_par_un_humain=False)["donnees"]

    # ------------------------------------------------------------------ valider : alors seulement, le message part
    async def valider(self, badge: Badge, numero: str) -> dict[str, Any]:
        self._accueil(badge, "valider une pré-admission")
        proposition = self._une(numero)
        valeurs = {c: proposition["champs"][c]["valeur"] for c in CHAMPS}
        if not valeurs["nom"] or not valeurs["prenom"]:
            raise Refus("il faut au moins le nom et le prénom pour envoyer une pré-admission")
        self.dossier.mkdir(parents=True, exist_ok=True)
        rang = len(list(self.dossier.glob("*.hl7"))) + 1
        fichier = self.dossier / f"{rang:04d}_A05_{numero}.hl7"
        fichier.write_text(self._message(numero, valeurs, rang), encoding="utf-8")
        etat = self.horloge.etat()
        proposition.update(etat="validée", fichier=fichier.name,
                           valide={"par": badge.id, "quand": {"jour": etat["jour"], "heure": etat["heure"]}})
        ligne = self.carnet.ecrire(badge, GENRE, proposition, valide_par_un_humain=True)["donnees"]
        if self.bus is not None:  # la boîte noire : le badge de la personne qui a validé, et l'heure ; pas de nom
            await self.bus.emettre("note", SOURCE, quoi="pre_admission_validee", etiquette=ETIQUETTE, numero=numero,
                                   badge=badge.id, heure=f"jour {etat['jour']}, {etat['heure']}", fichier=fichier.name)
        return ligne

    def _message(self, numero: str, v: dict[str, str], rang: int) -> str:
        def segment(nom: str, champs: dict[int, str], longueur: int) -> str:
            return "|".join([nom] + [champs.get(n, "") for n in range(1, longueur + 1)])

        etat = self.horloge.etat()
        from datetime import timedelta
        quand = (JOUR_1 + timedelta(days=int(etat["jour"]) - 1)).strftime("%Y%m%d") + str(etat["heure"]).replace(":", "")
        assurance, _, carte = v["assurance"].partition(" — ")
        msh = "|".join(["MSH", "^~\\&", NOTRE_SYSTEME, "CLINIQUE_EXEMPLE", DESTINATAIRE, "CLINIQUE_EXEMPLE", quand, "", "ADT^A05",
                        f"{NOTRE_SYSTEME}-{rang:06d}", "P", "2.5"])
        lignes = [msh, segment("EVN", {1: "A05", 2: quand}, 2),
                  segment("PID", {1: "1", 5: f"{v['nom']}^{v['prenom']}", 7: v["date_naissance"].replace("-", ""), 15: v["langue"]}, 15),
                  segment("PV1", {1: "1", 2: "P", 5: numero}, 5),
                  segment("PV2", {8: v["date_arrivee_prevue"].replace("-", "")}, 8)]
        if assurance:
            lignes.append(segment("IN1", {1: "1", 2: "EXEMPLE", 3: "EXEMPLE", 4: assurance, 36: carte}, 36))
        return "\n".join(lignes) + "\n"
