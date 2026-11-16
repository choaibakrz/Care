# Brique 14 — La porte des agents (guide d'une page)

**Rôle** : un agent d'IA (par exemple un assistant d'IA) commande le robot **comme une personne qui parle**, toujours sous le
contrôle du gardien. **MCP** (« Model Context Protocol ») = une façon standard pour un agent d'IA d'appeler des outils.
Chemin unique, le même que la voix : agent → `dire_au_robot` → cerveau → **gardien** (ticket) → prise → robot.
**Testé sur faux robot** (Linux). Jamais avec un vrai robot, jamais dans une vraie session de l'assistant de code.

## Lancer
```bash
export LEUKERBAD_CODE_EQUIPE='…'                      # le code d'équipe (obligatoire : voir plus bas)
python3 lancer.py porte-agents --agent assistant          # faux robot + écran (port 8001) + serveur MCP sur stdio
python3 lancer.py porte-agents --agent assistant --sans-ecran --cerveau regles --acceleration 10   # essais
```
« stdio » : l'agent lance lui-même cette commande et lui parle par l'entrée et la sortie standard. Lancée à la main,
elle attend un agent (Ctrl+C pour arrêter). Les messages pour les humains vont sur la sortie d'erreur.
Options : `--agent NOM` (noté « agent:NOM » dans la boîte noire), `--robot humanoide|chien|bras`, `--port`,
`--sans-ecran` (alors personne ne peut accepter une demande), `--cerveau regles|cascade`, `--acceleration`, `--journal`.
**Faux robot seulement** : avec un vrai robot, la commande refuse (feu orange, décision de Hiba).

## Les cinq outils (et rien d'autre)
| Outil | Ce qu'il fait |
|---|---|
| `dire_au_robot(texte, langue)` | une phrase, comme une personne ; rend les réponses du robot, le verdict du gardien, les raisons, le statut |
| `voir_carte` | ce que le robot sait faire, ses limites, lieux et objets, règles du gardien, limites de la porte |
| `voir_etat` | batterie, position, arrêt d'urgence ; mes demandes qui attendent un humain ; mes dernières actions |
| `voir_fiche` | la fiche de vérité (dont « demandes des agents ») |
| `arreter` | **arrêt d'urgence**, toujours permis (sans limite ni accord). Ensuite, seul un humain réarme (écran) |

Aucun outil pour changer une règle, réarmer, provoquer une panne, toucher la prise : cela reste aux humains.
Statuts rendus : `reussie`, `echouee`, `annulee`, `refusee` (raisons), `question`, `attend_confirmation` (répondre
« oui »/« non »), `attend_un_humain` (n° de demande), `en_cours` (suivre avec `voir_etat`), `pas_compris`,
`trop_d_ordres`, `ordre_invalide`. Chaque réponse porte la mention « testé sur faux robot » (lue sur la carte).

## Les limites des agents : `reglages.yaml → porte_agents`
- `accord_humain: true` (**allumé par défaut**, et aussi si la ligne manque) : chaque action d'un agent attend l'accord
  d'un humain (écran → aides, `POST /api/aide/repondre`). Sauf « etat » (lire) et l'arrêt. C'est le **gardien** qui
  l'applique. Pourquoi allumé : un agent peut être trompé par un texte qu'il a lu. `false` : l'agent agit seul, le
  gardien vérifie quand même tout (un « non » reste un « non » dans les deux cas).
- `ordres_par_minute: 10` : au-delà, refus **avant** le cerveau (`porte_agents` dans la boîte noire). « stop » : jamais compté.
- `attente_fin_s: 30` : l'agent attend la fin de l'action au plus 30 s, puis reçoit `en_cours`.
- `port_ecran: 8001` : l'écran de la porte (l'écran principal garde le 8000).

## Brancher un agent (l'assistant de code) — **FEU ORANGE : réglage à faire par Hiba**
L'enregistrement dans l'assistant de code est un réglage de l'ordinateur : **pas fait**, aucun `.mcp.json` dans le dépôt.
D'après la documentation (la documentation de l'assistant, lue le 11.11.2026 ; **à revérifier** au moment de le faire) :
```bash
<commande-de-l-assistant> mcp add --transport stdio --scope local porte-agents -- \
  /CHEMIN/leukerbad/.venv/bin/python /CHEMIN/leukerbad/lancer.py porte-agents --agent assistant
```
**Code d'équipe obligatoire** (relecture du lot C) : sans lui, la commande refuse de démarrer ; l'écran de la porte
l'exige même sur cet ordinateur. Le donner par la variable `LEUKERBAD_CODE_EQUIPE` (ou `reglages.yaml`).
**Attention** : un agent qui a un terminal ou l'accès aux fichiers de l'ordinateur-cerveau peut lire ce code (fichier
ou variable d'un programme) et accepter lui-même ses demandes. La vraie garde : l'agent n'a ni terminal ni accès aux
fichiers sur cet ordinateur (réglage de l'assistant de code, feu orange) ; et `ecran.local_sans_code: false` pour l'écran principal.
Le `--` sépare les options de l'assistant de code de la commande du serveur. Portée `local` : pour Hiba seule, dans ce projet.
Ensuite, dans l'assistant de code : « Regarde la carte du robot, puis dis-lui d'aller à la table. »

## Montrer au jury (3 minutes)
1. Ouvrir `http://localhost:8001/jury`. 2. Demander à l'assistant « va à la table » : le robot **lève la main**, la demande
s'affiche (demandeur `agent:assistant`). 3. Hiba accepte : le robot part. 4. « Va dans l'escalier » : **refusé et expliqué**.
5. « Va » : une **question**. 6. l'assistant appelle `arreter` : tout s'arrête ; l'assistant ne peut pas réarmer. 7. `voir_fiche`.

## Tester
`python3 lancer.py tests briques/b14_porte_agents` — 46 tests, environ 11 s : un vrai client MCP (paquet `mcp`) en
mémoire, et la vraie commande par stdio (Internet coupé). Code : `porte.py` (le travail), `serveur_mcp.py` (les outils),
`commande.py` (la commande). Paquet : `mcp` 2.3.0, licence MIT.
