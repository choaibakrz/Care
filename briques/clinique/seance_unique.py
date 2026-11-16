"""N03a — La répétition « d'un seul trait », jouée par le chef de démonstration (réponses de Hiba à Q14 et Q20).

    python3 lancer.py seance-unique            faux robot à vitesse normale : la durée est celle d'une vraie démonstration
    python3 lancer.py seance-unique --vite     faux robot accéléré 20 fois (pour les vérifications)

UNE seule clinique, UN seul faux robot, UNE seule horloge, du début à la fin : chaque étape trouve ce que la précédente a
laissé (le message de l'arrivée, la liste cochée…). Ce n'est pas la grande répétition (où chaque étape repart d'une clinique
neuve) : c'est la démonstration elle-même, jouée par le chef de démonstration de l'ossature (brique 15), avec la nouvelle
sorte d'étape « contrôle » (H05) : une annonce par scène, puis un contrôle par étape.
La durée de chaque étape, de chaque scène et de la séance est mesurée (montre réelle) et affichée.
N03a : scènes 1 à 3 (étapes 1 à 8). N03b : scènes 4 à 7 (étapes 9 à 14), dans la même séance : les questions du soir
arrivent dans le résumé du lendemain ; la panne est reprise par le faux robot de la séance ; la fiche de vérité est celle
de CETTE séance ; « rien n'est sorti de l'ordinateur » est surveillé depuis le début (la surveillance de la répétition).
La commande joue les sept scènes ; `jouer(scenes=...)` peut en jouer moins (les essais de N03a jouent 1 à 3).
DIRE VRAI : l'arrivée est tapée, pas dite ; les coches et les validations sont faites par le programme ; faux robot.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

CODE = "code-de-la-seance-unique"
SCENES = (1, 2, 3)  # par défaut de jouer() (les essais de N03a) ; la commande joue les sept
TOUTES = tuple(range(1, 8))
SOIGNANT, PATIENT, LISTE = "soignant-etage-2", "p01", "installation"


class Seance:
    """La clinique de la séance : montée une fois, partagée par toutes les étapes."""

    def __init__(self, dossier: Path, acceleration: float) -> None:
        from fastapi import FastAPI

        from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

        from .carnet import Carnet
        from .coursier import monde_de_la_clinique
        from .ecrans import brancher_ecrans
        from .horloge import HorlogeDeDemonstration
        from .porte import JournalDesAcces, PorteDeLecture

        reglages = charger_reglages(REGLAGES_EXEMPLE)
        reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
        self.systeme = Systeme(reglages, dossier_journal=str(dossier / "journal"), acceleration=acceleration,
                               monde=monde_de_la_clinique())
        self.horloge = HorlogeDeDemonstration(bus=self.systeme.bus)
        self.app = FastAPI()
        self.clinique = brancher_ecrans(self.app, porte=PorteDeLecture(journal=JournalDesAcces(), jour=self.horloge.jour),
                                        horloge=self.horloge, carnet=Carnet(horloge=self.horloge), systeme=self.systeme,
                                        code_equipe=CODE)
        self.clinique.faux_logiciel.dossier = dossier / "faux_logiciel"  # jamais le dossier de l'équipe
        self.loop: asyncio.AbstractEventLoop | None = None
        self.heures: list[str] = []
        self.notes: dict[int, Any] = {}

    # ---------------------------------------------------------------- tout se passe dans la boucle du faux robot
    def dans_la_boucle(self, coro, delai_s: float = 900.0):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=delai_s)

    def _appel(self, methode: str, chemin: str, **kw):
        import httpx

        async def faire():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://127.0.0.1",
                                         headers={"X-Code-Equipe": CODE}) as client:
                return await client.request(methode, chemin, **kw)

        return self.dans_la_boucle(faire())

    def get(self, chemin: str, **params):
        return self._appel("GET", chemin, params=params)

    def post(self, chemin: str, corps: dict[str, Any]):
        return self._appel("POST", chemin, json=corps)

    def sauter(self, repere: str) -> None:
        from . import horloge as horloge_clinique

        try:
            self.dans_la_boucle(self.horloge.sauter(repere))
        except horloge_clinique.SautRefuse:
            attendu, etat = horloge_clinique.reperes()[repere], self.horloge.etat()
            if (etat["jour"], etat["heure"]) != (attendu["jour"], attendu["heure"]):
                raise
        etat = self.horloge.etat()
        self.heures.append(f"{etat['jour']}-{etat['heure']}")
        from . import repetition

        if repetition.SEANCE is not None:  # la fiche de vérité compte les sauts de l'horloge du scénario
            repetition.SEANCE.sauts = len(self.horloge.sauts)


# ---------------------------------------------------------------------- les étapes, sur la clinique partagée
def etapes(s: Seance) -> dict[str, Callable[[], tuple[bool, str]]]:
    from . import dossier as faux_dossier
    from .ecrans_accueil import ARRIVEES

    def etape_1():
        s.sauter("arrivée")
        phrase, nom, attendus = ARRIVEES["it"]
        r = s.post("/api/clinique/hall/entendre", {"texte": phrase}).json()
        manquent = [a for a in attendus if a not in r.get("dit", "")]
        chemin = [p.get("lieu") for p in r.get("chemin", [])]
        ok = r.get("cas") == "arrivée" and r.get("langue") == "it" and not manquent and chemin[-1:] == ["Chambre 12"]
        return ok, f"arrivée tapée : « {phrase} » ; réponse en {nom} : « {r.get('dit', '')[:90]}… »"

    def etape_2():
        appels = len(s.clinique.carnet.lignes("appel d'un humain"))
        messages = len(s.clinique.carnet.lignes("message pour l'étage"))
        r = s.post("/api/clinique/hall/entendre", {"texte": "Pourquoi Madame B. est-elle ici ?"}).json()
        fuites = [f for f in ("Giulia", "hanche", "réadaptation") if f in str(r)]
        ok = (r.get("cas") == "santé" and not fuites and len(s.clinique.carnet.lignes("appel d'un humain")) == appels + 1
              and len(s.clinique.carnet.lignes("message pour l'étage")) == messages)
        return ok, f"question de santé refusée : « {r.get('dit')} » ; un humain est appelé"

    def etape_3():
        page = s.get("/clinique/soignant/contenu", badge=SOIGNANT).text
        ok = "Messages du hall (1)" in page and "Madame Giulia B. arrive. Chambre 12." in page
        return ok, "sur l'écran du soignant de l'étage 2 : le message laissé par l'arrivée de l'étape 1 (aucune nouvelle arrivée)"

    def etape_4():
        s.sauter("papiers")
        avant = faux_dossier.empreinte()
        attendus = {d["id"]: d["genre"] for d in faux_dossier.charger().patient(PATIENT)["DocumentReference"]}
        pile = s.get("/api/clinique/papiers", badge="accueil").json()
        proposes = {p["id"]: p["proposition"] for p in pile.get("a_valider", [])}
        bons = [i for i, genre in attendus.items() if i in proposes and proposes[i]["type"] == genre and proposes[i]["patient"] == PATIENT]
        reponses = [s.post("/api/clinique/papiers/valider", {"badge": "accueil", "papier": i}) for i in attendus]
        valides = [l for l in s.clinique.carnet.lignes("rangement de papier") if l["donnees"]["etat"] == "validé"]
        ok = len(bons) == 3 and all(r.status_code == 200 for r in reponses) and len(valides) == 3 and faux_dossier.empreinte() == avant
        return ok, f"{len(bons)} papiers sur 3 proposés au bon endroit, {len(valides)} validés par le programme (badge de l'accueil)"

    def etape_5():
        pile = s.get("/api/clinique/papiers", badge="accueil").json()
        a_trier = [p["id"] for p in pile.get("a_trier", [])]
        refus = s.post("/api/clinique/papiers/valider", {"badge": "accueil", "papier": "f-01"})
        ok = a_trier == ["f-01"] and refus.status_code == 400
        return ok, f"la feuille sans nom reste dans « à trier » ({', '.join(a_trier)}) ; la ranger est refusé ({refus.status_code})"

    def etape_6():
        s.sauter("installation en chambre")
        page = s.get("/clinique/soignant/liste", badge=SOIGNANT, patient=PATIENT, liste=LISTE)
        attendus = ("entend mal de l&#x27;oreille gauche", "Montrer la sonnette et la laisser à portée de main.")
        ok = page.status_code == 200 and all(a in page.text for a in attendus) and page.text.count("data-cocher=") == 6
        return ok, f"la liste « installation » s'affiche avec les habitudes et {page.text.count('data-cocher=')} points"

    def etape_7():
        for numero in (1, 2, 4, 5, 6):
            s.post("/api/clinique/liste/cocher", {"badge": SOIGNANT, "patient": PATIENT, "liste": LISTE, "numero": numero})
        r = s.post("/api/clinique/je_sors", {"badge": SOIGNANT, "patient": PATIENT}).json()
        ok = r.get("phrase") == "Il reste un point : la sonnette."
        return ok, f"cinq points cochés par le programme ; en sortant : « {r.get('phrase')} »"

    def etape_8():
        demande = {"badge": SOIGNANT, "patient": PATIENT, "texte": "il manque un coussin en chambre 12", "liste": LISTE, "numero": 4}
        r = s.post("/api/clinique/demande", demande).json()
        question = r.get("phrase") if r.get("genre") == "question" else None
        if question:
            r = s.post("/api/clinique/demande", {**demande, "choix": r["choix"][0]}).json()
        tache = r.get("tache") or {}
        fin = {}
        limite = time.monotonic() + 900
        while tache and time.monotonic() < limite:
            fin = s.clinique.taches.tache(tache["id"])
            if fin["etat"] in ("livrée", "échouée") or fin.get("sorte") == "humain":
                break
            time.sleep(0.05)
        points = s.get("/api/clinique/liste", badge=SOIGNANT, patient=PATIENT, liste=LISTE).json()["points"]
        reste = [p["numero"] for p in points if p["etat"] != "fait"]
        ok = bool(question) and fin.get("etat") == "livrée" and reste == [3]
        return ok, (f"question : « {question} » ; {fin.get('quoi', '?')} {fin.get('etat', '?')} par le faux robot "
                    f"({fin.get('de', '?')} → {fin.get('ou', '?')}) ; la liste de l'étape 7 : il reste le point {reste}")

    from .ecrans_soir import DICTEE_DU_SCENARIO, QUESTIONS_DU_SCENARIO
    from .resume import RIEN
    from .soir import MENTION_BROUILLON

    def etape_9():
        s.sauter("questions du soir")
        ecran = s.get("/clinique/patient", badge="patient-p01").text
        posee = "Ha domande per il medico domani?" in ecran
        reponses = [s.post("/api/clinique/soir/question", {"badge": "patient-p01", "texte": q}) for q in QUESTIONS_DU_SCENARIO]
        transmises = all(r.status_code == 200 and "trasmessa al medico" in r.json().get("dit", "") for r in reponses)
        lignes = s.clinique.carnet.lignes("question du soir")
        ok = posee and transmises and len(lignes) == 2
        return ok, (f"à 19 h, l'écran de la patiente pose la question en italien ; {len(lignes)} questions tapées par le "
                    f"programme, transmises au médecin ; le prototype ne répond pas")

    def etape_10():
        s.sauter("visite")
        medecin = s.clinique.badges["medecin-exemple"]
        resumes = s.clinique.resume.preparer(medecin)
        dites = [l for r in resumes for l in r["lignes"] if l["texte"] != RIEN]
        sans_source = [l["titre"] for l in dites if not l["sources"]]
        page = s.get("/clinique/medecin", badge=medecin.id).text
        giulia = next((r for r in resumes if r["patient"] == PATIENT), {"lignes": []})
        questions = next((l for l in giulia["lignes"] if l["point"] == "questions"), {"texte": "", "sources": []})
        arrivees = [q for q in QUESTIONS_DU_SCENARIO if q in questions["texte"]]
        ok = not sans_source and len(arrivees) == 2 and len(questions["sources"]) == 2 and "Source" in page
        return ok, (f"le lendemain : {len(dites)} lignes de résumé, chacune avec sa source ; les deux questions de l'étape 9 "
                    f"sont dans le résumé de Madame B. ({len(arrivees)} sur 2, {len(questions['sources'])} sources)")

    def etape_11():
        avant = s.get("/clinique/therapeute", badge="therapeute-exemple").text
        r = s.post("/api/clinique/dictee", {"badge": "medecin-exemple", "patient": PATIENT, "texte": DICTEE_DU_SCENARIO})
        reponse = r.json() if r.status_code == 200 else {}
        page = s.get("/clinique/therapeute", badge="therapeute-exemple").text
        visible = "évaluer la marche demain" in page and "évaluer la marche demain" not in avant
        ok = visible and (reponse.get("tache") or {}).get("pour") == "thérapeute" and (reponse.get("brouillon") or {}).get("mention") == MENTION_BROUILLON
        return ok, f"« {DICTEE_DU_SCENARIO} » tapée par le programme → brouillon, et une tâche visible sur l'écran du thérapeute"

    def etape_12():
        s.sauter("panne d'un robot")
        soignant = s.clinique.badges[SOIGNANT]

        async def panne_et_reprise():
            tache = s.clinique.taches.demander(soignant, PATIENT, "la feuille d'exercices")["tache"]
            s.clinique.flotte.partir("robot-r3", tache["id"])
            en_panne = s.clinique.flotte.panne("robot-r3", "batterie basse")
            fin = await s.clinique.flotte.reprendre(tache["id"])
            return en_panne, fin

        en_panne, fin = s.dans_la_boucle(panne_et_reprise())
        ok = bool(en_panne) and en_panne["etat"] == "reprise" and fin["etat"] == "livrée" and fin.get("robot") == "robot-r1"
        return ok, (f"R3 (simulé) part avec la feuille d'exercices et tombe en panne (batterie basse) ; R1, le faux robot de "
                    f"la séance, reprend : {fin.get('quoi')} {fin['etat']} ({fin.get('de')} → {fin.get('ou')})")

    def etape_13():
        from . import fiche, repetition

        la_fiche = fiche.fiche_de_la_repetition(repetition.SEANCE)  # calculée sur CETTE séance ; pas gardée (la page montre la répétition)
        valeurs = {l["titre"]: str(l.get("valeur") or "").strip() for l in la_fiche["lignes"]}
        manquent = [t for t in fiche.LIGNES_DU_CAHIER + fiche.LIGNES_EN_PLUS if not valeurs.get(t)]
        ok = not manquent and repetition.SEANCE.jouees(range(1, 13))
        return ok, (f"la fiche de vérité de cette séance : {len(la_fiche['lignes'])} lignes, les 12 du cahier et des avenants "
                    f"remplies ; « Réussis du premier coup » : {valeurs.get('Réussis du premier coup', '?')[:40]}"
                    + (f" ; il manque : {manquent}" if manquent else ""))

    def etape_14():
        from .rien_dehors import etape_14 as rien_dehors

        r = rien_dehors()  # le contrôle établi, sur la surveillance ouverte au début de la séance
        return r.reussie, r.detail

    return {f"etape_{n}": f for n, f in enumerate((etape_1, etape_2, etape_3, etape_4, etape_5, etape_6, etape_7, etape_8,
                                                    etape_9, etape_10, etape_11, etape_12, etape_13, etape_14), 1)}


ETIQUETTES = {8: "FAUX ROBOT", 12: "FAUX ROBOT ET SIMULÉ"}  # les autres étapes : SIMULÉ (pas de robot)


def noter_dans_la_seance(controles: dict[str, Callable[[], tuple[bool, str]]]) -> dict[str, Callable[[], tuple[bool, str]]]:
    """Chaque étape jouée est notée dans la séance de la répétition (pour la fiche de vérité et l'étape 14)."""
    from . import repetition

    def noter(n: int, f):
        def note():
            try:
                ok, detail = f()
            except Exception as erreur:
                ok, detail = False, f"la pièce s'est arrêtée ({type(erreur).__name__} : {erreur})"[:300]
            repetition._noter(n, "reussie" if ok else "ratee", repetition.Resultat(ok, ETIQUETTES.get(n, "SIMULÉ"), detail))
            return ok, detail
        return note

    return {nom: noter(int(nom.split("_")[1]), f) for nom, f in controles.items()}


# ---------------------------------------------------------------------- compter ce qui est monté pendant la séance
@contextmanager
def compter_les_montages() -> Iterator[dict[str, int]]:
    """Le temps de la séance : combien de cliniques, de faux robots (systèmes) et d'horloges sont montés en plus."""
    from commun import systeme as module_systeme

    from . import ecrans, horloge

    compte = {"cliniques": 0, "robots": 0, "horloges": 0}
    brancher, sys_init, h_init = ecrans.brancher_ecrans, module_systeme.Systeme.__init__, horloge.HorlogeDeDemonstration.__init__

    def brancher_compte(*a, **k):
        compte["cliniques"] += 1
        return brancher(*a, **k)

    def sys_compte(self, *a, **k):
        compte["robots"] += 1
        return sys_init(self, *a, **k)

    def h_compte(self, *a, **k):
        compte["horloges"] += 1
        return h_init(self, *a, **k)

    ecrans.brancher_ecrans, module_systeme.Systeme.__init__, horloge.HorlogeDeDemonstration.__init__ = brancher_compte, sys_compte, h_compte
    try:
        yield compte
    finally:
        ecrans.brancher_ecrans, module_systeme.Systeme.__init__, horloge.HorlogeDeDemonstration.__init__ = brancher, sys_init, h_init


def _virgule(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def jouer(ecrire: Callable[[str], None] = print, dossier: str | Path | None = None, acceleration: float = 1.0,
          scenes: tuple[int, ...] = SCENES) -> dict[str, Any]:
    import tempfile

    from briques.b15_chef_demo.chef import ChefDemo
    from briques.b15_chef_demo.scenario import lire

    from . import chef_clinique, repetition

    a_part = None if dossier else tempfile.TemporaryDirectory()
    dossier = Path(dossier) if dossier else Path(a_part.name)
    scenario = chef_clinique.charger()
    voulues = tuple(scenes)
    scenes = [sc for sc in scenario.scenes if sc.numero in voulues]
    toutes = voulues == TOUTES
    partition = {"titre": f"La clinique en boîte — séance unique (scènes {voulues[0]} à {voulues[-1]})", "langue": "fr", "duree_max_s": 900,
                 "etapes": []}
    for scene in scenes:
        partition["etapes"].append({"nom": f"scene_{scene.numero}", "annonce": scene.annonce})
        partition["etapes"] += [{"nom": f"etape_{n}", "controle": f"etape_{n}"} for n in scene.etapes]
    with compter_les_montages() as compte, repetition.seance():
        seance = Seance(dossier, acceleration)
        montages_avant = dict(compte)
        controles = noter_dans_la_seance(etapes(seance))

        async def principal():
            await seance.systeme.demarrer()
            seance.loop = asyncio.get_running_loop()
            try:
                chef = ChefDemo(seance.systeme, lire(partition, "séance unique"), acceleration=acceleration, controles=controles)
                debut = time.monotonic()
                resultat = await chef.jouer()
                return resultat, time.monotonic() - debut
            finally:
                await seance.systeme.arreter()

        resultat, duree = asyncio.run(principal())
        en_plus = {k: compte[k] - montages_avant[k] for k in compte}
    if a_part is not None:
        a_part.cleanup()
    lignes_etapes = [{"etape": int(e.nom.split("_")[1]), "resultat": e.resultat, "detail": e.detail, "duree_s": e.duree_s}
                     for e in resultat.etapes if e.genre == "controle"]
    annonces = sum(1 for e in resultat.etapes if e.genre == "annonce" and e.resultat == "reussie")
    vitesse = "faux robot à vitesse normale" if acceleration == 1 else f"faux robot accéléré {acceleration:g} fois"
    ecrire("LA SÉANCE UNIQUE — une seule clinique, jouée par le chef de démonstration (brique 15) — DONNÉES INVENTÉES — FAUX ROBOT")
    for scene in scenes:
        du = [l for l in lignes_etapes if l["etape"] in scene.etapes]
        ecrire(f"  scène {scene.numero} — {scene.titre} : {_virgule(sum(l['duree_s'] for l in du))} s")
        for l in du:
            ecrire(f"    étape {l['etape']} : {'réussie' if l['resultat'] == 'reussie' else 'RATÉE'} ({_virgule(l['duree_s'])} s) — {l['detail']}")
    ecrire(f"  durée de la séance : {_virgule(duree)} s (montre réelle ; {vitesse} ; arrivée tapée, coches par le programme)")
    ecrire(f"  montés pendant la séance : 1 clinique, 1 faux robot, 1 horloge ; en plus : {en_plus['cliniques']} clinique, "
           f"{en_plus['robots']} robot, {en_plus['horloges']} horloge")
    if not toutes:
        ecrire(f"  scènes 4 à 7 : pas jouées dans cette séance (elle ne joue que les scènes {', '.join(str(n) for n in voulues)}) ; "
               "la commande « python3 lancer.py seance-unique » joue les sept (N03b est faite)")
    attendues = [n for sc in scenes for n in sc.etapes]
    reussi = ([l["etape"] for l in lignes_etapes] == attendues and all(l["resultat"] == "reussie" for l in lignes_etapes)
              and not any(en_plus.values()) and annonces == len(scenes))
    ecrire(f"SÉANCE UNIQUE (scènes {voulues[0]} à {voulues[-1]}) : {'RÉUSSIE' if reussi else 'RATÉE'}")
    return {"reussi": reussi, "etapes": lignes_etapes, "duree_s": duree, "chef": "brique 15", "annonces": annonces,
            "cliniques": 1 + en_plus["cliniques"], "robots": 1 + en_plus["robots"], "horloges": 1 + en_plus["horloges"],
            "heures": list(seance.heures)}


def main(reste: list[str] | None = None) -> int:
    return 0 if jouer(acceleration=20.0 if "--vite" in (reste or []) else 1.0, scenes=TOUTES)["reussi"] else 1
