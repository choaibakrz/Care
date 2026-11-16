"""Brique 8 — « Je ne suis pas sûr » : savoir demander de l'aide au bon moment.

1. Demande floue, ou deux actions possibles : une question courte au lieu d'agir.
   Le cerveau à règles le fait déjà. `filet_plusieurs_choix` le fait pour TOUS les cerveaux (idée de KnowNo :
   s'il reste plus d'un choix possible, on demande au lieu de parier).
2. Il bute : il lève la main. Deux incompréhensions de suite pour la même personne, deux échecs de suite,
   ou un verdict « humain » du gardien → événement `aide_demandee` (le signal pour l'écran)
   + « Je lève la main : j'ai besoin d'aide. », dit à voix haute dans la langue de la personne.
3. Un humain l'aide : il accepte ou refuse (demande du gardien), ou il lui apprend un mot (« frigo » = cuisine).
   Chaque aide est gardée : événement `aide_recue` dans la boîte noire, et les mots dans journal/aides_apprises.yaml.
"""
from __future__ import annotations

from briques.b01_prise.actions import ActionDemandee
from briques.b01_prise.carte import CarteIdentite
from briques.b06_cerveau.prise_cerveau import Decision
from commun.bus import Bus
from commun.monde import Monde
from commun.phrases import dire

from .aides_apprises import AidesApprises

# Pour chaque action : la précision qui nomme la cible, et où chercher les candidats dans le monde.
CIBLES = {"se_deplacer": ("lieu", "lieux"), "poser": ("lieu", "lieux"), "saisir": ("objet", "objets"),
          "regarder": ("cible", "tout"), "montrer": ("cible", "tout")}


def choses_nommees(texte: str, monde: Monde) -> tuple[list[str], list[str]]:
    """Les lieux et les objets du monde nommés dans la phrase (mêmes règles que le cerveau à règles)."""
    from briques.b06_cerveau.branchements.regles import contient, normaliser

    t = normaliser(texte)
    lieux = [l.id for l in monde.lieux if any(contient(t, n) for _, n in l.tous_les_noms())]
    objets = [o.id for o in monde.objets if any(contient(t, n) for _, n in o.tous_les_noms())]
    return lieux, objets


def filet_plusieurs_choix(decision: Decision, texte: str, monde: Monde, carte: CarteIdentite | None = None) -> Decision:
    """Deux lieux (ou deux objets, deux gestes) nommés pour une seule action : une question, pas un pari.
    Indépendant du cerveau : un modèle de langue peut choisir l'un des deux sans le dire."""
    if decision.genre != "action" or decision.action is None:
        return decision
    a = decision.action
    if a.nom == "rejouer_geste":
        from briques.b06_cerveau.branchements.regles import _lexique, contient, normaliser

        t = normaliser(texte)
        gestes = [g for g, table in _lexique()["gestes"].items()
                  if any(contient(t, m) for mots in table.values() for m in mots) and (carte is None or g in carte.gestes)]
        options = [ActionDemandee(nom="rejouer_geste", parametres={"nom": g}) for g in gestes]
    elif a.nom in CIBLES:
        parametre, ou = CIBLES[a.nom]
        lieux, objets = choses_nommees(texte, monde)
        candidats = lieux if ou == "lieux" else objets if ou == "objets" else lieux + objets
        options = [ActionDemandee(nom=a.nom, parametres={parametre: c}) for c in candidats]
    else:
        return decision
    if len(options) < 2:
        return decision
    return decision.model_copy(update={"genre": "question", "question": "question_choix", "options": options,
                                       "action": None, "texte": None, "confiance": min(decision.confiance, 0.4)})


class Doute:
    """Compte les incompréhensions et les échecs ; lève la main quand le robot bute."""

    def __init__(self, bus: Bus, monde: Monde, aides: AidesApprises | None = None, actif: bool = True,
                 incompris_avant_main: int = 2, echecs_avant_main: int = 2) -> None:
        self.bus = bus
        self.monde = monde
        self.aides = aides or AidesApprises()
        self.actif = actif  # reglages.yaml → interrupteurs.main_levee (le verdict « humain » du gardien marche toujours)
        self.incompris_avant_main = incompris_avant_main
        self.echecs_avant_main = echecs_avant_main
        self._incompris: dict[str, list[str]] = {}  # personne → phrases pas comprises, de suite
        self._echecs: list[str] = []  # actions ratées, de suite

    async def lever_la_main(self, raison: str, langue: str | None, conversation: str | None, robot: str | None = None,
                            **details) -> str:
        """Le signal (événement `aide_demandee`, vu par l'écran) et la phrase à dire à voix haute."""
        texte = dire("main_levee", langue)
        await self.bus.emettre("aide_demandee", "doute", robot=robot, conversation=conversation, raison=raison,
                               langue=langue, texte=texte, **details)
        return texte

    async def apres_decision(self, genre: str, personne: str, texte: str, langue: str | None,
                             conversation: str | None, robot: str | None = None) -> str | None:
        """Après chaque décision du cerveau. Rend la phrase « je lève la main » si le robot bute, sinon None.
        « inconnu » compte ; une question ne change rien ; tout le reste (compris) remet à zéro."""
        if genre == "question":
            return None
        if genre != "inconnu":
            self._incompris.pop(personne, None)
            return None
        phrases = self._incompris.setdefault(personne, [])
        phrases.append(texte)
        if not self.actif or len(phrases) < self.incompris_avant_main:
            return None
        del self._incompris[personne]
        return await self.lever_la_main("incompris_de_suite", langue, conversation, robot,
                                        personne=personne, phrases=phrases)

    async def apres_action(self, action: ActionDemandee, reussie: bool | None, langue: str | None,
                           conversation: str | None, robot: str | None = None, message: str = "") -> str | None:
        """Après chaque action : réussie (True), ratée (False) ou annulée (None, ne compte pas)."""
        if reussie is None:
            return None
        if reussie:
            self._echecs.clear()
            return None
        self._echecs.append(f"{action.resume()} : {message}".strip(" :"))
        if not self.actif or len(self._echecs) < self.echecs_avant_main:
            return None
        echecs, self._echecs = self._echecs, []
        return await self.lever_la_main("echecs_de_suite", langue, conversation, robot, echecs=echecs)

    async def apprendre(self, mot: str, langue: str, sens: str, qui: str = "humain") -> dict:
        """« Quand on dit X, cela veut dire Y » : gardé dans journal/aides_apprises.yaml et ajouté au monde tout de suite.
        Lève AideRefusee (ValueError) avec la raison, en français."""
        appris, nouveau = self.aides.apprendre(mot, langue, sens, self.monde)
        await self.bus.emettre("aide_recue", "doute", sorte="mot_appris", mot=appris.mot, langue=appris.langue,
                               sens=appris.sens, genre=appris.genre, nouveau=nouveau, qui=qui)
        return {**appris.model_dump(), "nouveau": nouveau}
