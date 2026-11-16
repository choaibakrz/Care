"""Les papiers, version simple : du texte déjà tapé à une proposition de rangement, validée par un humain
(cahier 5.8 et 6.4, tâche T09).

    papiers = Papiers(porte, carnet)
    papiers.pile(badge_accueil)                 # à valider, à trier, validés ; chaque papier avec sa proposition
    papiers.valider(badge_accueil, "p01-d1")    # un doigt : la proposition validée va au carnet
    proposer(texte, "tapée", patients)          # la règle seule : le texte, rien d'autre

- La proposition dit : le type, la date, l'auteur, le patient, l'endroit du dossier, et un niveau de confiance.
  Elle se fait à partir du TEXTE du papier, et de son écriture (tapée, ou à la main : ce que la lecture d'une image
  dira avec T15 ; aujourd'hui c'est noté dans le faux dossier). Ni le genre, ni le titre, ni l'identifiant ne servent.
- Confiance « haute » seulement si : un seul patient, un seul type reconnu par deux mots au moins, un texte tapé.
- Confiance basse : « je ne suis pas sûr », et l'humain choisit le type.
- Aucun patient ne correspond : on ne range pas. Le papier attend dans « à trier ».
- Rien n'entre au faux dossier. Proposition et validation sont des lignes du carnet ; la validation est marquée
  « validée par (badge), à (heure) ».
- Les papiers du jour : ceux des personnes qui arrivent aujourd'hui (ce que la porte montre à l'accueil), plus les
  feuilles sans nom. Le texte de référence tient lieu de papier lu : la lecture d'une image viendra avec T15.
  Un papier déjà vu reste dans la pile les jours suivants : il attend (son texte est gardé dans le carnet).
- L'accueil ne voit aucune ligne d'un papier (H01, réponse de Hiba à Q18) : le genre proposé, la date, l'auteur, le
  patient. Cette pièce lit le texte par la porte avec son propre badge (l'assistant, au service de l'accueil).
- Par des règles simples, sans modèle. Le cerveau viendra avec T14. Rien de médical : on range, on ne lit pas un soin.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .carnet import Carnet
from .listes import ChoixRefuse
from .porte import Badge, PorteDeLecture, charger_badges

GENRE = "rangement de papier"
MARQUE = "données inventées"
PAS_SUR = "je ne suis pas sûr"
PROPOSE, VALIDE, A_TRIER = "proposé", "validé", "à trier"
VERSION = "règles simples, sans modèle, à partir du texte de référence"

# Le type d'un papier → l'endroit du dossier où le ranger, et les mots qui le font reconnaître (sans accents).
# Mots français, allemands et italiens : écrits par l'agent, à relire par quelqu'un qui parle la langue.
TYPES: dict[str, dict[str, Any]] = {
    "lettre du médecin traitant": {"endroit": "Courrier médical",
                                   "mots": ("lettera", "medico curante", "studio medico", "brief", "hausarzt", "praxis",
                                            "lettre", "medecin traitant")},
    "liste de médicaments": {"endroit": "Médicaments",
                             "mots": ("medicinal", "medicament", "medikament", "elenco")},
    "carte d'assurance": {"endroit": "Assurance et administratif",
                          "mots": ("assurance", "assuree", "assicurazione", "versicherung")},
    "rapport de radiologie": {"endroit": "Imagerie", "mots": ("radiolog", "bericht", "bilder")},
    "ordonnance de physiothérapie": {"endroit": "Ordonnances", "mots": ("ordonnance", "physiotherap", "seances")},
    "formulaire d'admission": {"endroit": "Assurance et administratif",
                               "mots": ("formulaire", "admission", "aufnahmeformular")},
}
MOIS = ("janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|"
        "januar|februar|märz|maerz|april|juni|juli|august|september|oktober|november|dezember|"
        "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|dicembre")
DATE = re.compile(rf"\b\d{{1,2}}\.? (?:{MOIS})(?: \d{{4}})?\b|\b\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}}\b", re.IGNORECASE)


class PapierRefuse(ChoixRefuse):
    """Ce rangement n'est pas possible. Le message dit pourquoi, en mots simples."""


def _simple(texte: str) -> str:
    sans = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'"))
    return "".join(c for c in sans if unicodedata.category(c) != "Mn")


def proposer(texte: str, ecriture: str, patients: list[dict[str, Any]]) -> dict[str, Any]:
    """La proposition de rangement d'un papier, à partir de son texte. `patients` : les personnes possibles (id, nom).
    Rien n'est inventé : ce qui n'est pas dans le texte vaut None."""
    simple, raisons = _simple(texte), []

    trouves = []
    for p in patients:  # « Madame Giulia B. » : on cherche « Giulia B » dans le texte, sur une seule ligne
        morceaux = str(p["nom"]).split()
        if len(morceaux) < 3:
            continue  # pas de prénom ou pas d'initiale : on ne devine pas
        prenom, initiale = _simple(" ".join(morceaux[1:-1])), _simple(morceaux[-1].rstrip("."))
        if re.search(rf"(?<![\w-]){re.escape(prenom)}[ ]+{re.escape(initiale)}(?![\w-])", simple):
            trouves.append(p)
    patient = trouves[0] if len(trouves) == 1 else None
    if not trouves:
        raisons.append("aucun patient ne correspond")
    elif len(trouves) > 1:
        raisons.append("plusieurs patients correspondent")

    notes = sorted(((sum(bool(re.search(rf"\b{re.escape(mot)}", simple)) for mot in regle["mots"]), nom)
                    for nom, regle in TYPES.items()), reverse=True)
    (meilleure, nom_du_type), (seconde, _) = notes[0], notes[1]
    genre = nom_du_type if meilleure > 0 and meilleure > seconde else None
    if genre is None:
        raisons.append("le type du papier n'est pas reconnu" if meilleure == 0 else "deux types sont possibles")
    elif meilleure < 2:
        raisons.append("le type est reconnu par un seul mot")

    if _simple(ecriture) != "tapee":
        raisons.append(f"écriture : {ecriture}")

    date = DATE.search(texte)
    premiere = next((l.strip() for l in texte.splitlines() if l.strip()), "")
    premiere = re.sub(r"^INVENTÉ\s*—\s*", "", premiere)
    # tout nom de cabinet ou d'assurance contient « Exemple » ; une ligne qui nomme un patient n'est pas un auteur
    nomme = any(_simple(str(p["nom"]).split()[1]) in _simple(premiere) for p in patients if len(str(p["nom"]).split()) >= 3)
    auteur = premiere if "Exemple" in premiere and not nomme else None

    sur = patient is not None and genre is not None and meilleure >= 2 and _simple(ecriture) == "tapee"
    return {"type": genre, "date": date.group(0) if date else None, "auteur": auteur,
            "patient": patient["id"] if patient else None, "nom_du_patient": patient["nom"] if patient else None,
            "endroit": TYPES[genre]["endroit"] if genre and patient else None,
            "confiance": "haute" if sur else "basse", "dit": "" if sur else PAS_SUR, "raisons": raisons,
            "version": VERSION, "marque": MARQUE}


# ---------------------------------------------------------------------- le rangement proposé par le cerveau (T14)
class CerveauDeTest:
    """Un cerveau de test : il donne des réponses fixes (cahier 2.8). `repondre` : texte du papier → réponse.
    Il sert aux vérifications. Le vrai cerveau (Apertus) aura la même porte : `lire(texte, types, patients)`."""

    nom = "cerveau de test (réponses fixes)"

    def __init__(self, repondre) -> None:
        self._repondre = repondre

    def lire(self, texte: str, types: list[str], patients: list[str]) -> Any:
        return self._repondre(texte)


CHAMPS_DU_CERVEAU = ("type", "date", "auteur", "patient", "confiance")
NIVEAUX = ("haute", "moyenne", "basse")


def _reponse_lisible(reponse: Any) -> bool:
    """Le formulaire attendu : un type, une date, un auteur, un patient (du texte, ou rien), et un niveau de confiance."""
    if not isinstance(reponse, dict) or reponse.get("confiance") not in NIVEAUX or "type" not in reponse:
        return False
    return all(reponse.get(c) is None or isinstance(reponse.get(c), str) for c in CHAMPS_DU_CERVEAU)


def proposer_avec_cerveau(texte: str, ecriture: str, patients: list[dict[str, Any]], cerveau) -> dict[str, Any]:
    """La proposition de rangement, faite par un cerveau, puis VÉRIFIÉE contre le papier. Un cerveau peut inventer :
    - le type doit être dans la liste ; le patient doit être écrit sur le papier ET attendu aujourd'hui (c'est la règle
      qui le dit, pas le cerveau) ; la date et l'auteur doivent être recopiés tels quels du papier ;
    - tout ce qui ne tient pas est retiré, et la confiance tombe à « basse » : « je ne suis pas sûr » ;
    - si le cerveau et les règles simples ne sont pas d'accord sur le type, ce n'est pas sûr non plus ;
    - si le cerveau ne répond pas, ou hors formulaire : les règles simples, et la version le dit."""
    regles = proposer(texte, ecriture, patients)
    try:
        reponse = cerveau.lire(texte, list(TYPES), [str(p["nom"]) for p in patients])
        souci = "" if _reponse_lisible(reponse) else "réponse hors formulaire"
    except Exception as erreur:  # trop long, éteint, cassé : on ne bloque jamais l'accueil
        reponse, souci = None, f"{type(erreur).__name__}"
    if souci:
        return {**regles, "version": f"règles simples (le cerveau n'a pas répondu : {souci})"}

    raisons: list[str] = []
    genre = reponse.get("type")
    if genre is not None and genre not in TYPES:
        raisons.append(f"le cerveau propose un type qui n'est pas dans la liste (« {genre[:60]} »)")
        genre = regles["type"]
    elif genre != regles["type"]:
        raisons.append(f"le cerveau et les règles ne sont pas d'accord sur le type (règles : {regles['type'] or 'non reconnu'})")
    if genre is None:
        raisons.append("le type du papier n'est pas reconnu")

    # Le patient : seule la règle décide (un nom écrit sur le papier, d'une personne attendue aujourd'hui).
    patient, nom_du_patient = regles["patient"], regles["nom_du_patient"]
    if patient is None:
        raisons.append("le cerveau nomme un patient qui n'est pas écrit sur le papier, ou pas attendu aujourd'hui : "
                       "aucun patient ne correspond" if reponse.get("patient") else "aucun patient ne correspond")
    elif not reponse.get("patient") or _simple(reponse["patient"]).strip(" .") not in (
            _simple(str(nom_du_patient)).strip(" ."), _simple(" ".join(str(nom_du_patient).split()[1:])).strip(" .")):
        # d'accord : le nom entier (« Madame Giulia B. ») ou sans la civilité (« Giulia B. »). Rien de plus court.
        # relecture de la tranche 2 : « . », « a » ou « Madame » comptaient comme d'accord (ils sont « dans » le nom)
        raisons.append("le cerveau et les règles ne sont pas d'accord sur le patient")

    date, auteur = reponse.get("date"), reponse.get("auteur")
    if date is not None and date not in texte:
        raisons.append("date proposée par le cerveau : absente du papier, retirée")
        date = None
    if date is not None and not DATE.fullmatch(date.strip()):
        # H06a, mesuré avec le vrai Apertus le 12.11 : il mettait « Neuf séances. » ou « INVENTÉ » dans la date,
        # des mots bien écrits sur le papier, mais qui ne sont pas une date.
        raisons.append("date proposée par le cerveau : ce n'est pas une date, retirée")
        date = None
    if auteur is not None and auteur not in texte:
        raisons.append("auteur proposé par le cerveau : absent du papier, retiré")
        auteur = None
    if auteur is not None:
        # relecture de la tranche 2 : « e », « » ou le nom de la patiente passaient (ce sont des bouts du papier).
        # L'auteur doit être celui que la règle lit sur la première ligne du papier (ou un morceau entier de celui-ci).
        dit, lu = _simple(auteur).strip(" .,"), _simple(regles["auteur"] or "")
        if len(dit) < 4 or not lu or dit not in lu:
            raisons.append("auteur proposé par le cerveau : ce n'est pas l'auteur lu par la règle sur le papier, retiré")
            auteur = regles["auteur"]

    if reponse["confiance"] != "haute":
        raisons.append(f"le cerveau dit que sa confiance est {reponse['confiance']}")
    if _simple(ecriture) != "tapee":
        raisons.append(f"écriture : {ecriture}")
    sur = not raisons
    return {"type": genre, "date": date, "auteur": auteur, "patient": patient, "nom_du_patient": nom_du_patient,
            "endroit": TYPES[genre]["endroit"] if genre and patient else None,
            "confiance": "haute" if sur else "basse", "dit": "" if sur else PAS_SUR, "raisons": raisons,
            "version": f"cerveau : {cerveau.nom}, vérifié contre le papier par des règles", "marque": MARQUE}


class Papiers:
    def __init__(self, porte: PorteDeLecture, carnet: Carnet, cerveau=None, lecteur=None) -> None:
        self.cerveau = cerveau  # None : les règles simples (T09). Sinon : un cerveau qui propose, vérifié par les règles (T14)
        # None : le texte de référence tient lieu de papier lu. Sinon : identifiant → ce que la lecture de l'image a donné (T15)
        self.lecteur = lecteur
        self.muet = False  # vrai pendant la panne « le cerveau ne répond plus » (pannes.py)
        self._sans_proposition: list[str] = []
        self.porte, self.carnet = porte, carnet
        # Avenant 4, L04 : des papiers arrivés sur demande (texte seulement), et ceux qu'une remise à zéro a retirés de la pile.
        self.arrives: list[dict[str, Any]] = []
        self.retires: set[str] = set()

    # ------------------------------------------------------------------ qui a le droit
    def _accueil(self, badge: Badge, quoi: str) -> None:
        if badge.role != "accueil":
            self.porte.refuser(badge, quoi, "les papiers à ranger sont pour l'accueil")

    @staticmethod
    def _qui_range(badge: Badge) -> Badge:
        return badge if badge.role == "assistant" else charger_badges()["assistant"].travaille_pour(badge)

    # ------------------------------------------------------------------ lire
    def _etats(self) -> dict[str, dict[str, Any]]:
        """L'état d'un papier est sa dernière ligne au carnet. On ne croit que les lignes complètes, écrites avec un
        badge de l'accueil : une autre pièce ne peut pas changer l'état d'un papier."""
        return {l["donnees"]["papier"]: l for l in self.carnet.lignes(GENRE)
                if l["role"] == "accueil" and isinstance(l["donnees"].get("papier"), str)
                and l["donnees"].get("etat") in (PROPOSE, VALIDE, A_TRIER) and isinstance(l["donnees"].get("texte"), str)}

    def _du_jour(self, badge: Badge) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Les papiers apportés aujourd'hui (texte et écriture seulement) et les personnes possibles, par la porte."""
        arrivees = self.porte.patients(badge)
        # H01 : le texte des papiers n'est pas donné à l'accueil. Cette pièce le lit avec son propre badge (l'assistant,
        # au service de l'accueil), pour préparer sa proposition. C'est noté au journal des accès.
        papiers = self.porte.papiers_a_ranger(self._qui_range(badge))
        papiers += [dict(p) for p in self.arrives]  # arrivés sur demande (pré-admission, L04) : aucun patient ne correspond
        if self.lecteur is not None:  # T15 : le texte vient de l'image du papier, quand elle existe
            for papier in papiers:
                try:
                    lu = self.lecteur(papier["id"])
                except Exception as erreur:  # une image illisible ne bloque pas l'accueil : on le dit, on garde la référence
                    lu, papier["source"] = None, f"texte de référence (image illisible : {type(erreur).__name__})"
                if lu is not None:
                    papier.update(texte=lu["texte"], ecriture=lu["ecriture"], source=f"image lue par la {lu['outil']}")
                else:
                    papier.setdefault("source", "texte de référence (pas d'image)")
        return papiers, [{"id": p["id"], "nom": p["nom"]} for p in arrivees]

    def _tous(self, badge: Badge) -> list[dict[str, Any]]:
        """Tous les papiers connus, avec leur texte entier : ceux du jour (proposés à la première lecture), et ceux des
        jours d'avant, qui attendent dans le carnet."""
        papiers, patients = self._du_jour(badge)
        etats = self._etats()
        self._sans_proposition = [p["id"] for p in papiers if p["id"] not in etats] if self.muet else []
        for papier in papiers:
            if papier["id"] not in etats and not self.muet:  # cerveau muet : pas de proposition, le papier attend
                if self.cerveau is not None:  # H09 (cahier 5.2) : le cerveau a son badge, et sa lecture est au journal
                    self.porte.noter(self._qui_range(badge), f"texte d'un papier donné au cerveau : « {papier['id']} »", [])
                proposition = (proposer(papier["texte"], papier["ecriture"], patients) if self.cerveau is None
                               else proposer_avec_cerveau(papier["texte"], papier["ecriture"], patients, self.cerveau))
                etat = PROPOSE if proposition["patient"] else A_TRIER
                etats[papier["id"]] = self.carnet.ecrire(badge, GENRE, {"papier": papier["id"], "etat": etat, **papier,
                                                                        **proposition}, valide_par_un_humain=False)
        return [dict(ligne["donnees"]) for ligne in etats.values() if ligne["donnees"]["papier"] not in self.retires]

    def pile(self, badge: Badge) -> dict[str, Any]:
        """Les papiers, chacun avec sa proposition. Une proposition est écrite au carnet une seule fois.
        H01 : l'accueil ne reçoit aucune ligne du papier — le genre proposé, la date, l'auteur, le patient, l'endroit."""
        self._accueil(badge, "papiers à ranger")
        version = VERSION if self.cerveau is None else f"cerveau : {self.cerveau.nom}, vérifié contre le papier par des règles"
        if self.lecteur is not None:
            version = version.replace("à partir du texte de référence", "à partir de l'image du papier") + " ; texte lu depuis l'image du papier"
        pile: dict[str, Any] = {"a_valider": [], "a_trier": [], "valides": [], "marque": MARQUE, "version": version,
                                "types": list(TYPES)}
        for d in self._tous(badge):
            proposition = {cle: d.get(cle) for cle in ("type", "date", "auteur", "patient", "nom_du_patient", "endroit",
                                                       "confiance", "dit", "raisons")}
            vu = {"id": d["papier"], "langue": d.get("langue"), "ecriture": d.get("ecriture"),
                  "etat": d["etat"], "proposition": proposition, "valide": d.get("valide"),
                  "choisi_par_un_humain": bool(d.get("choisi_par_un_humain"))}
            pile[{PROPOSE: "a_valider", A_TRIER: "a_trier", VALIDE: "valides"}[d["etat"]]].append(vu)
        pile["sans_proposition"] = list(self._sans_proposition)
        pile["dit"] = (f"{len(self._sans_proposition)} papier(s) sans proposition : le cerveau ne répond plus. Ils attendent ; "
                       "rien n'est rangé sans proposition." if self._sans_proposition else "")
        return pile

    # ------------------------------------------------------------------ valider (un humain, d'un doigt)
    def valider(self, badge: Badge, papier: str, type: str | None = None) -> dict[str, Any]:
        """Un humain valide la proposition. `type` : son choix, s'il corrige ou si le prototype n'est pas sûr."""
        self._accueil(badge, "valider un rangement")
        tous = {d["papier"]: d for d in self._tous(badge)}
        if papier not in tous:
            raise PapierRefuse("ce papier n'est pas dans les papiers à ranger")
        d = tous[papier]
        if d["etat"] == VALIDE:
            return self._sans_texte(d)  # déjà validé : on ne compte pas deux fois
        if d["etat"] == A_TRIER or d.get("patient") is None:
            raise PapierRefuse("aucun patient ne correspond : ce papier reste dans « à trier », il n'est pas rangé")
        if type is not None and type not in TYPES:
            raise PapierRefuse("ce type de document n'existe pas dans la liste")
        if type is None and (d.get("confiance") != "haute" or d.get("type") not in TYPES):
            raise PapierRefuse(f"« {PAS_SUR} » : choisissez le type du document")
        choisi = type or d["type"]
        etat = self.carnet.horloge.etat() if self.carnet.horloge is not None else None
        heure = f"Jour {etat['jour']} — {int(etat['heure'][:2])} h {etat['heure'][3:]}" if etat else "heure non notée"
        ligne = self.carnet.ecrire(badge, GENRE, {**d, "etat": VALIDE, "type": choisi, "endroit": TYPES[choisi]["endroit"],
                                                  "choisi_par_un_humain": type is not None,
                                                  "valide": f"validée par {badge.libelle}, à {heure}"},
                                   valide_par_un_humain=True)
        return self._sans_texte(ligne["donnees"])

    @staticmethod
    def _sans_texte(donnees: dict[str, Any]) -> dict[str, Any]:
        """H01 : ce qui revient à l'accueil (et à son écran) ne porte jamais le texte du papier."""
        return {cle: v for cle, v in donnees.items() if cle != "texte"}
