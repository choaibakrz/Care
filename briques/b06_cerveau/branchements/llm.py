"""Brique 6 — Un cerveau « modèle de langue » (Apertus), joint par le réseau local ou sur le même ordinateur.

Il parle à un serveur qui suit la forme d'OpenAI (`/v1/chat/completions`) :
- llama.cpp (`llama-server`, licence MIT) : formulaire FORCÉ (grammaire). Sur Mac et Linux.
- llama-cpp-python (`python -m llama_cpp.server`, licence MIT) : pareil. Utilisé pour les tests sur Linux.
- mlx-lm (`mlx_lm.server`, licence MIT) : pas de grammaire → formulaire VÉRIFIÉ après coup. Mac seulement.
- un service en ligne (bonus, éteint par défaut) : par exemple l'API d'inférence du CSCS
  (`https://api.inference.cscs.ch/v1`), où l'équipe a vu répondre `swiss-ai/Apertus-v1.5-70B` avec un formulaire
  imposé (« json_schema strict ») le 01.10.2026 (dépôt HackVS, docs/audit/probe_publicai.md). Clé nécessaire ;
  conditions et coût : à vérifier.
Le serveur peut être sur l'autre Mac : seule l'adresse change.
"""
from __future__ import annotations

import os
import sys
import time

import httpx

from briques.b01_prise.carte import CarteIdentite
from commun.monde import Monde

from ..formulaire import FormulaireInvalide, cible_non_nommee, consigne, exemples, lire_reponse, schema
from ..prise_cerveau import Cerveau, Decision, garde_fou_carte

NOMS_LANGUES = {"fr": "French", "de": "German", "gsw": "Swiss German", "it": "Italian", "en": "English", "zh": "Chinese"}


class CerveauIndisponible(Exception):
    """Le serveur ne répond pas (éteint, trop lent, erreur)."""


class HorsFormulaire(CerveauIndisponible):
    """Le modèle répond, mais pas dans le formulaire : on passe au suivant POUR CETTE PHRASE, sans le mettre de côté."""


class CerveauLLM(Cerveau):
    def __init__(self, nom: str, url: str, modele: str = "", formulaire: str = "force", cle_env: str | None = None,
                 max_jetons: int = 120, delai_reseau_s: float = 30.0, trousseau: str | None = None) -> None:
        self.nom = nom
        self.url = url.rstrip("/").removesuffix("/v1")  # « …/v1 » ou sans : les deux marchent
        self.modele = modele
        # "force" : grammaire llama.cpp ; "json_schema" : forme OpenAI (services en ligne) ; "verifie" : contrôle après coup
        self.formulaire = formulaire
        self.cle_env = cle_env
        self.trousseau = trousseau  # nom du service dans le trousseau macOS (la clé n'est jamais écrite dans un fichier)
        self.__cle: str | None = None  # lue une seule fois, gardée en mémoire seulement
        self.max_jetons = max_jetons
        self.delai_reseau_s = delai_reseau_s
        self.transport: httpx.AsyncBaseTransport | None = None  # les tests y mettent un faux serveur
        self._clients: dict[int, httpx.AsyncClient] = {}
        self.derniere_duree_ms: float | None = None

    def _client(self) -> httpx.AsyncClient:
        """Un client réseau par boucle d'exécution (un client ne peut pas changer de boucle)."""
        import asyncio

        cle = id(asyncio.get_running_loop())
        if cle not in self._clients:
            self._clients[cle] = httpx.AsyncClient(timeout=self.delai_reseau_s, transport=self.transport)
        return self._clients[cle]

    async def arreter(self) -> None:
        import asyncio

        client = self._clients.pop(id(asyncio.get_running_loop()), None)
        if client:
            await client.aclose()

    def _corps(self, texte: str, langue: str | None, carte: CarteIdentite, monde: Monde) -> dict:
        nom_langue = NOMS_LANGUES.get(langue or "", "the language of the request")
        corps = {
            "messages": [
                {"role": "system", "content": consigne(carte, monde)},
                *exemples(carte),  # toujours les mêmes : le moteur les garde en mémoire d'une demande à l'autre
                {"role": "user", "content": f"[language: {nom_langue}] {texte}"},
            ],
            "temperature": 0, "max_tokens": self.max_jetons, "stream": False,
        }
        if self.modele:
            corps["model"] = self.modele
        if self.formulaire == "force":
            # Forme acceptée par llama.cpp et llama-cpp-python : la réponse est forcée à suivre le schéma.
            corps["response_format"] = {"type": "json_object", "schema": schema(carte, monde)}
        elif self.formulaire == "json_schema":
            # Forme OpenAI, acceptée par l'API du CSCS (vérifié par l'équipe le 01.10.2026).
            corps["response_format"] = {"type": "json_schema",
                                        "json_schema": {"name": "reponse_robot", "schema": schema(carte, monde), "strict": True}}
        return corps

    def _cle(self) -> str | None:
        """La clé : variable d'environnement, sinon (Mac) le trousseau. Jamais écrite dans un fichier ni un journal.
        Lue une seule fois (la commande du trousseau peut prendre quelques secondes)."""
        if self.__cle:
            return self.__cle
        self.__cle = self._lire_cle()
        return self.__cle

    def _lire_cle(self) -> str | None:
        if self.cle_env and os.environ.get(self.cle_env):
            return os.environ[self.cle_env]
        if self.trousseau and sys.platform == "darwin":
            import subprocess

            r = subprocess.run(["security", "find-generic-password", "-s", self.trousseau, "-w"],
                               capture_output=True, text=True, timeout=10, check=False)
            return r.stdout.strip() or None if r.returncode == 0 else None
        return None

    def __repr__(self) -> str:  # ne montre jamais la clé
        return f"CerveauLLM({self.nom!r}, {self.url!r}, {self.modele!r})"

    async def decider(self, texte: str, langue: str | None, carte: CarteIdentite, monde: Monde) -> Decision:
        # Certains services refusent une demande sans « User-Agent » : on envoie un nom générique, rien de personnel.
        entetes = {"User-Agent": "leukerbad-robot/1.0"}
        if self.cle_env or self.trousseau:
            import asyncio

            cle = await asyncio.to_thread(self._cle)  # hors de la boucle : l'écran et l'arrêt d'urgence restent vivants
            if not cle:
                raise CerveauIndisponible(f"{self.nom} : clé absente (variable {self.cle_env} ou trousseau {self.trousseau})")
            entetes["Authorization"] = f"Bearer {cle}"
        t0 = time.perf_counter()
        corps = self._corps(texte, langue, carte, monde)
        try:
            r = await self._client().post(f"{self.url}/v1/chat/completions", json=corps, headers=entetes)
            if r.status_code in (400, 422) and self.formulaire == "json_schema":
                # Le service refuse le formulaire imposé : on réessaie avec un « appel d'outil » forcé qui suit le même
                # formulaire (idée reprise du dépôt Flexsis- de Hiba, avec son accord).
                corps.pop("response_format")
                corps["tools"] = [{"type": "function", "function": {"name": "reponse_robot", "parameters": schema(carte, monde)}}]
                corps["tool_choice"] = {"type": "function", "function": {"name": "reponse_robot"}}
                r = await self._client().post(f"{self.url}/v1/chat/completions", json=corps, headers=entetes)
            r.raise_for_status()
            message = r.json()["choices"][0]["message"]
            appels = message.get("tool_calls") or []
            contenu = appels[0]["function"]["arguments"] if appels else (message.get("content") or "")
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise CerveauIndisponible(f"{self.nom} : {e.__class__.__name__}: {e}"[:200]) from e
        finally:
            self.derniere_duree_ms = round((time.perf_counter() - t0) * 1000, 1)
        try:
            d = lire_reponse(contenu.strip(), carte, monde)
        except FormulaireInvalide as e:
            raise HorsFormulaire(f"{self.nom} : formulaire non suivi ({e})") from e
        d.cerveau = self.nom
        d.langue_devinee = langue
        question = cible_non_nommee(d, texte, monde)
        if question:  # lieu ou objet inventé par le modèle : on demande au lieu d'agir
            return Decision(genre="question", question=question, confiance=0.8, cerveau=self.nom, langue_devinee=langue)
        return garde_fou_carte(d, carte)
