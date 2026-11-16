# Brique 12 — Boîte noire et fiche de vérité (guide d'une page)

**Rôle** : tout garder, dire la vérité en chiffres, tout pouvoir rejouer. Testé sur faux robot.

## La boîte noire (`journal.py`)
Chaque événement du bus est écrit tout de suite dans `journal/AAAA-MM-JJ_HHMMSS.jsonl`, une ligne par événement :
type, heure, source, robot, conversation, détails. Les types possibles : `commun/evenements.py`.
Rien ne sort de l'ordinateur-cerveau.

## La fiche de vérité (`fiche.py`)
Calculée **uniquement** depuis les événements : la même en direct, après coup, ou après un rejeu.
Réussites, ratés, annulées, refus (gardien, prise), questions, aides demandées, arrêts d'urgence, pannes,
part de l'humain (%), temps de première réponse, temps du cerveau, temps d'action, « non compris » par langue,
et la mention **testé sur faux robot / testé sur vrai robot**.

## Le rejeu (`rejeu.py`)
```bash
python3 lancer.py rejouer                     # le dernier journal
python3 lancer.py rejouer journal/FICHIER.jsonl
```
Affiche le récit lisible puis la fiche. Le rejeu ne touche jamais un robot : il republie sur un bus séparé.

## Tester
```bash
python3 lancer.py tests briques/b12_boite_noire
```
