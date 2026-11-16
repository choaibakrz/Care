# Les rôles

Un rôle = une personne (ou un agent) et un dossier. Celui qui écrit n'est pas celui qui vérifie.
Règles communes : `docs/projet/REGLES_DES_AGENTS.md`. Où on en est : `docs/projet/CONTEXT.md`.

| Rôle | Dossier(s) | Fait | Vérifié par |
|---|---|---|---|
| Architecte | `commun/`, `briques/b01_prise/` | garde la prise universelle stable ; décide d'ajouter une action | relecteur sécurité |
| Voix | `briques/b04_oreilles_voix/` | écoute, langues, voix, mode interprète | tests |
| Yeux | `briques/b05_yeux/` | objets, textes, étiquettes, personnes, pictogrammes | tests |
| Cerveau | `briques/b06_cerveau/` | branchements de modèles, banc d'essai | tests + relecteur sécurité |
| Gardien | `briques/b07_gardien/` | règles, chien de garde, refus expliqués | relecteur sécurité (obligatoire) |
| Adaptateurs | `briques/b03_adaptateurs/` | un adaptateur par robot, test de conformité | tests + relecteur sécurité |
| Écran | `briques/b13_ecran/` | écran du jury, flux pour le motion design | tests |
| Tests | `tests_bout_en_bout/`, `conftest.py` | les six preuves, Internet coupé | architecte |
| Relecteur sécurité | tout | relit chaque changement touchant gardien, prise, adaptateurs | — |
| Rédacteur des guides | `*.md` | guides d'une page, `TACHES.md` | Hiba |

## Pour les agents IA
- Commencer seul. Des sous-agents en parallèle seulement pour des briques vraiment indépendantes (la prise est figée).
- Un sous-agent relit et teste le travail d'un autre, sans lui donner la conclusion attendue.
- Ne jamais toucher à `b01_prise/prise.py`, `b01_prise/ticket.py`, `b07_gardien/` sans relecteur sécurité.
