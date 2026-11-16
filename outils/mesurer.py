#!/usr/bin/env python3
"""Mesurer les vitesses et la mémoire sur l'ordinateur-cerveau. Ne fait bouger aucun robot.

    python3 outils/mesurer.py                       tout ce qui est installé
    python3 outils/mesurer.py --autre-mac 192.168.1.20   + mesure du partage entre deux Mac

Chaque mesure est indépendante : si un outil n'est pas installé, la ligne dit « absent », rien ne plante.
Résultats : mesures/<date>_<machine>.json et .md (à recopier dans la fiche de vérité et DECISIONS.md).

Ce qui est comparé :
- cerveau : llama.cpp sur la puce graphique (Metal) / llama.cpp sur le processeur seul / MLX ;
- écoute : whisper.cpp (pywhispercpp) / mlx-whisper / faster-whisper (processeur seul) ;
- voix : voix Piper lues par sherpa-onnx ;
- mémoire : tout chargé en même temps, et la marge restante ;
- deux Mac : temps d'aller-retour sur le Wi-Fi, cerveau local contre cerveau sur l'autre Mac.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave

import numpy as np
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
MODELES = RACINE / "modeles"
SORTIE = RACINE / "mesures"
PORT_CERVEAU = 8089

# Phrases d'essai et voix macOS pour fabriquer les sons d'essai sans rien télécharger (commande « say »).
# Les voix macOS disponibles varient selon la machine : à vérifier avec « say -v '?' ».
PHRASES = {
    "fr": ("Va à la cuisine et prends la bouteille.", ["Thomas", "Amélie", "Aurélie"]),
    "de": ("Geh in die Küche und nimm die Flasche.", ["Anna", "Markus", "Petra"]),
    "it": ("Vai in cucina e prendi la bottiglia.", ["Alice", "Luca", "Federica"]),
    "en": ("Go to the kitchen and take the bottle.", ["Samantha", "Daniel", "Alex"]),
    "zh": ("去厨房拿瓶子。", ["Tingting", "Ting-Ting", "Lili"]),
}
CONSIGNE = ("Tu commandes un robot. Réponds UNIQUEMENT en JSON : "
            '{"action": une de [se_deplacer, regarder, saisir, poser, montrer, arreter, etat, question], '
            '"parametres": {...}}. Lieux connus : cuisine, entree, table, scene. Objets : bouteille, tasse.')
DEMANDES = ["Va à la cuisine", "Geh zum Tisch", "Go to the stage", "去入口", "Prendi la bottiglia",
            "Regarde la table", "Stop !", "Wie ist dein Akku?", "Montre la scène", "Pose la tasse ici"]
SCHEMA = {"type": "object", "properties": {
    "action": {"enum": ["se_deplacer", "regarder", "saisir", "poser", "montrer", "arreter", "etat", "question"]},
    "parametres": {"type": "object"}}, "required": ["action", "parametres"]}


def dire(*m):
    print(*m, flush=True)


# ------------------------------------------------------------------ machine
def machine() -> dict:
    info = {"systeme": platform.platform(), "processeur": platform.processor(), "python": sys.version.split()[0],
            "nom": socket.gethostname()}
    if sys.platform == "darwin":
        lire = lambda k: subprocess.run(["sysctl", "-n", k], capture_output=True, text=True).stdout.strip()
        info["puce"] = lire("machdep.cpu.brand_string")
        info["memoire_go"] = round(int(lire("hw.memsize") or 0) / 1e9, 1)
        info["coeurs"] = lire("hw.ncpu")
    else:
        try:
            import psutil
            info["memoire_go"] = round(psutil.virtual_memory().total / 1e9, 1)
        except ImportError:
            pass
        info["coeurs"] = os.cpu_count()
    info["disque_libre_go"] = round(shutil.disk_usage(RACINE).free / 1e9, 1)
    info["apple_silicon"] = sys.platform == "darwin" and platform.machine() == "arm64"
    return info


def memoire_systeme() -> dict:
    try:
        import psutil
        v = psutil.virtual_memory()
        return {"total_go": round(v.total / 1e9, 2), "utilisee_go": round((v.total - v.available) / 1e9, 2),
                "disponible_go": round(v.available / 1e9, 2)}
    except ImportError:
        return {"erreur": "psutil absent"}


def chercher(motif: str) -> Path | None:
    trouve = sorted(MODELES.rglob(motif))
    return trouve[0] if trouve else None


# ------------------------------------------------------------------ cerveau : llama.cpp
def llama_server_binaire() -> str | None:
    for nom in ("llama-server",):
        p = shutil.which(nom) or (RACINE / "outils" / "bin" / nom if (RACINE / "outils" / "bin" / nom).exists() else None)
        if p:
            return str(p)
    return None


def _post(url: str, corps: dict, delai: float = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corps).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return json.load(r)


def attendre_serveur(base: str, delai: float = 180) -> bool:
    fin = time.time() + delai
    while time.time() < fin:
        try:
            with urllib.request.urlopen(base + "/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def interroger_cerveau(base: str, n: int = len(DEMANDES)) -> dict:
    temps, vitesses, json_ok = [], [], 0
    for d in DEMANDES[:n]:
        t0 = time.perf_counter()
        r = _post(base + "/v1/chat/completions", {
            "messages": [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": d}],
            "max_tokens": 80, "temperature": 0,
            "response_format": {"type": "json_object", "schema": SCHEMA}})
        temps.append((time.perf_counter() - t0) * 1000)
        t = r.get("timings") or {}
        if t.get("predicted_per_second"):
            vitesses.append(t["predicted_per_second"])
        try:
            json.loads(r["choices"][0]["message"]["content"])
            json_ok += 1
        except Exception:
            pass
    return {"demandes": len(temps), "temps_mediane_ms": round(statistics.median(temps)),
            "temps_max_ms": round(max(temps)), "jetons_par_s": round(statistics.median(vitesses), 1) if vitesses else None,
            "json_valides": f"{json_ok}/{len(temps)}"}


def mesurer_llama(modele: Path, gpu: bool, garder: bool = False) -> tuple[dict, subprocess.Popen | None]:
    binaire = llama_server_binaire()
    if not binaire:
        return {"etat": "absent (llama-server introuvable)"}, None
    avant = memoire_systeme()
    cmd = [binaire, "-m", str(modele), "-c", "4096", "--port", str(PORT_CERVEAU), "--host", "0.0.0.0",
           "-ngl", "99" if gpu else "0"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.perf_counter()
    base = f"http://127.0.0.1:{PORT_CERVEAU}"
    if not attendre_serveur(base):
        proc.terminate()
        return {"etat": "le serveur n'a pas démarré"}, None
    res = {"etat": "ok", "modele": modele.name, "puce_graphique": gpu,
           "chargement_s": round(time.perf_counter() - t0, 1)}
    res.update(interroger_cerveau(base))
    apres = memoire_systeme()
    if "utilisee_go" in avant and "utilisee_go" in apres:
        res["memoire_ajoutee_go"] = round(apres["utilisee_go"] - avant["utilisee_go"], 2)
    if garder:
        return res, proc
    proc.terminate()
    proc.wait(timeout=20)
    return res, None


# ------------------------------------------------------------------ cerveau : MLX
def mesurer_mlx(dossier: Path) -> dict:
    try:
        import mlx.core as mx
        from mlx_lm import generate, load
    except ImportError:
        return {"etat": "absent (mlx-lm non installé, ou pas un Mac à puce Apple)"}
    t0 = time.perf_counter()
    modele, tok = load(str(dossier))
    res = {"etat": "ok", "modele": dossier.name, "chargement_s": round(time.perf_counter() - t0, 1)}
    temps, nb = [], 0
    for d in DEMANDES:
        messages = [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": d}]
        prompt = tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        t0 = time.perf_counter()
        texte = generate(modele, tok, prompt=prompt, max_tokens=80, verbose=False)
        temps.append((time.perf_counter() - t0) * 1000)
        nb += len(tok.encode(texte))
    res.update({"demandes": len(temps), "temps_mediane_ms": round(statistics.median(temps)),
                "jetons_par_s_approx": round(nb / (sum(temps) / 1000), 1)})
    try:
        res["memoire_pic_go"] = round(mx.get_peak_memory() / 1e9, 2)
    except AttributeError:
        pass
    del modele
    return res


# ------------------------------------------------------------------ écoute
def fabriquer_sons(dossier: Path) -> dict[str, Path]:
    """Sons d'essai fabriqués par la voix du Mac (« say »). Sur Linux : aucun son, mesure sautée."""
    sons = {}
    if sys.platform != "darwin" or not shutil.which("say"):
        return sons
    voix_dispo = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    for lg, (texte, voix) in PHRASES.items():
        v = next((x for x in voix if x in voix_dispo), None)
        if not v:
            continue
        aiff, wav = dossier / f"{lg}.aiff", dossier / f"{lg}.wav"
        subprocess.run(["say", "-v", v, "-o", str(aiff), texte], check=False)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=False)
        if wav.exists():
            sons[lg] = wav
    return sons


def duree_wav(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def erreur_mots(ref: str, hyp: str) -> float:
    """Taux d'erreur sur les mots (ou sur les caractères pour le chinois)."""
    import re
    norm = lambda s: re.sub(r"[^\w\s]", "", s.lower()).split()
    r, h = norm(ref), norm(hyp)
    if len(r) <= 1:  # chinois : on compare caractère par caractère
        r, h = list("".join(r)), list("".join(h))
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prec, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prec, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prec + (r[i - 1] != h[j - 1]))
    return round(100 * d[len(h)] / max(1, len(r)), 1)


def mesurer_ecoute(sons: dict[str, Path]) -> dict:
    """Compare nos branchements d'écoute (mêmes réglages que le robot) sur les sons fabriqués par « say »."""
    if not sons:
        return {"etat": "pas de sons d'essai (seulement sur Mac, avec la commande say)"}
    sys.path.insert(0, str(RACINE))
    from briques.b04_oreilles_voix.audio import lire
    from briques.b04_oreilles_voix.ecoute import creer_ecoute

    moteurs = {}
    for moteur in ("mlx_whisper", "whisper_cpp", "faster_whisper"):
        for taille in ("small", "large-v3-turbo"):
            nom = f"{moteur} {taille}"
            try:
                e = creer_ecoute({"voix": {"ecoute": {"moteur": moteur, "modele": taille}}})
            except Exception as ex:
                moteurs[nom] = {"etat": f"absent : {ex!r}"[:150]}
                continue
            lignes = {}
            for lg, wav in sons.items():
                son = lire(wav)
                e.transcrire(son)  # premier passage : chauffe (chargement sur la puce)
                t = e.transcrire(son)
                lignes[lg] = {"temps_ms": t.duree_calcul_ms, "langue_reconnue": t.langue,
                              "erreur_mots_pct": erreur_mots(PHRASES[lg][0], t.texte), "texte": t.texte}
            moteurs[nom] = lignes
    return moteurs


# ------------------------------------------------------------------ voix
def mesurer_voix() -> dict:
    """Nos voix (Piper par sherpa-onnx, voix du Mac) : temps de calcul par langue."""
    sys.path.insert(0, str(RACINE))
    try:
        from briques.b04_oreilles_voix.voix import creer_voix
    except ImportError as e:
        return {"etat": f"absent : {e!r}"}
    v = creer_voix({"voix": {"parole": {"moteurs": ["sherpa_piper", "mac_say"]}}})
    textes = {"fr": "Je vais à la cuisine.", "de": "Ich gehe in die Küche.", "it": "Vado in cucina.",
              "en": "I am going to the kitchen.", "zh": "我去厨房。"}
    res = {"moteurs": v.nom}
    for lg, texte in textes.items():
        son = v.synthetiser(texte, lg)
        res[lg] = ({"temps_ms": son.duree_calcul_ms, "duree_audio_s": round(son.duree_s, 2), "moteur": son.moteur}
                   if son else {"etat": "pas de voix : sous-titres seulement"})
    return res


# ------------------------------------------------------------------ deux Mac
def mesurer_deux_mac(ip: str) -> dict:
    res = {"autre_mac": ip}
    p = subprocess.run(["ping", "-c", "5", ip], capture_output=True, text=True)
    lignes = [l for l in p.stdout.splitlines() if "min/avg" in l or "rtt" in l]
    res["ping"] = lignes[-1] if lignes else "pas de réponse"
    base = f"http://{ip}:{PORT_CERVEAU}"
    try:
        with urllib.request.urlopen(base + "/health", timeout=3):
            pass
        res["cerveau_sur_l_autre_mac"] = interroger_cerveau(base)
    except Exception as e:
        res["cerveau_sur_l_autre_mac"] = (f"pas de cerveau joignable sur {base} ({e.__class__.__name__}). "
                                          "Lancer d'abord ce script sur l'autre Mac avec --garder-cerveau.")
    return res


# ------------------------------------------------------------------ rapport
def rapport_md(r: dict) -> str:
    l = [f"# Mesures du {r['date']} — {r['machine'].get('puce') or r['machine'].get('processeur')}", "",
         "Toutes ces mesures : **testé sur faux robot** (aucun robot ne bouge pendant la mesure).", "",
         "## Machine", "", "```", json.dumps(r["machine"], indent=2, ensure_ascii=False), "```", "", "## Cerveau", ""]
    for nom, v in r["cerveau"].items():
        l.append(f"- **{nom}** : {json.dumps(v, ensure_ascii=False)}")
    l += ["", "## Écoute", ""]
    for nom, v in r["ecoute"].items():
        l.append(f"- **{nom}** : {json.dumps(v, ensure_ascii=False)[:600]}")
    l += ["", "## Voix", "", f"{json.dumps(r['voix'], ensure_ascii=False)}", "", "## Mémoire, tout chargé ensemble", "",
          f"{json.dumps(r.get('memoire_ensemble'), ensure_ascii=False)}", ""]
    if r.get("deux_mac"):
        l += ["## Deux Mac", "", f"{json.dumps(r['deux_mac'], ensure_ascii=False)}", ""]
    return "\n".join(l)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--autre-mac", help="adresse IP de l'autre Mac (mesure du partage)")
    p.add_argument("--garder-cerveau", action="store_true", help="laisser le cerveau tourner à la fin (pour l'autre Mac)")
    args = p.parse_args()

    r = {"date": datetime.now().isoformat(timespec="seconds"), "machine": machine(), "cerveau": {}}
    dire(f"Machine : {r['machine']}")
    r["memoire_au_repos"] = memoire_systeme()

    gguf = chercher("Apertus-8B*Q4_K_M.gguf") or chercher("apertus*4b*q4_k_m.gguf")
    if gguf:
        dire("Cerveau : llama.cpp sur la puce graphique…")
        r["cerveau"]["llama.cpp (puce graphique)"], _ = mesurer_llama(gguf, gpu=True)
        dire("Cerveau : llama.cpp sur le processeur seul (pour comparer)…")
        r["cerveau"]["llama.cpp (processeur seul)"], _ = mesurer_llama(gguf, gpu=False)
    else:
        r["cerveau"]["llama.cpp"] = {"etat": "modèle GGUF non téléchargé"}
    for dossier in [MODELES / "apertus-8b-mlx", MODELES / "apertus-4b-mlx"]:
        if dossier.exists():
            dire(f"Cerveau : MLX {dossier.name}…")
            r["cerveau"][f"MLX {dossier.name}"] = mesurer_mlx(dossier)

    with tempfile.TemporaryDirectory() as tmp:
        dire("Écoute : fabrication des sons d'essai et transcription…")
        r["ecoute"] = mesurer_ecoute(fabriquer_sons(Path(tmp)))
    dire("Voix…")
    r["voix"] = mesurer_voix()

    # Tout ensemble : le cerveau reste chargé pendant qu'on charge l'écoute et la voix.
    proc = None
    if gguf:
        dire("Mémoire : tout charger en même temps…")
        _, proc = mesurer_llama(gguf, gpu=True, garder=True)
        try:
            # Le kit léger tel qu'il tournera : cerveau + écoute (réglages du Mac) + voix, tous chargés ensemble.
            sys.path.insert(0, str(RACINE))
            from briques.b04_oreilles_voix.ecoute import creer_ecoute
            from briques.b04_oreilles_voix.voix import creer_voix
            from commun.systeme import charger_reglages

            reglages = charger_reglages()
            charges = []
            try:
                e = creer_ecoute(reglages)
                charges.append(e)
                e.transcrire(np.zeros(16000, dtype="float32"))
            except Exception as ex:
                r["memoire_ecoute_erreur"] = repr(ex)[:150]
            v = creer_voix(reglages)
            charges.append(v)
            for lg in ("fr", "de", "it", "en", "zh"):
                v.synthetiser("Bonjour.", lg)
            m = memoire_systeme()
            m["charges"] = [getattr(x, "nom", "?") for x in charges]
            if "total_go" in m:
                m["marge_go"] = round(m["disponible_go"], 2)
            r["memoire_ensemble"] = m
        finally:
            if proc and not args.garder_cerveau:
                proc.terminate()

    if args.autre_mac:
        dire("Deux Mac : mesure du réseau et du cerveau distant…")
        r["deux_mac"] = mesurer_deux_mac(args.autre_mac)

    SORTIE.mkdir(exist_ok=True)
    nom = f"{datetime.now():%Y-%m-%d_%H%M}_{socket.gethostname().split('.')[0]}"
    (SORTIE / f"{nom}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    (SORTIE / f"{nom}.md").write_text(rapport_md(r), encoding="utf-8")
    dire(f"\nRésultats : {SORTIE / nom}.md")
    if args.garder_cerveau and proc:
        dire(f"Le cerveau reste allumé sur le port {PORT_CERVEAU} (Ctrl+C pour l'arrêter).")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
