"""Brique 6 — Démarrer et arrêter les serveurs des modèles (Apertus) sur cet ordinateur.

Sur Mac : `llama-server` (llama.cpp, installé par preparer_mac.sh) utilise la puce graphique.
Sinon : `python -m llama_cpp.server` (llama-cpp-python, processeur) — utilisé pour les tests sur Linux.
Mémoire : Apertus 8B (~5,6 Go avec sa mémoire de conversation) et 4B (~2,8 Go) ne tiennent pas ensemble avec
l'écoute et la voix sur un Mac de 16 Go : le 4B est donc démarré « au besoin », seulement si le 8B tombe.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
log = logging.getLogger("serveurs")


class ServeurModele:
    def __init__(self, nom: str, modele: str, port: int, hote: str = "127.0.0.1", contexte: int = 4096,
                 puce_graphique: bool = True) -> None:
        self.nom, self.port, self.hote, self.contexte, self.gpu = nom, port, hote, contexte, puce_graphique
        chemin = Path(modele)
        self.modele = chemin if chemin.is_absolute() else RACINE / chemin
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def commande(self) -> list[str]:
        binaire = shutil.which("llama-server") or (str(RACINE / "outils/bin/llama-server")
                                                   if (RACINE / "outils/bin/llama-server").exists() else None)
        if binaire:
            return [binaire, "-m", str(self.modele), "--port", str(self.port), "--host", self.hote,
                    "-c", str(self.contexte), "-ngl", "99" if self.gpu else "0"]
        return [sys.executable, "-m", "llama_cpp.server", "--model", str(self.modele), "--port", str(self.port),
                "--host", self.hote, "--n_ctx", str(self.contexte)]

    def en_marche(self) -> bool:
        for chemin in ("/health", "/v1/models"):
            try:
                with urllib.request.urlopen(self.url + chemin, timeout=0.5) as r:
                    if r.status == 200:
                        return True
            except Exception:
                continue
        return False

    def en_chargement(self) -> bool:
        """Lancé par nous, mais pas encore prêt (le modèle se charge en mémoire)."""
        if not self.proc or self.proc.poll() is not None:
            return False
        maintenant = time.time()
        if maintenant - getattr(self, "_vu_a", 0) > 2:  # on ne redemande pas plus d'une fois toutes les 2 s
            self._pret, self._vu_a = self.en_marche(), maintenant
        return not self._pret

    def tourne(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def lancer(self) -> None:
        """Lance le serveur s'il ne tourne pas déjà (ne bloque pas)."""
        if (self.proc and self.proc.poll() is None) or self.en_marche():
            return
        if not self.modele.exists():
            raise FileNotFoundError(f"Modèle absent : {self.modele} (outils/telecharger.py)")
        log.info("Démarrage du cerveau %s : %s", self.nom, " ".join(self.commande()))
        self.proc = subprocess.Popen(self.commande(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def attendre(self, delai_s: float = 120) -> bool:
        fin = time.time() + delai_s
        while time.time() < fin:
            if self.en_marche():
                return True
            if self.proc and self.proc.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    def eteindre(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
