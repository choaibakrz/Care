# Brique 1 — La prise universelle (guide d'une page)

**Rôle** : la courte liste de choses que tout robot sait faire, dite pareil pour tous. Testé sur faux robot.

## Les fichiers
| Fichier | Contenu |
|---|---|
| `PRISE.md` | la liste des 10 actions, en clair |
| `actions.py` | la même liste, pour le programme (un test vérifie qu'elles sont identiques) |
| `carte.py` | la carte d'identité d'un robot : capacités et limites |
| `validation.py` | une action est-elle dans la carte et dans les limites ? |
| `ticket.py` | le ticket signé que seul le gardien peut fabriquer |
| `prise.py` | **le seul** code qui parle à un adaptateur |
| `adaptateur.py` | ce que tout adaptateur doit savoir faire |
| `conformite.py` | le test qu'un adaptateur doit passer |

## Le chemin d'une action
```
cerveau → ActionDemandee → gardien.verifier() → Ticket → prise.executer(ticket) → adaptateur.demarrer()
```
La prise refuse : sans ticket, ticket faux ou réutilisé, action absente de la carte, valeur hors limites,
arrêt d'urgence actif. Chaque refus devient un événement `action_refusee` avec un **code** (voir `raisons.py`),
traduit ensuite dans la langue de la personne.

## Suivre et annuler
`executer()` rend tout de suite un suivi (`SuiviAction`). Ensuite : `suivre(id)`, `annuler(id)`, `attendre(id)`.

## Arrêt d'urgence
`prise.arret_urgence()` : sans ticket, sans attente, toujours. Puis `prise.rearmer()` par un humain.

## Tester
```bash
python3 lancer.py tests briques/b01_prise
```

## Ne pas faire
- Appeler un adaptateur ailleurs que dans `prise.py` (un test l'interdit).
- Ajouter une action sans décision d'équipe (`DECISIONS.md`) et sans mettre à jour `PRISE.md`.
