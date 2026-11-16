#!/usr/bin/env python3
"""ESSAI EN OPTION (Mac seulement) : le modèle suisse allemand Flix-AI contre Whisper normal.

    python3 outils/essai_suisse_allemand.py

Décision de Hiba (11.11.2026) : on reste avec Whisper normal (gain petit, 3 Go, 4 Go de marge seulement).
Ce script ne sert qu'à MESURER, et seulement si :
- c'est un Mac à puce Apple avec mlx-whisper installé ;
- il reste au moins 6 Go de mémoire libre et 10 Go de disque ;
- des ordres en suisse allemand ont été enregistrés par l'équipe (python3 lancer.py enregistrer gsw) ;
- une personne tape « oui » pour télécharger 3,09 Go (Flix-AI/flix-swissgerman-full, Apache-2.0).
Il convertit le modèle au format MLX (8 bits, environ 0,9 Go), en suivant la méthode d'Apple
(ml-explore/mlx-examples, whisper/convert.py, licence MIT, © Apple Inc.).
NON TESTÉ : écrit sans Mac. Rien n'est changé dans les réglages : la décision reste à Hiba.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
DEPOT, REVISION = "Flix-AI/flix-swissgerman-full", "a9c347a904"
SORTIE = RACINE / "modeles" / "whisper-flix-gsw-mlx"


def verifier() -> str | None:
    if sys.platform != "darwin":
        return "seulement sur Mac"
    try:
        import mlx.core  # noqa: F401
        import mlx_whisper  # noqa: F401
        import psutil
    except ImportError as e:
        return f"paquet manquant : {e.name}"
    libre = psutil.virtual_memory().available / 1e9
    if libre < 6:
        return f"pas assez de mémoire libre ({libre:.1f} Go, il en faut 6)"
    disque = shutil.disk_usage(RACINE).free / 1e9
    if disque < 10:
        return f"pas assez de disque ({disque:.1f} Go, il en faut 10)"
    if not (RACINE / "donnees_voix/equipe/gsw/textes.json").exists():
        return "aucun enregistrement suisse allemand : lancer d'abord « python3 lancer.py enregistrer gsw »"
    return None


def convertir(dossier_hf: Path) -> None:
    """Whisper au format Hugging Face → format mlx-whisper (noms des poids d'après mlx-examples, MIT, Apple)."""
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten, tree_unflatten
    from mlx_whisper import whisper

    cfg = json.loads((dossier_hf / "config.json").read_text())
    dims = {"n_mels": cfg["num_mel_bins"], "n_audio_ctx": cfg["max_source_positions"], "n_audio_state": cfg["d_model"],
            "n_audio_head": cfg["encoder_attention_heads"], "n_audio_layer": cfg["encoder_layers"],
            "n_vocab": cfg["vocab_size"], "n_text_ctx": cfg["max_target_positions"], "n_text_state": cfg["d_model"],
            "n_text_head": cfg["decoder_attention_heads"], "n_text_layer": cfg["decoder_layers"]}
    poids = mx.load(str(dossier_hf / "model.safetensors"))
    remplacements = [("model.", ""), (".layers", ".blocks"), (".self_attn", ".attn"), (".attn_layer_norm", ".attn_ln"),
                     (".encoder_attn.", ".cross_attn."), (".encoder_attn_layer_norm", ".cross_attn_ln"),
                     (".final_layer_norm", ".mlp_ln"), (".q_proj", ".query"), (".k_proj", ".key"), (".v_proj", ".value"),
                     (".out_proj", ".out"), (".fc1", ".mlp1"), (".fc2", ".mlp2"),
                     ("embed_positions.weight", "positional_embedding"), ("decoder.embed_tokens", "decoder.token_embedding"),
                     ("encoder.layer_norm", "encoder.ln_post"), ("decoder.layer_norm", "decoder.ln")]
    nouveaux = {}
    for k, v in poids.items():
        if k.startswith("proj_out"):
            continue  # Whisper réutilise la table des mots en sortie
        for a, b in remplacements:
            k = k.replace(a, b)
        if "conv" in k and v.ndim == 3:
            v = v.swapaxes(1, 2)  # ordre des axes des convolutions : PyTorch → MLX
        nouveaux[k] = v.astype(mx.float16)
    modele = whisper.Whisper(whisper.ModelDimensions(**dims), mx.float16)
    modele.update(tree_unflatten(list(nouveaux.items())))
    nn.quantize(modele, group_size=64, bits=8)  # 8 bits : environ 0,9 Go au lieu de 3
    SORTIE.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(str(SORTIE / "weights.safetensors"), dict(tree_flatten(modele.parameters())))
    (SORTIE / "config.json").write_text(json.dumps({**dims, "model_type": "whisper",
                                                     "quantization": {"group_size": 64, "bits": 8}}, indent=1))


def main() -> int:
    raison = verifier()
    if raison:
        print(f"Essai suisse allemand sauté : {raison}.")
        return 0
    if not (SORTIE / "weights.safetensors").exists():
        if input("Télécharger Flix-AI/flix-swissgerman-full (3,09 Go, Apache-2.0) pour l'essai ? Tapez « oui » : ").strip() != "oui":
            return 0
        import urllib.request

        brut = RACINE / "modeles" / "flix-gsw-hf"
        brut.mkdir(parents=True, exist_ok=True)
        for nom in ("config.json", "model.safetensors"):
            if not (brut / nom).exists():
                print(f"  téléchargement de {nom}…", flush=True)
                urllib.request.urlretrieve(f"https://huggingface.co/{DEPOT}/resolve/{REVISION}/{nom}", brut / nom)
        print("  conversion au format MLX (8 bits)…", flush=True)
        convertir(brut)
        shutil.rmtree(brut)  # on ne garde que la version convertie (~0,9 Go)
    import mlx.core as mx

    from briques.b04_oreilles_voix.audio import lire
    from briques.b04_oreilles_voix.banc_voix import taux_erreur
    from briques.b04_oreilles_voix.ecoute import creer_ecoute

    meta = json.loads((RACINE / "donnees_voix/equipe/gsw/textes.json").read_text(encoding="utf-8"))
    resultats = {}
    for nom, ecoute in [("Whisper normal (réglages)", creer_ecoute({"voix": {"ecoute": {"moteur": "mlx_whisper", "modele": "small"}}})),
                        ("Flix-AI (essai)", creer_ecoute({"voix": {"ecoute": {"moteur": "mlx_whisper", "modele": "flix-gsw"}}}))]:
        mx.reset_peak_memory()
        erreurs, temps = [], []
        for m in meta:
            t0 = time.perf_counter()
            t = ecoute.transcrire(lire(RACINE / "donnees_voix/equipe/gsw" / m["fichier"]), langue="gsw")
            temps.append((time.perf_counter() - t0) * 1000)
            erreurs.append(taux_erreur(m["texte"], t.texte, "gsw"))
        resultats[nom] = {"mots_faux_pct": round(sum(erreurs) / len(erreurs), 1), "temps_ms": round(sum(temps) / len(temps)),
                          "memoire_pic_go": round(mx.get_peak_memory() / 1e9, 2)}
        print(f"  {nom} : {resultats[nom]}", flush=True)
    (RACINE / "mesures").mkdir(exist_ok=True)
    (RACINE / "mesures" / "essai_suisse_allemand.json").write_text(json.dumps(resultats, indent=1, ensure_ascii=False))
    print("Résultats : mesures/essai_suisse_allemand.json (à envoyer à Hiba). Aucun réglage n'a été changé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
