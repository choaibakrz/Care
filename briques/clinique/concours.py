"""KC — La commande du concours (avenant 2, partie 6). À côté de la grande répétition et de la commande des preuves.

    python3 lancer.py concours [--court]

Les sept contrôles, joués sur le faux robot, chacun par les vraies pièces :
1. le tirage : trois tirages, et « gestes interdits exécutés : 0 » ;
2. l'aide humaine : une aide déclarée change la case de l'essai ; une endurance d'une minute finit sans arrêt ;
3. l'âge de l'information : un écran coupé se grise ; une tâche confirmée mais pas constatée ne compte pas ;
4. le choix expliqué : deux situations, deux choix, deux phrases ; chaque départ a son annonce ;
5. le tableau des capacités : aucune capacité dans la colonne du vrai robot sans essai réel ;
6. les avis : le formulaire marche ; aucun avis d'essai ne reste ; la page dit vrai sur le nombre d'avis réels ;
7. l'invité : les quatre boutons marchent ; la remise à zéro prend moins de dix secondes.
Une ligne par contrôle, avec son étiquette ; puis CONCOURS : RÉUSSI ou CONCOURS : RATÉ — (ce qui manque).
Garde-fous : un contrôle sauté, une pièce qui plante ou une tâche BLOQUÉ → RATÉ ; une partie seulement → jamais « RÉUSSI ».
`--court` : un tirage au lieu de trois, une endurance de dix secondes au lieu d'une minute ; chaque ligne le dit.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


def _sans_bruit(_: str) -> None:
    return None


# ---------------------------------------------------------------------- 1. le tirage
def controle_1(c: dict[str, Any]) -> dict[str, Any]:
    from . import tirage

    numeros = (1,) if c["court"] else (1, 2, 3)
    interdits = 0
    for n in numeros:
        interdits += tirage.jouer(n, ecrire=_sans_bruit, dossier=c["dossier"] / f"tirage_{n}")["interdits_executes"]
    quoi = "1 tirage (version courte : la commande en joue trois)" if c["court"] else "3 tirages (n° 1, 2, 3)"
    return {"reussi": interdits == 0, "etiquette": "FAUX ROBOT",
            "detail": f"{quoi}, 30 demandes chacun ; gestes interdits exécutés : {interdits} ; cerveau de test"}


# ---------------------------------------------------------------------- 2. l'aide humaine
def controle_2(c: dict[str, Any]) -> dict[str, Any]:
    from . import aide_humaine, endurance, essais, repetition

    controles = dict(repetition.CONTROLES)
    vraie = controles[3]

    def avec_une_aide():
        aide_humaine.signaler("bouton", qui="commande du concours", detail="une aide déclarée exprès, pour le contrôle")
        return vraie()

    controles[3] = avec_une_aide
    bilan = essais.jouer_les_essais(essais.charger()[:1], controles=controles, ecrire=_sans_bruit, dossier=c["dossier"] / "essais")
    cases = bilan["fiche"]["cases"]
    case = next((case for case, n in cases.items() if n), "aucune")
    duree = 10.0 if c["court"] else 60.0
    mesure = endurance.tenir(duree, ecrire=_sans_bruit, dossier=c["dossier"] / "endurance")
    quoi = "10 s (version courte : la commande tient une minute)" if c["court"] else "une minute"
    ok = cases.get(aide_humaine.CASES[2]) == 1 and mesure["arret"] == endurance.AUCUN_ARRET
    return {"reussi": ok, "etiquette": "FAUX ROBOT ET SIMULÉ",
            "detail": f"un essai avec une aide déclarée va dans la case « {case} » ; endurance de {quoi} : {mesure['passages']} "
                      f"passages, {mesure['arret']}"}


# ---------------------------------------------------------------------- 3. l'âge de l'information
def _ecran_coupe() -> tuple[bool, str]:
    from . import ecrans
    from .tests.test_age_de_l_information import BANC, SCENARIO

    if shutil.which("node") is None:
        return False, "Node absent : le petit programme de la page n'est pas joué (contrôle sauté = raté)"
    script = ecrans.script_de_mise_a_jour("/clinique/soignant/contenu").replace("<script>", "").replace("</script>", "")
    sortie = subprocess.run(["node", "-e", BANC + script + f"\nconst LIMITE = {ecrans.LIMITE_VIEUX_S};\n" + SCENARIO],
                            capture_output=True, text=True, timeout=30)
    vu = next((l for l in sortie.stdout.splitlines() if l.startswith("AGE : GRISE A")), "")
    return sortie.returncode == 0 and bool(vu), (vu.replace("AGE : GRISE A", "écran coupé : grisée à").lower() if vu
                                                 else f"pas grisée ({sortie.stderr.strip()[:120]})")


def _confirme_pas_constate(dossier: Path) -> tuple[bool, str]:
    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from . import aide_humaine
    from .carnet import Carnet
    from .coursier import Coursier, monde_de_la_clinique
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges
    from .taches import TableauDesTaches

    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    badges = charger_badges()

    async def jouer():
        systeme = Systeme(reglages, dossier_journal=str(dossier), acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, badges["robot-r1"])
        vrai_etat = systeme.prise.etat

        async def rien_n_a_bouge():  # le faux robot dit qu'il a fini, mais le monde montre l'objet toujours à la réserve
            etat = await vrai_etat()
            objets = {**etat.extra["objets"], "couverture": [3.4, 4.5]}
            return etat.model_copy(update={"extra": {**etat.extra, "objets": objets}})

        coursier._lire_le_monde = rien_n_a_bouge
        tache = tableau.demander(badges["soignant-etage-2"], "p01", "la couverture")["tache"]
        await systeme.demarrer()
        try:
            with aide_humaine.compter() as compte:
                fin = await coursier.faire(tache["id"])
        finally:
            await systeme.arreter()
        return fin, compte

    fin, compte = asyncio.run(jouer())
    ok = fin["etat"] == "livrée" and fin.get("constate") == "pas encore" and compte.livraisons == 1 and compte.constatees == 0
    return ok, (f"une livraison confirmée sans que le monde change : « {fin['etat']} », constaté : {fin.get('constate')} ; "
                f"réussis et constatés : {compte.constatees} sur {compte.livraisons}")


def controle_3(c: dict[str, Any]) -> dict[str, Any]:
    ok1, dit1 = _ecran_coupe()
    ok2, dit2 = _confirme_pas_constate(c["dossier"] / "constat")
    return {"reussi": ok1 and ok2, "etiquette": "FAUX ROBOT ET SIMULÉ", "detail": f"{dit1} ; {dit2}"}


# ---------------------------------------------------------------------- 4. le choix expliqué
def controle_4(c: dict[str, Any]) -> dict[str, Any]:
    from commun.systeme import REGLAGES_EXEMPLE, Systeme, charger_reglages

    from . import cartes, repartiteur
    from .carnet import Carnet
    from .coursier import Coursier, monde_de_la_clinique
    from .horloge import HorlogeDeDemonstration
    from .listes import ListesDeSoin
    from .monde_robots import MondeDesRobots
    from .porte import JournalDesAcces, PorteDeLecture, charger_badges
    from .taches import TableauDesTaches

    flotte = cartes.CartesDeLaFlotte()
    monde = MondeDesRobots(cartes=flotte)
    monde.placer("robot-r1", "Salon")
    rep = repartiteur.Repartiteur(monde, flotte)
    tache = {"id": "t1", "quoi": "couverture", "de": "Réserve", "ou": "Chambre 12"}
    monde.envoyer("robot-r2", "Chambre 11")  # situation 1 : le plus proche est occupé
    occupe = rep.choisir(tache)
    monde._robot("robot-r4")["batterie"] = 16.0  # situation 2 : en plus, une batterie basse
    batterie = rep.choisir(tache)
    deux = occupe["robot"] != batterie["robot"] and occupe["pourquoi"] != batterie["pourquoi"]

    reglages = charger_reglages(REGLAGES_EXEMPLE)
    reglages["cerveau"] = {**reglages["cerveau"], "choix": "regles"}
    badges = charger_badges()

    async def course():
        systeme = Systeme(reglages, dossier_journal=str(c["dossier"] / "annonce"), acceleration=20.0, monde=monde_de_la_clinique())
        horloge = HorlogeDeDemonstration(bus=systeme.bus)
        carnet = Carnet(horloge=horloge)
        listes = ListesDeSoin(PorteDeLecture(journal=JournalDesAcces(), jour=horloge.jour), carnet)
        tableau = TableauDesTaches(listes.porte, carnet, listes)
        coursier = Coursier(systeme, tableau, listes, badges["robot-r1"])
        t = tableau.demander(badges["soignant-etage-2"], "p01", "la couverture")["tache"]
        await systeme.demarrer()
        try:
            fin = await coursier.faire(t["id"])
        finally:
            await systeme.arreter()
        return fin, list(systeme.bus.historique)

    fin, historique = asyncio.run(course())
    suite = ["annonce" if e.type == "note" and e.donnees.get("quoi") == "annonce" else "départ" for e in historique
             if (e.type == "note" and e.donnees.get("quoi") == "annonce")
             or (e.type == "action_demarree" and (e.donnees.get("action") or {}).get("nom") == "se_deplacer")]
    paires = suite == ["annonce", "départ"] * (len(suite) // 2) and len(suite) >= 2
    return {"reussi": deux and paires and fin["etat"] == "livrée", "etiquette": "FAUX ROBOT ET SIMULÉ",
            "detail": f"deux situations (un robot occupé ; puis une batterie basse) : deux choix ({occupe['nom']}, {batterie['nom']}) "
                      f"et deux phrases ; une course sur le faux robot : {suite.count('départ')} départs, chacun précédé de son annonce "
                      f"dans la boîte noire"}


# ---------------------------------------------------------------------- 5. le tableau des capacités
def controle_5(c: dict[str, Any]) -> dict[str, Any]:
    from . import capacites

    lignes = capacites.tableau()
    fausses = [l["titre"] for l in lignes if l["niveau"] == capacites.REEL and (l["reel"] == capacites.VIDE or l["reel"].startswith("0 "))]
    sans_reel = capacites.tableau(reels=c["dossier"] / "aucun_essai_reel.jsonl")
    vides = [l["titre"] for l in sans_reel if l["niveau"] == capacites.REEL]
    reelles = sum(1 for l in lignes if l["niveau"] == capacites.REEL)
    return {"reussi": not fausses and not vides, "etiquette": "SIMULÉ",
            "detail": f"aucune capacité dans la colonne du vrai robot sans essai réel ({len(lignes)} capacités ; {reelles} dans la "
                      f"colonne du vrai robot aujourd'hui ; avec un compteur d'essais réels vide : {len(vides)})"}


# ---------------------------------------------------------------------- 6. les avis
def controle_6(c: dict[str, Any]) -> dict[str, Any]:
    import html

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from . import avis
    from .ecrans import brancher_ecrans

    reels = sum(1 for l in avis.Avis().lignes() if l.get("marque") == avis.REEL)  # le vrai fichier, lu seulement
    app = FastAPI()
    clinique = brancher_ecrans(app, code_equipe="code-de-la-commande-du-concours")
    clinique.faux_logiciel.dossier = c["dossier"] / "faux_logiciel"
    clinique.avis.fichier = c["dossier"] / "avis_essai.jsonl"  # jamais le vrai fichier des avis
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Code-Equipe": "code-de-la-commande-du-concours"})
    envoye = client.post("/api/clinique/avis", json={"role": "visiteur", "notes": [3, 3, 3, 3, 3], "essai": True})
    client.post("/api/clinique/avis/effacer-les-essais")
    restent = sum(1 for l in clinique.avis.lignes() if l.get("marque") == avis.ESSAI)
    clinique.avis.fichier = avis.FICHIER  # la page, sur le vrai fichier : dit-elle vrai ?
    page = html.unescape(client.get("/clinique/avis").text)
    vrai = (avis.AUCUN in page) if reels == 0 else (f"{reels} avis" in page.split("Avis réels")[1])
    return {"reussi": envoye.status_code == 200 and restent == 0 and vrai, "etiquette": "SIMULÉ",
            "detail": f"le formulaire enregistre un avis d'essai ; aucun avis d'essai ne reste ; avis réels : {reels}, et la page le dit"}


# ---------------------------------------------------------------------- 7. l'invité
def controle_7(c: dict[str, Any]) -> dict[str, Any]:
    from . import invite_essai

    bilan = invite_essai.essayer(ecrire=_sans_bruit, avec_lisibilite=False)
    plus_longue = max(bilan["remises"])
    return {"reussi": bool(bilan["reussi"]) and plus_longue < 10, "etiquette": "FAUX ROBOT",
            "detail": f"les quatre boutons dans six ordres : {bilan['ordres_reussis']} sur 6 ; remise à zéro la plus longue : "
                      f"{plus_longue:.2f} s (limite : 10 s)".replace(".", ",", 1)}


CONTROLES: dict[int, tuple[str, Callable[[dict[str, Any]], dict[str, Any]], tuple[str, ...]]] = {
    1: ("Le tirage", controle_1, ("K01a", "K01b")),
    2: ("L'aide humaine", controle_2, ("K02a", "K02b")),
    3: ("L'âge de l'information", controle_3, ("K03a", "K03b")),
    4: ("Le choix expliqué", controle_4, ("K04",)),
    5: ("Le tableau des capacités", controle_5, ("K05",)),
    6: ("Les avis", controle_6, ("K06",)),
    7: ("L'invité", controle_7, ("K07a", "K07b")),
}


def jouer(controles: dict[int, tuple] | None = None, ecrire: Callable[[str], None] = print, court: bool = False,
          dossier: str | Path | None = None, seulement: tuple[int, ...] | None = None, suivi: str | None = None) -> int:
    from .capacites import statuts_du_suivi

    controles = CONTROLES if controles is None else controles
    statuts = statuts_du_suivi(suivi)
    ecrire("LE CONCOURS — sept contrôles — DONNÉES INVENTÉES — sur le FAUX ROBOT" + (" — version courte" if court else ""))
    a_part = None if dossier else tempfile.TemporaryDirectory()
    c = {"court": court, "dossier": Path(dossier) if dossier else Path(a_part.name)}
    rates: list[str] = []
    numeros = tuple(range(1, 8)) if seulement is None else tuple(seulement)
    try:
        for numero in numeros:
            if numero not in controles:
                titre = CONTROLES.get(numero, (f"contrôle {numero}",))[0]
                ecrire(f"  {numero}. [—] MANQUANT — {titre} — pas de contrôle")
                rates.append(f"{numero} manquant")
                continue
            titre, fonction, taches = controles[numero]
            bloquees = [t for t in taches if statuts.get(t, "").startswith("BLOQUÉ")]
            if bloquees:
                ecrire(f"  {numero}. [—] RATÉ — {titre} — tâche BLOQUÉ : {', '.join(bloquees)} (Hiba décide)")
                rates.append(f"{numero} bloqué")
                continue
            try:
                r = fonction(c)
            except Exception as erreur:  # une pièce qui casse : le contrôle est raté, et on dit pourquoi
                r = {"reussi": False, "etiquette": "—", "detail": f"la pièce s'est arrêtée ({type(erreur).__name__} : {erreur})"[:300]}
            ecrire(f"  {numero}. [{r['etiquette']}] {'réussi' if r['reussi'] else 'RATÉ'} — {titre} — {r['detail']}")
            if not r["reussi"]:
                rates.append(str(numero))
    finally:
        if a_part is not None:
            a_part.cleanup()
    if rates:
        ecrire(f"CONCOURS : RATÉ — {', '.join(rates)}")
        return 1
    if seulement is not None:
        ecrire(f"CONCOURS : INCOMPLET — seulement {', '.join(str(n) for n in numeros)} sur 7")
        return 1
    ecrire("CONCOURS : RÉUSSI")
    return 0


def main(reste: list[str] | None = None) -> int:
    return jouer(court="--court" in (reste or []))
