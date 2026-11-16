# La promesse

> Une personne parle au robot dans sa langue. Le robot comprend, vérifie que c'est sans danger, agit ou demande
> de l'aide, répond dans la même langue, et tout est gardé en mémoire. Cela marche avec n'importe quel robot,
> et sans Internet.

## Les six preuves (Internet coupé, un seul ordinateur)

| # | Preuve | Où c'est testé | État au 11.11.2026 |
|---|---|---|---|
| 1 | Même phrase en fr, de, en, zh → même action | `tests_bout_en_bout/test_chaine.py`, `briques/b04_oreilles_voix/tests` | ✔ texte tapé · ✔ à la voix en chinois (voix synthétique) · fr, de, en à la voix : sur Mac (`banc-voix`) |
| 2 | Ordre dangereux → refus expliqué dans la langue | idem | ✔ vitesse excessive · règles complètes : étape 4 |
| 3 | Ordre flou → question | idem | ✔ cerveau à règles · brique 8 complète : étape 4 |
| 4 | L'écran montre tout, la fiche se remplit | idem | ✔ écran minimal · écran du jury : étape 4 |
| 5 | Faux humanoïde → faux bras, rien d'autre ne change | idem | ✔ |
| 6 | Un agent IA passe par la porte des agents, contrôlé par le gardien | — | étape 5 |

## Ce que ce n'est pas
Pas le produit final, pas une fonction propre à un défi, pas une interface finie. Une ossature testée.
