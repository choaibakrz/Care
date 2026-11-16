# Brique 14 — Notes pour le coordinateur

Tout est **testé sur faux robot** (faux humanoïde, cerveau à règles, Linux du nuage). Rien n'a touché un vrai robot.
Jamais branché dans une vraie session de l'assistant de code (l'enregistrement est un réglage : feu orange, pour Hiba).

## Ce qui est fait
- **Serveur MCP sur stdio** (`serveur_mcp.py`) avec le SDK officiel `mcp` 2.3.0 (`MCPServer`). Cinq outils, et rien
  d'autre : `dire_au_robot(texte, langue)`, `voir_carte`, `voir_etat`, `voir_fiche`, `arreter`. Aucun outil pour
  changer une règle, réarmer, provoquer une panne ou toucher la prise.
- **La porte** (`porte.py`) : chaque phrase va à `systeme.chaine.traiter(..., source="agent:<nom>")`, donc
  cerveau → gardien (ticket) → prise, exactement comme la voix. L'agent reçoit les réponses du robot, le verdict du
  gardien, les raisons, le statut (réussie, refusée, question, attend un humain, attend « oui », en cours…) et une
  explication simple. Sur la prise, la porte n'utilise que `carte()`, `etat()` et `arret_urgence()` (les boutons
  ouverts de l'écran). L'appel à la chaîne est protégé (`asyncio.shield`) : un appel abandonné par l'agent ne coupe
  jamais la chaîne entre le ticket et la prise.
- **Limites des agents** (`reglages.yaml → porte_agents`) : `ordres_par_minute` (10 ; refus AVANT le cerveau, noté
  `porte_agents` ; « stop » jamais compté), `accord_humain` (allumé par défaut : chaque action d'un agent attend
  l'accord d'un humain, appliqué par le GARDIEN ; sauf `etat` ; l'arrêt toujours permis), `attente_fin_s` (30),
  `port_ecran` (8001).
- **Boîte noire et fiche** : source distincte `agent:<nom>` (parole entendue, demandeur du gardien, aide demandée,
  arrêt d'urgence `qui`) ; nouveau type `porte_agents` (ouverte, ordre_refuse) ; fiche : `demandes_agents`,
  `refus_porte_agents` (même fiche au rejeu, testé).
- **Commande** `python3 lancer.py porte-agents --agent assistant` (`commande.py`) : faux robot + écran de la brique 13
  (port 8001, même système, pour voir et accepter les demandes) + MCP sur stdio. Refuse un vrai robot.
  Messages humains sur la sortie d'erreur (la sortie standard est au protocole MCP).
- **Tests** : `briques/b14_porte_agents/tests/` — 46 tests, environ 11 s. Un vrai client MCP (client officiel du
  paquet `mcp`, en mémoire, poignée de main `initialize` en JSON-RPC) ; la vraie commande lancée dans un autre
  programme et parlée par stdio, Internet coupé, avec un « humain » qui accepte par l'API de l'écran ; les 10 ordres
  dangereux du gardien (accord humain allumé et éteint) ; ordre flou → question ; arrêt au-delà de la limite ; trop
  d'ordres ; aucun chemin hors du gardien (lecture du code + espions sur `prise.executer` et `gardien.verifier` :
  seulement appelés par `commun/chaine.py`) ; un argument `source` ajouté par l'agent est ignoré.
- `GUIDE.md` (une page, dont comment brancher l'assistant de code, lu sur la documentation de l'assistant le 11.11.2026),
  `TACHES.md`. Entrée 14 de `briques/etat_des_briques.yaml` mise à jour (état « socle »).

## Paquet ajouté (installé dans `/home/user/leukerbad/.venv`, épinglé dans `requirements.txt`)
Licences lues dans les métadonnées PyPI (`pip install --dry-run --report`), le 11.11.2026. Téléchargement 5,6 Mo ;
installé environ 23 Mo (dont cryptography 16 Mo). Aucune mise à jour d'un paquet déjà là.

| Paquet | Version | Licence |
|---|---|---|
| mcp (SDK officiel du Model Context Protocol) | 2.3.0 | MIT |
| mcp-types | 2.3.0 | MIT |
| jsonschema, jsonschema-specifications, referencing | 4.26.0, 2025.9.1, 0.37.0 | MIT |
| attrs | 26.1.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| PyJWT | 2.15.1 | MIT |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| python-multipart | 0.0.33 | Apache-2.0 |

Remarque : mcp 2.x a renommé `FastMCP` en `MCPServer` (`mcp.server.mcpserver`) ; le code suit la 2.3.0 lue dans le
paquet installé. `preparer_mac.sh` annonce « ~20 Mo » pour `requirements.txt` : environ 6 Mo de plus maintenant.

## Changements hors de la brique (exactement)
1. `commun/evenements.py` : **1 type** ajouté à la fin de `TYPES` : `porte_agents`.
2. `briques/b12_boite_noire/fiche.py` : **2 champs** (`demandes_agents`, `refus_porte_agents`), 1 ligne dans la branche
   `parole_entendue`, 2 lignes (`porte_agents` + `quoi == "ordre_refuse"`).
3. `commun/chaine.py` : import de `PREFIXE_AGENT` ; dans `_agir`, `demandeur = source si elle commence par
   « agent: », sinon « cerveau »` passé à `gardien.verifier` (pour les personnes : rien ne change) ; le chemin
   « stop prioritaire » passe `source=source` à `_agir` (le gardien note qui a dit stop).
4. `briques/b07_gardien/gardien.py` — **à faire relire par le relecteur sécurité** (AGENTS.md) : constante
   `PREFIXE_AGENT = "agent:"` ; paramètre `accord_humain_agents: bool = True` ; dans `__verifier`, 3 lignes : allumé
   et demandeur « agent:… » et action ≠ `etat` → raison `humain_requis` {action, demandeur} ajoutée aux raisons
   « humain » (sans doublon). Un « non » reste un « non ». Après l'accord, la revérification a le demandeur
   « humain:qui » : la raison n'est pas remise. Rien d'autre ne change dans le gardien.
5. `commun/systeme.py` : `accord_humain_agents` donné au gardien ; éteint **seulement** si `porte_agents.accord_humain`
   vaut exactement `false` (ligne absente, ancienne copie de reglages.yaml, faute de frappe : allumé).
6. `lancer.py` : une ligne de documentation, la fonction `porte_agents` (3 lignes), 2 lignes pour la sous-commande,
   1 entrée dans le tableau ; le message « reglages.yaml créé » va sur la sortie d'erreur (sinon il casserait le
   protocole MCP au premier lancement).
7. `reglages.exemple.yaml` : section `porte_agents` (4 réglages, avec l'explication du choix « allumé »).
8. `requirements.txt` : `mcp==2.3.0`.
9. Brique 13 (obligé par `test_la_doc_du_flux_montre_chaque_type_et_chaque_picto`) : `exemples_flux.py` (une entrée
   dans `CHAMPS` et une dans `A_LA_MAIN`) ; `FLUX_POUR_MOTION_DESIGN.md` : la section `porte_agents` ajoutée à la fin,
   au même format (le fichier n'a PAS été regénéré : pas d'autre changement).
10. `briques/etat_des_briques.yaml` : entrée 14 ; **et** une ligne de l'entrée 7 mise entre guillemets :
    « trois réponses : oui (ticket)… » était lue comme un dictionnaire, et les tests du kit (brique 17) échouaient
    déjà sur 1a2a75f (`sequence item 2: expected str instance, dict found`).

Conflits possibles avec la brique 3 : surtout la fin de `TYPES` (evenements.py) et la fin du tableau de `lancer.py`.

## Choix à faire relire
- `accord_humain` **allumé par défaut** (un agent peut être trompé par un texte lu ailleurs ; une personne, elle,
  n'est pas touchée : testé). `false` pour une démonstration où l'agent agit seul, gardien toujours là.
- C'est le **gardien** qui demande l'humain (verdict « humain » existant, raison `humain_requis`), pas la porte :
  l'écran, les aides (`/api/aides`, `/api/aide/repondre`) et la revérification marchent tels quels.
- `etat` n'attend personne (lire) ; `arreter` (action) est toujours oui chez le gardien.
- L'outil `arreter` = **arrêt d'urgence** (`prise.arret_urgence`, comme le bouton ouvert de l'écran) : un humain doit
  réarmer. « stop » dit par `dire_au_robot` = arrêt normal par la chaîne (pas de réarmement).
- La source vient de la porte (`--agent NOM`, contrôlé : minuscules, chiffres, - et _), jamais de l'agent.
- Le « oui » d'une confirmation : seulement du même agent (règle de la chaîne). Un agent ne peut pas accepter une
  demande du gardien (aucun outil ; « oui » ne la fait pas partir : testé).
- Les positions des personnes ne sont pas données aux agents (`voir_carte` : lieux et objets seulement).
- `porte-agents` crée son propre système : **faux robot seulement** (deux systèmes = deux liaisons avec un vrai robot).
  La version HTTP dans le programme de l'écran principal reste à faire (TACHES.md) : je ne l'ai pas faite.
- `parler` : avec `accord_humain: false`, un agent peut faire dire au robot un texte de son choix (comme la tablette).

## Lignes à ajouter (je n'ai pas modifié ces fichiers)

**LICENCES.md**
```
## Brique 14 (porte des agents)

Paquet ajouté (installé depuis PyPI, utilisé tel quel ; licences lues dans les métadonnées PyPI le 11.11.2026) :

| Paquet | Version | Licence | Auteur / projet |
|---|---|---|---|
| mcp | 2.3.0 | MIT | Model Context Protocol a Series of LF Projects, LLC (github.com/modelcontextprotocol/python-sdk) |
| mcp-types | 2.3.0 | MIT | idem |
| jsonschema, jsonschema-specifications, referencing | 4.26.0, 2025.9.1, 0.37.0 | MIT | Julian Berman |
| attrs | 26.1.0 | MIT | Hynek Schlawack |
| rpds-py | 2026.9.1 | MIT | Julian Berman |
| PyJWT | 2.15.1 | MIT | Jose Padilla |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | The Python Cryptographic Authority |
| python-multipart | 0.0.33 | Apache-2.0 | Andrew Dunham |

Aucun code copié : la porte est écrite pour ce projet. Le format MCP est celui du SDK officiel (spécification
publique non relue pour cette étape). Auteurs : lus dans les métadonnées des paquets installés.
```

**DECISIONS.md** (section « à relire par Hiba »)
```
- **Porte des agents (brique 14)** : un agent d'IA parle au robot comme une personne (MCP, stdio) ; chaque ordre
  passe par la chaîne de la voix (cerveau → gardien → ticket → prise), source « agent:nom ». Cinq outils seulement ;
  rien pour les règles, le réarmement, les pannes. L'outil « arreter » = arrêt d'urgence (un humain réarme).
- **Accord d'un humain pour les agents : allumé par défaut** (reglages.yaml → porte_agents → accord_humain), appliqué
  par le gardien (raison humain_requis), sauf « etat » ; éteint seulement par « false ». 10 ordres par minute au plus
  par agent ; « stop » jamais compté. Paquet `mcp` 2.3.0 (MIT) ajouté.
- **porte-agents sur faux robot seulement** tant que la version HTTP n'est pas dans le programme de l'écran principal.
```

**NON_TESTE.md** (nouvelle section ; et dans « Pas encore construit », retirer 14 : « Briques 3, 5, 9 à 11, 16. »)
```
## Porte des agents (brique 14) : testé sur faux robot seulement
- Jamais dans une vraie session de l'assistant de code ni avec un autre agent : client essayé = le client du SDK `mcp` 2.3.0
  (protocole 2025-11-25 par stdio et en mémoire). Version du protocole choisie par l'assistant de code : à vérifier.
- Enregistrement dans l'assistant de code : pas fait (feu orange) ; commande du GUIDE lue dans la documentation, jamais lancée.
- Jamais sur Mac ; jamais avec la cascade Apertus (tests : cerveau à règles).
- L'écran lancé par porte-agents : testé par son API (aides, accepter), pas dans un navigateur.
- Arrêt de la commande par Ctrl+C ou par un signal : non testé (fin testée : l'agent ferme l'entrée standard).
- Plusieurs agents en même temps : non testé.
```

## Mesuré (11.11.2026, Linux du nuage, faux robot)
- Suite complète depuis ma copie (`/home/user/leukerbad/.venv/bin/python lancer.py tests`) : **362 réussis,
  11 sautés**, 130 s. Sur 1a2a75f, avant mon travail, les tests du kit (brique 17) échouaient (entrée 7, voir plus haut).
- Tests de la brique : 46 réussis, environ 11 s, trois fois de suite (avec ceux de la brique 17).
- Commande réelle par stdio : connexion en 0,7 s ; « Va à la table » → attend un humain ; « Batterie ? » → réussie.

## À faire vérifier
« Celui qui écrit n'est pas celui qui vérifie » : personne d'autre n'a relu. À relire surtout : l'ajout dans
`gardien.py` (relecteur sécurité), `PorteDesAgents.dire` et `_compte_rendu` (statuts), `commande.py` (écran et MCP
dans le même programme ; l'écran est lancé sans son propre démarrage, `lifespan="off"`).

## Vu en passant (hors de ma brique, non corrigé)
- `flux_simple.ligne_simple` rend un texte vide pour `porte_agents` (et un picto vide) : à ajouter par la brique 13.
- `lancer.py` crée `reglages.yaml` à chaque lancement s'il manque, même pour `tests` : les tests le laissent ensuite.
