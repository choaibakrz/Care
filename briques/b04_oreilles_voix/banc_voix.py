"""Banc d'essai de la voix. Internet inutile. Ne fait bouger aucun vrai robot (faux robot seulement).

    python3 lancer.py banc-voix                      (moteur et modèle de reglages.yaml)
    python3 lancer.py banc-voix --modele base --phrases 6

Mesure, pour chaque langue :
1. l'écoute sur de VRAIES voix (FLEURS, + enregistrements de l'équipe dans donnees_voix/equipe/<langue>/) :
   mots faux (%) au calme, puis avec un bruit de foule à 10 dB et 5 dB ; langue bien reconnue (%) ;
   « deux mots suffisent » : langue reconnue sur la première seconde et demie ;
2. le temps entre la FIN de la phrase et le DÉBUT de la réponse parlée, sur des ordres courts, en temps réel,
   avec toute la chaîne (fin de parole → écoute → cerveau → gardien → voix). Ordres dits par la voix de synthèse
   disponible (chinois ici ; sur Mac, la voix du Mac pour toutes les langues) : SYNTHÉTIQUE, et dit comme tel.
Résultats : mesures/voix_<date>_<machine>.md et .json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import socket
import statistics
import sys
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np

from .audio import bruit_de_foule, lire, melanger, reechantillonner, silence

RACINE = Path(__file__).resolve().parents[2]
DONNEES = RACINE / "donnees_voix"
LANGUES = ["fr", "de", "gsw", "it", "en", "zh"]
ORDRES = {  # ordres courts dits au robot, avec l'action attendue
    "fr": [("Va à la cuisine.", "se_deplacer", "cuisine"), ("Regarde la table.", "regarder", "table"), ("Stop !", "arreter", None)],
    "de": [("Geh in die Küche.", "se_deplacer", "cuisine"), ("Schau den Tisch an.", "regarder", "table"), ("Stopp!", "arreter", None)],
    "it": [("Vai in cucina.", "se_deplacer", "cuisine"), ("Guarda il tavolo.", "regarder", "table"), ("Fermati!", "arreter", None)],
    "en": [("Go to the kitchen.", "se_deplacer", "cuisine"), ("Look at the table.", "regarder", "table"), ("Stop!", "arreter", None)],
    "zh": [("请去厨房。", "se_deplacer", "cuisine"), ("请看桌子。", "regarder", "table"), ("停下。", "arreter", None)],
}


FIGES = {"请去厨房。": "aller_cuisine", "请看桌子。": "regarder_table", "停下。": "stop"}


def normaliser(t: str) -> str:
    t = unicodedata.normalize("NFKC", t.lower())
    t = "".join(" " if unicodedata.category(c).startswith("P") else c for c in t)
    return re.sub(r"\s+", " ", t).strip()


def taux_erreur(reference: str, hypothese: str, langue: str) -> float:
    """Mots faux en % (caractères faux pour le chinois)."""
    r, h = normaliser(reference), normaliser(hypothese)
    if langue == "zh":
        r, h = list(r.replace(" ", "")), list(h.replace(" ", ""))
    else:
        r, h = r.split(), h.split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prec, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prec, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prec + (r[i - 1] != h[j - 1]))
    return 100.0 * d[len(h)] / max(1, len(r))


def debut_de_parole(son: np.ndarray, duree_s: float) -> np.ndarray:
    """Les `duree_s` premières secondes de PAROLE (on saute le silence du début)."""
    from .fin_de_parole import DetecteurParole

    d = DetecteurParole(silence_fin_ms=300)
    debut = 0
    for i in range(0, len(son) - 511, 512):
        d.ajouter(son[i:i + 512])
        if d.en_parole:
            debut = max(0, i - int(0.3 * 16000))
            break
    return son[debut: debut + int(duree_s * 16000)]


def charger_clips(langue: str, n: int) -> list[tuple[np.ndarray, str, str]]:
    """(son, texte, origine) : FLEURS puis enregistrements de l'équipe."""
    clips = []
    for origine, dossier in (("FLEURS", DONNEES / "fleurs" / langue), ("équipe", DONNEES / "equipe" / langue)):
        meta = dossier / "textes.json"
        if meta.exists():
            for m in json.loads(meta.read_text(encoding="utf-8"))[:n]:
                clips.append((lire(dossier / m["fichier"]), m["texte"], origine))
    return clips


def mesurer_ecoute(ecoute, langues: list[str], n: int) -> dict:
    tous = {lg: charger_clips(lg, n) for lg in langues}
    res = {}
    for lg, clips in tous.items():
        if not clips:
            res[lg] = {"etat": "aucun enregistrement (donnees_voix/equipe/%s à remplir avec : lancer.py enregistrer %s)" % (lg, lg)}
            continue
        autres = [c[0] for l2, cs in tous.items() if l2 != lg for c in cs][:16] or [c[0] for c in clips]
        foule = bruit_de_foule(autres, 30.0, nb_voix=8)
        lignes = {"propre": [], "foule_10dB": [], "foule_5dB": [], "meme_langue_10dB": []}
        langue_ok, deux_mots_ok, conf, calcul = [], [], [], []
        attendue = "de" if lg == "gsw" else lg
        for k, (son, texte, _) in enumerate(clips):
            # Foule qui parle LA MÊME langue (les autres phrases de la langue) : plus difficile à ignorer.
            meme = bruit_de_foule([c[0] for j, c in enumerate(clips) if j != k] or [son], 30.0, nb_voix=8, graine=k)
            for cond, rsb, bruit in (("propre", None, None), ("foule_10dB", 10, foule), ("foule_5dB", 5, foule),
                                     ("meme_langue_10dB", 10, meme)):
                s = son if rsb is None else melanger(son, bruit, rsb)
                t = ecoute.transcrire(s)
                lignes[cond].append(taux_erreur(texte, t.texte, lg))
                if cond == "propre":
                    langue_ok.append(t.langue in (lg, attendue))
                    conf.append(t.confiance)
                    calcul.append(t.duree_calcul_ms / max(0.1, t.duree_son_s))
            l2, _ = ecoute.detecter_langue(debut_de_parole(son, 1.5))
            deux_mots_ok.append(l2 in (lg, attendue))
        res[lg] = {
            "phrases": len(clips), "origine": sorted({c[2] for c in clips}),
            "mots_faux_pct": {k: round(statistics.mean(v), 1) for k, v in lignes.items()},
            "langue_reconnue_pct": round(100 * sum(langue_ok) / len(langue_ok)),
            "langue_sur_1_5_s_pct": round(100 * sum(deux_mots_ok) / len(deux_mots_ok)),
            "confiance_moyenne": round(statistics.mean(conf), 2),
            "calcul_ms_par_seconde_de_son": round(statistics.median(calcul)),
        }
        print(f"  {lg}: {res[lg]}", flush=True)
    return res


async def mesurer_latence(ecoute, voix, reglages: dict) -> dict:
    """Ordres courts, en TEMPS RÉEL, à travers toute la chaîne. Latence = fin de phrase → début de la réponse."""
    from commun.systeme import Systeme

    from .conversation import Conversation
    from .peripheriques import HautParleurFactice, MicroFichier

    res = {}
    await asyncio.to_thread(ecoute.prechauffer)  # comme au démarrage du vrai robot
    voix.prechauffer()
    for lg, ordres in ORDRES.items():
        if lg not in voix.langues():
            res[lg] = {"etat": "pas de voix de synthèse pour dire les ordres (sur Mac : voix du Mac)"}
            continue
        lignes = []
        for phrase, action, lieu in ordres:
            s = Systeme(reglages, dossier_journal=tempfile.mkdtemp(), acceleration=20)
            c = Conversation(s, ecoute, voix, HautParleurFactice(vitesse=20), reglages.get("voix", {}), vitesse_micro=1.0)
            await s.demarrer()
            fige = DONNEES / "synthetique_zh" / f"{FIGES.get(phrase, '-')}.wav"
            if lg == "zh" and fige.exists():
                audio = lire(fige)  # même son à chaque fois (la voix de synthèse varie sinon)
            else:
                son = voix.synthetiser(phrase.rstrip("。.!！"), lg)
                audio = reechantillonner(son.echantillons, son.taux)
            await c.ecouter(MicroFichier(np.concatenate([silence(400), audio]), vitesse=1.0, silence_final_s=2.5))
            for _ in range(80):  # laisser à l'action le temps de démarrer, et au robot de commencer à répondre
                if any(e.type in ("action_demarree", "action_refusee") for e in s.bus.historique) and \
                        any(e.type == "voix_debut" for e in s.bus.historique):
                    break
                await asyncio.sleep(0.05)
            c.fermer()
            await s.arreter()
            ev = s.bus.historique
            lat = next((e.donnees.get("latence_ms") for e in ev if e.type == "voix_debut" and e.donnees.get("latence_ms")), None)
            lancee = next((e.donnees for e in ev if e.type == "action_demarree"), {})
            act = lancee.get("action") or {}
            bonne = act.get("nom") == action and (lieu is None or lieu in str(act.get("parametres")))  # action LANCÉE
            tr = next((e.donnees for e in ev if e.type == "transcription"), {})
            pf = next((e.donnees for e in ev if e.type == "parole_finie"), {})
            lignes.append({"phrase": phrase, "entendu": tr.get("texte"), "bonne_action": bonne, "latence_ms": lat,
                           "attente_silence_ms": pf.get("attente_fin_ms"), "ecoute_ms": tr.get("calcul_ms")})
            print(f"  {lg} {phrase!r} → {tr.get('texte')!r} action ok={bonne} latence={lat} ms", flush=True)
        lats = [l["latence_ms"] for l in lignes if l["latence_ms"]]
        res[lg] = {"ordres": lignes, "latence_mediane_ms": round(statistics.median(lats)) if lats else None,
                   "bonnes_actions_lancees": f"{sum(l['bonne_action'] for l in lignes)}/{len(lignes)}",
                   "source_des_ordres": f"SYNTHÉTIQUE ({voix.nom})"}
    return res


def mesurer_ordres(ecoute, voix) -> dict:
    """Combien d'ORDRES sont bien compris (pas seulement combien de mots) : les 18 ordres normaux du banc du cerveau,
    dits par la voix de synthèse disponible, écoutés sans dire la langue. Un ordre est « compris » si le texte entendu
    suffit au cerveau à règles pour trouver la bonne action (mesure de l'écoute, pas du cerveau)."""
    import asyncio as _a

    from briques.b01_prise.carte import CarteIdentite
    from briques.b02_faux_robot.faux_robot import DOSSIER_CARTES
    from briques.b06_cerveau.banc_cerveau import charger_demandes, juger
    from briques.b06_cerveau.branchements.regles import CerveauRegles
    from commun.monde import Monde

    carte, monde, regles = CarteIdentite.charger(DOSSIER_CARTES / "humanoide.yaml"), Monde.charger(), CerveauRegles()
    ordres = [d for d in charger_demandes() if d["categorie"] == "normal"]
    res = {}
    for lg in ["fr", "de", "it", "en", "zh"]:
        if lg not in voix.langues():
            res[lg] = {"etat": "pas de voix de synthèse pour dire les ordres (sur Mac : voix du Mac)"}
            continue
        lignes, plafond = [], 0
        for d in ordres:
            # Plafond : ce que le cerveau à règles comprend avec le texte EXACT (l'écoute ne peut pas faire mieux).
            plafond += juger(d["attendu"], _a.run(regles.decider(d["phrases"][lg], lg, carte, monde)), None)
            son = voix.synthetiser(d["phrases"][lg], lg)
            t = ecoute.transcrire(reechantillonner(son.echantillons, son.taux))
            dec = _a.run(regles.decider(t.texte, t.langue, carte, monde))
            lignes.append({"phrase": d["phrases"][lg], "entendu": t.texte, "langue": t.langue,
                           "compris": juger(d["attendu"], dec, None), "mots_faux_pct": round(taux_erreur(d["phrases"][lg], t.texte, lg), 1)})
        res[lg] = {"ordres": len(lignes), "compris_pct": round(100 * sum(l["compris"] for l in lignes) / len(lignes)),
                   "plafond_texte_exact_pct": round(100 * plafond / len(lignes)),
                   "langue_juste_pct": round(100 * sum(l["langue"] == lg for l in lignes) / len(lignes)),
                   "mots_faux_pct": round(statistics.mean(l["mots_faux_pct"] for l in lignes), 1),
                   "source": f"SYNTHÉTIQUE ({voix.nom})", "detail": lignes}
        print(f"  ordres [{lg}] compris {res[lg]['compris_pct']} %  mots faux {res[lg]['mots_faux_pct']} %", flush=True)
    return res


def memoire_processus_go() -> float | None:
    try:
        import psutil

        return round(psutil.Process().memory_info().rss / 1e9, 2)
    except ImportError:
        return None


def rapport(r: dict) -> str:
    L = [f"# Banc d'essai de la voix — {r['date']} — {r['machine']}", "",
         f"Écoute : **{r['ecoute']}**. Voix : **{r['voix']}**. Faux robot. Internet non utilisé.",
         f"Mémoire du programme une fois l'écoute chargée : {r.get('memoire_go')} Go (avant : {r.get('memoire_avant_go')} Go) ;"
         f" pic MLX : {r.get('memoire_pic_mlx_go', '—')} Go.", "",
         "## 1. Écoute sur de vraies voix (FLEURS ; équipe si enregistrée)", "",
         "| Langue | Phrases | Mots faux calme | Foule 10 dB | Foule 5 dB | Foule même langue 10 dB | Langue reconnue | Langue en 1,5 s | Confiance | Calcul (ms par s de son) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for lg, v in r["ecoute_reelle"].items():
        if "etat" in v:
            L.append(f"| {lg} | — | {v['etat']} | | | | | | | |")
            continue
        m = v["mots_faux_pct"]
        L.append(f"| {lg} | {v['phrases']} | {m['propre']} % | {m['foule_10dB']} % | {m['foule_5dB']} % | {m['meme_langue_10dB']} % | "
                 f"{v['langue_reconnue_pct']} % | {v['langue_sur_1_5_s_pct']} % | {v['confiance_moyenne']} | {v['calcul_ms_par_seconde_de_son']} |")
    L += ["", "Chinois : caractères faux (pas de mots séparés). « 10 dB » : la voix est nettement plus forte que la foule ;",
          "« 5 dB » : la foule est presque aussi forte. Foule = 8 voix des autres langues mélangées ;",
          "« même langue » : 8 voix de la même langue (plus difficile).", "",
          "## 2. Ordres bien compris (18 ordres par langue, voix de synthèse)", "",
          "| Langue | Ordres compris | Plafond (texte exact) | Langue juste | Mots faux | Ordres dits par |", "|---|---|---|---|---|---|"]
    for lg, v in r.get("ordres", {}).items():
        L.append(f"| {lg} | — | — | — | — | {v['etat']} |" if "etat" in v else
                 f"| {lg} | **{v['compris_pct']} %** | {v['plafond_texte_exact_pct']} % | {v['langue_juste_pct']} % | "
                 f"{v['mots_faux_pct']} % | {v['source']} |")
    L += ["", "« Compris » : le texte entendu suffit au cerveau à règles pour trouver la bonne action. « Plafond » : ce",
          "même cerveau avec le texte exact ; l'écoute ne peut pas dépasser ce chiffre.", "",
          "## 3. Fin de la phrase → début de la réponse (ordres courts, temps réel)", "",
          "| Langue | Latence médiane | Bonne action lancée | Ordres dits par |", "|---|---|---|---|"]
    for lg, v in r["latence"].items():
        if "etat" in v:
            L.append(f"| {lg} | — | — | {v['etat']} |")
        else:
            L.append(f"| {lg} | {v['latence_mediane_ms']} ms | {v['bonnes_actions_lancees']} | {v['source_des_ordres']} |")
    L += ["", "La latence comprend : l'attente du silence de fin (600 ms réglables), l'écoute, le cerveau, le gardien,",
          "et le calcul du premier son. Détail par ordre dans le fichier .json."]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    from commun.systeme import charger_reglages

    from .ecoute import creer_ecoute
    from .voix import creer_voix

    p = argparse.ArgumentParser()
    p.add_argument("--moteur")
    p.add_argument("--modele")
    p.add_argument("--phrases", type=int, default=6)
    p.add_argument("--sans-latence", action="store_true")
    p.add_argument("--sans-ecoute", action="store_true", help="seulement le temps de réponse")
    a = p.parse_args(argv)
    reglages = charger_reglages()
    e = reglages.setdefault("voix", {}).setdefault("ecoute", {})
    if a.moteur:
        e["moteur"] = a.moteur
    if a.modele:
        e["modele"] = a.modele
    avant = memoire_processus_go()
    ecoute, voix = creer_ecoute(reglages), creer_voix(reglages)
    ecoute.prechauffer()
    print(f"Écoute : {ecoute.nom} — voix : {voix.nom}", flush=True)
    t0 = time.time()
    r = {"date": datetime.now().isoformat(timespec="minutes"), "machine": socket.gethostname(), "ecoute": ecoute.nom,
         "voix": voix.nom, "memoire_avant_go": avant, "memoire_go": memoire_processus_go()}
    try:
        import mlx.core as mx

        r["memoire_pic_mlx_go"] = round(mx.get_peak_memory() / 1e9, 2)
    except Exception:
        pass
    r["ecoute_reelle"] = {} if a.sans_ecoute else mesurer_ecoute(ecoute, LANGUES, a.phrases)
    r["ordres"] = {} if a.sans_ecoute else mesurer_ordres(ecoute, voix)
    r["latence"] = {} if a.sans_latence else asyncio.run(mesurer_latence(ecoute, voix, reglages))
    r["duree_banc_s"] = round(time.time() - t0)
    sortie = RACINE / "mesures"
    sortie.mkdir(exist_ok=True)
    nom = f"voix_{datetime.now():%Y-%m-%d_%H%M}_{socket.gethostname().split('.')[0]}_{ecoute.nom.replace(' ', '-')}"
    (sortie / f"{nom}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
    (sortie / f"{nom}.md").write_text(rapport(r), encoding="utf-8")
    print(f"\nRésultats : {sortie / nom}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
