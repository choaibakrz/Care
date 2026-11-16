"""Brique 13 — Fabriquer les exemples de FLUX_POUR_MOTION_DESIGN.md à partir de VRAIS événements (faux robot).

    python -m briques.b13_ecran.exemples_flux            affiche les exemples
    python -m briques.b13_ecran.exemples_flux --ecrire   les réécrit dans FLUX_POUR_MOTION_DESIGN.md

Une petite séance sur le faux robot, cerveau à règles, sans Internet : l'écran (TestClient), une cascade dont le premier
cerveau est éteint (pour `cerveau_secours`), et la conversation avec une écoute factice (pour les événements de la voix).
Les types qu'aucune brique n'émet encore sont écrits à la main et marqués « pas encore émis ».
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
DOC = ICI / "FLUX_POUR_MOTION_DESIGN.md"
DEBUT, FIN = "<!-- EXEMPLES:DEBUT -->", "<!-- EXEMPLES:FIN -->"
CODE = {"X-Code-Equipe": "exemples"}

# Les champs utiles de chaque type (en plus de type, heure, conversation, robot).
CHAMPS = {
    "session_debut": "`mention` (testé sur faux / vrai robot), `cerveau`, `vrai_robot`. `carte` : la carte d'identité (raccourcie ici).",
    "session_fin": "rien de plus : le programme s'arrête.",
    "parole_entendue": "`texte`, `langue` (fr, de, gsw, it, en, zh ; vide = devinée plus tard), `confiance` de l'écoute.",
    "demande_comprise": "`genre` (action, question, inconnu, hors_carte, discussion, confirmation), `action.nom`, "
                        "`action.parametres`, `confiance`, `langue`, `duree_ms` (temps du cerveau). `source` = le cerveau.",
    "question_posee": "`question` (le texte dit), `options`, `langue`.",
    "aide_demandee": "à confirmer quand la brique 8 sera prête. Prévoir : `texte` ou `raison`.",
    "gardien_decision": "`verdict` (oui, non, humain), `action` (complétée : vitesse, force), `raisons[].code`.",
    "action_demarree": "`action.nom`, `action.parametres`, `id_action`, `longue`.",
    "action_progression": "`progression` de 0 à 1, `id_action`. Beaucoup de lignes : à filtrer si inutile.",
    "action_terminee": "`statut` (reussie, ratee, annulee), `message`, `duree_ms`.",
    "action_refusee": "`raisons[].code` (ex. robot_occupe), `action`.",
    "reponse_dite": "`texte`, `langue` (langue de la réponse), `langue_entendue`, `genre` (annonce, fin, refus, question, "
                    "inconnu…), `cle` + `valeurs` (phrase connue : l'écran la redit dans une autre langue).",
    "arret_urgence": "`raison`, `qui`. Passe avant tout : à montrer en grand.",
    "panne": "`quoi`, `provoquee` (vrai = panne d'entraînement).",
    "reparation": "`quoi` (tout, liaison, rearmement).",
    "etat_robot": "pas encore émis par une brique. Prévoir : `batterie_pct`, `erreurs`, `position`.",
    "pilotage_humain": "`quoi` : reprise, ordre, rendu, demande, demande_retiree (brique 11) ; `qui` (prénom ou rôle) ; "
                       "ordre : `action` (même `conversation` que la suite : gardien, robot) ; rendu : `duree_s`, `ordres`, "
                       "`fait`. La fiche compte la part de l'humain (reprise → rendu) et `ordres_humains`. Source "
                       "« main_humaine » = l'écran ; « chef_demo » = main humaine annoncée par le chef (opérateur simulé).",
    "regle_changee": "`regle`, `avant`, `apres` (la règle : `phrase`, `valeurs`…), `qui`, `comment` (vote du public, fichier relu), `vote`.",
    "aide_demandee": "`raison` (gardien, pas compris, échecs), `texte` ou `action` + `raisons`, `numero` (pour répondre). Le robot lève la main.",
    "aide_recue": "`sorte` (demande_du_gardien, mot_appris), `accepte`, `qui` ; pour un mot : `mot`, `sens`, `langue`.",
    "scenario_debut": "`titre`, `etapes`, `repetition`, `acceleration`, `pannes` prévues, `duree_visee_s`, `mention`.",
    "scenario_etape": "`quoi` (debut, fin), `numero`, `nom`, `genre` ; à la fin : `resultat`, `cause`, `detail`, `duree_s`, `plans_b`.",
    "plan_b": "`etat` (essai, reussi, rate, inutile), `moyen` (tablette, mode_local, main_humaine, sauter), `cause`, `etape`.",
    "scenario_fin": "`titre`, `duree_s`, `reussies`, `rattrapees`, `ratees`, `sautees`, `jouees`, `interrompu`, `raison`.",
    "note": "`texte` : une remarque (chiffres recopiés, décision annulée par un stop…).",
    "parole_finie": "`duree_s` de la phrase, `attente_fin_ms`, `bouton`.",
    "transcription": "`texte`, `langue`, `confiance`, `calcul_ms` (temps de l'écoute), `moteur`.",
    "mot_d_appel": "`texte`, `langue` : le robot écoute pendant un moment.",
    "interruption": "`parle_depuis_ms` : la personne a coupé la parole au robot.",
    "voix_debut": "`texte`, `langue`, `latence_ms` (fin de la phrase → début du son), `sous_titres_seulement`.",
    "cerveau_secours": "`de`, `vers`, `raison`, `attente_ms`.",
    "cerveau_serveur": "`quoi` (lance, arrete), `de`, `vers`, `raison` : un cerveau de secours lancé ou arrêté (pas une panne).",
    "confirmation_demandee": "`question`, `action`, `langue` : avant une action à risque, le robot attend « oui ».",
    "internet_coupe": "`coupe` (vrai / faux), `preuve`, `etages_eteints` (Apertus par Internet), `connexions_refusees`.",
    "mode_silence": "`actif` : la voix passe en sous-titres seulement, pictogrammes en grand.",
    "porte_agents": "`quoi` (ouverte, ordre_refuse), `agent` (agent:nom) ; ouverte : `ordres_par_minute`, `accord_humain` ; "
                    "ordre_refuse : `raison` (trop_d_ordres, ordre_invalide), `texte`. Les ordres acceptés, eux, sont des "
                    "`parole_entendue` de source « agent:nom » (brique 14).",
    "yeux": "`quoi` (demarrage, camera, gardien, branchement:NOM, objet_vu, objet_pas_vu, objet_non_cherche, erreur), "
            "`valeur`, `raison` ; demarrage : `mention` (testé sur caméra simulée / vraie caméra), `absents` ; objet_vu : "
            "`objet`, `direction_deg`, `distance_max_m`. Seulement quand quelque chose change (brique 5).",
}

# Les types qu'aucune brique n'émet encore (ou seulement par le micro et le détecteur de parole) : forme écrite à la main.
A_LA_MAIN = {
    "aide_demandee": ("émis par le gardien (brique 7) et par le doute (brique 8) — forme relevée dans le code, valeurs d'exemple",
                      {"raison": "gardien", "numero": "a1b2c3", "action": {"nom": "rejouer_geste", "parametres": {"nom": "verser"}},
                       "raisons": [{"code": "demander_humain", "details": {"regle": "verser"}}], "demandeur": "chaine"}),
    "cerveau_serveur": ("émis par la cascade du cerveau (brique 6) avec les vrais serveurs Apertus — forme relevée dans le code, valeurs d'exemple",
                        {"de": "apertus_8b", "vers": "apertus_4b", "quoi": "lance", "raison": "secours lancé au besoin"}),
    "aide_recue": ("émis par le gardien et le doute (briques 7, 8) — forme relevée dans le code, valeurs d'exemple",
                   {"sorte": "demande_du_gardien", "numero": "a1b2c3", "accepte": True, "qui": "ecran"}),
    "scenario_debut": ("émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple",
                       {"titre": "Essai de trois minutes", "fichier": "essai_3_minutes.yaml", "etapes": 21, "repetition": False,
                        "acceleration": 1.0, "pannes": {}, "graine": None, "duree_visee_s": 180, "mention": "testé sur faux robot"}),
    "scenario_etape": ("émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple",
                       {"quoi": "fin", "numero": 7, "nom": "aller_table", "genre": "dire", "resultat": "reussie", "cause": None,
                        "detail": "", "duree_s": 15.2, "limite_s": 30.0, "plans_b": []}),
    "plan_b": ("émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple",
               {"etat": "essai", "moyen": "tablette", "cause": "voix", "etape": "salut_fr", "numero": 2}),
    "scenario_fin": ("émis par le chef de démonstration (brique 15) — forme relevée dans le code, valeurs d'exemple",
                     {"titre": "Essai de trois minutes", "duree_s": 174.8, "reussies": 21, "rattrapees": 0, "ratees": 0,
                      "sautees": 0, "jouees": 21, "etapes": 21, "interrompu": False, "raison": None}),
    "etat_robot": ("pas encore émis — forme à vérifier", {"batterie_pct": 87.0, "erreurs": [], "position": {"x": 1.0, "y": 1.0}}),
    "regle_changee": ("émis par le gardien (brique 7) — forme relevée dans le code, valeurs d'exemple",
                      {"regle": "vitesse_max",
                       "avant": {"id": "vitesse_max", "phrase": "Le robot ne va jamais plus vite que 0,3 mètre par seconde.",
                                 "active": True, "sorte": "vitesse_max", "en_direct": True, "valeurs": {"m_s": 0.3}},
                       "apres": {"id": "vitesse_max", "phrase": "Le robot ne va jamais plus vite que 0,2 mètre par seconde.",
                                 "active": True, "sorte": "vitesse_max", "en_direct": True, "valeurs": {"m_s": 0.2}},
                       "qui": "vote", "comment": "vote du public"}),
    "pilotage_humain": ("émis par la main humaine (brique 11) — forme relevée dans le code, valeurs d'exemple",
                        {"quoi": "ordre", "qui": "Hiba", "action": {"nom": "se_deplacer", "parametres": {"lieu": "table"}},
                         "envoye_par": "Hiba"}),
    "mot_d_appel": ("émis par conversation.py avec un vrai micro — forme relevée dans le code, valeurs d'exemple",
                    {"texte": "Robot, va à la cuisine", "langue": "fr"}),
    "interruption": ("émis par conversation.py avec un vrai micro — forme relevée dans le code, valeurs d'exemple",
                     {"parle_depuis_ms": 340}),
    "porte_agents": ("émis par la porte des agents (brique 14) — forme relevée dans le code, valeurs d'exemple",
                     {"quoi": "ordre_refuse", "agent": "agent:assistant", "raison": "trop_d_ordres", "texte": "Va à la table",
                      "n": 10, "attendre_s": 12.5}),
    "yeux": ("émis par les yeux (brique 5), éteints par défaut — forme relevée dans le code, valeurs d'exemple",
             {"quoi": "objet_pas_vu", "objet": "bouteille", "depuis_s": 3.0}),
}


def _seance_ecran(dossier: Path) -> list:
    from fastapi.testclient import TestClient

    from briques.b13_ecran.serveur import creer_app
    from commun.systeme import Systeme, charger_reglages

    r = charger_reglages()
    r["cerveau"]["choix"] = "regles"
    r["robot"] = {**r["robot"], "adaptateur": "faux_robot", "carte": "humanoide"}
    r["ecran"] = {**r["ecran"], "code_equipe": CODE["X-Code-Equipe"]}
    s = Systeme(r, dossier_journal=dossier / "ecran", acceleration=20)

    def attendre(condition, delai_s=10.0):
        fin = time.monotonic() + delai_s
        while time.monotonic() < fin and not any(condition(e) for e in list(s.bus.historique)):
            time.sleep(0.02)

    with TestClient(creer_app(s)) as c:
        def dire(texte, langue="fr"):
            n = len(s.bus.historique)
            c.post("/api/dire", json={"texte": texte, "langue": langue}, headers=CODE)
            attendre(lambda e: e.type == "reponse_dite" and e.numero > s.bus.historique[n - 1].numero)

        dire("Va à la cuisine")
        attendre(lambda e: e.type == "action_terminee")
        dire("Va à la scène à 5 mètres par seconde")
        dire("va")
        dire("Prends la bouteille")
        dire("oui")
        attendre(lambda e: e.type == "action_terminee" and (e.donnees.get("action") or {}).get("nom") == "saisir")
        dire("Va à l'entrée")
        dire("Va à la table")  # le robot marche encore : la prise refuse (robot occupé)
        c.post("/api/panne", json={"nom": "lenteur"}, headers=CODE)
        c.post("/api/reparer", headers=CODE)
        c.post("/api/arret_urgence")
        c.post("/api/rearmer", headers=CODE)
        c.post("/api/internet_coupe", json={"coupe": True}, headers=CODE)
        c.post("/api/internet_coupe", json={"coupe": False}, headers=CODE)
        c.post("/api/mode_silence", json={"actif": True}, headers=CODE)
        c.post("/api/mode_silence", json={"actif": False}, headers=CODE)
    return list(s.bus.historique)


async def _seance_cascade(dossier: Path) -> list:
    """Une cascade dont le premier cerveau (sur cet ordinateur) est éteint : `cerveau_secours`."""
    from commun.systeme import Systeme, charger_reglages

    r = charger_reglages()
    r["robot"] = {**r["robot"], "adaptateur": "faux_robot", "carte": "humanoide"}
    r["cerveau"] = {"choix": "cascade", "seuil_confiance": 0.5, "serveurs": {},
                    "cascade": [{"nom": "apertus_8b", "url": "http://127.0.0.1:9", "delai_s": 2}, {"nom": "regles"}]}
    s = Systeme(r, dossier_journal=dossier / "cascade", acceleration=20)
    await s.demarrer()
    await s.chaine.traiter("Regarde la table", "fr")
    await s.arreter()
    return list(s.bus.historique)


async def _seance_voix(dossier: Path) -> list:
    """La conversation avec une écoute factice (on choisit ce qu'elle « entend ») et une voix d'essai."""
    import numpy as np

    from briques.b04_oreilles_voix.conversation import Conversation
    from briques.b04_oreilles_voix.ecoute import Transcription
    from briques.b04_oreilles_voix.peripheriques import HautParleurFactice
    from briques.b04_oreilles_voix.voix import Son
    from commun.systeme import Systeme, charger_reglages

    class EcouteFactice:
        nom = "écoute factice"
        textes = ["Geh in die Küche", "Ich gehe zu: Küche."]  # la 2e phrase : le micro entend la voix du robot (écho)

        def transcrire(self, son, langue=None, langue_probable=None):
            return Transcription(texte=self.textes.pop(0), langue="de", langue_proba=0.98, confiance=0.91,
                                 duree_son_s=1.0, duree_calcul_ms=412.0, moteur=self.nom)

    class VoixEssai:
        nom = "voix d'essai"

        def synthetiser(self, texte, langue, lent=False):
            return Son(echantillons=np.zeros(1600, dtype="float32"), taux=16000, duree_calcul_ms=35.0, moteur=self.nom)

    r = charger_reglages()
    r["cerveau"]["choix"] = "regles"
    r["robot"] = {**r["robot"], "adaptateur": "faux_robot", "carte": "humanoide"}
    s = Systeme(r, dossier_journal=dossier / "voix", acceleration=20)
    await s.demarrer()
    conv = Conversation(s, EcouteFactice(), VoixEssai(), HautParleurFactice(vitesse=50), s.reglages.get("voix", {}))
    for _ in range(2):
        conv.appuyer()  # le bouton « je parle »
        await conv.recevoir(np.zeros(16000, dtype="float32"))
        conv.relacher()
        await conv.attendre_calme(20)
    conv.fermer()
    await s.arreter()
    return list(s.bus.historique)


def _raccourcir(e: dict) -> dict:
    d = dict(e.get("donnees") or {})
    if "carte" in d:
        d["carte"] = {"…": "la carte d'identité complète (voir /api/carte)"}
    if "machine" in d:
        d["machine"] = "(nom de l'ordinateur)"
    return {**e, "donnees": d}


def exemples() -> dict[str, tuple[str, dict]]:
    """type → (provenance, événement en JSON). Un exemple par type de commun/evenements.py."""
    from briques.b13_ecran.flux_simple import ligne_simple  # noqa: F401 (vérifie l'import)
    from commun.evenements import TYPES, Evenement

    with tempfile.TemporaryDirectory(prefix="exemples_flux_") as dossier:
        d = Path(dossier)
        evs = _seance_ecran(d) + asyncio.run(_seance_cascade(d)) + asyncio.run(_seance_voix(d))
    res: dict[str, tuple[str, dict]] = {}
    for e in evs:
        if e.type not in res and e.type not in A_LA_MAIN:
            res[e.type] = ("vrai événement, testé sur faux robot", _raccourcir(e.model_dump(mode="json")))
    for t, (provenance, donnees) in A_LA_MAIN.items():
        ev = Evenement(type=t, source="exemple", donnees=donnees, robot="faux-humanoide")
        res[t] = (provenance, ev.model_dump(mode="json"))
    manquants = set(TYPES) - set(res)
    if manquants:
        raise RuntimeError(f"pas d'exemple pour : {sorted(manquants)}")
    return {t: res[t] for t in TYPES}


def markdown() -> str:
    from briques.b13_ecran.flux_simple import ligne_simple
    from commun.evenements import TYPES

    morceaux = []
    for t, (provenance, e) in exemples().items():
        morceaux.append(f"### `{t}`\n\n{TYPES[t]} — *{provenance}.*\n\nChamps utiles : {CHAMPS.get(t, '')}\n\n"
                        f"```json\n{json.dumps(e, ensure_ascii=False)}\n```\n\nLigne simple :\n\n"
                        f"```json\n{json.dumps(ligne_simple(e), ensure_ascii=False)}\n```\n")
    return "\n".join(morceaux)


def main(argv: list[str]) -> int:
    texte = markdown()
    if "--ecrire" in argv:
        doc = DOC.read_text(encoding="utf-8")
        avant, reste = doc.split(DEBUT, 1)
        _, apres = reste.split(FIN, 1)
        DOC.write_text(f"{avant}{DEBUT}\n\n{texte}\n{FIN}{apres}", encoding="utf-8")
        print(f"écrit : {DOC}")
    else:
        print(texte)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ICI.parents[1]))
    sys.exit(main(sys.argv[1:]))
