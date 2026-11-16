# Mesures du cerveau — 11.11.2026

**Où** : ordinateur Linux dans le nuage, 4 cœurs, processeur seul. **Faux robot.** Internet non utilisé.
30 demandes × 6 langues (dont 12 pièges : 3 dangereuses, 3 floues, 3 impossibles, 3 qui ne sont pas des ordres).

| Cerveau | Bonnes réponses (selon la langue) | Ordres normaux | Pièges | Temps médian |
|---|---|---|---|---|
| à règles | 90 à 93 % | 83 à 89 % | 100 % | < 1 ms |
| Apertus v1.1 **0,5B** (test seulement) | 43 à 60 % | 6 à 39 % | 67 à 100 % | ~1,8 s |
| Apertus **8B** et **4B** | **à mesurer sur les Mac** | | | |

À lire avec prudence :
- **Le cerveau à règles est avantagé** : j'ai écrit les phrases du banc ET sa liste de mots. Sur une parole libre
  (« tu pourrais filer vers le frigo ? »), il fera moins bien. D'où la tâche : 30 demandes écrites par l'équipe.
- **Le 0,5B ne sert qu'à vérifier que tout marche** (formulaire forcé respecté à 100 %, secours automatique) ;
  il est trop petit pour comprendre. Sans le filet « cible non nommée », il agissait sur les ordres flous (0 %).
- Les pièges « dangereux » passent à 100 % grâce au verrou des chiffres et au gardien, pas grâce au modèle. Ces
  pièges ont été écrits par le même agent que le verrou : il faut des tournures écrites par l'équipe.
- Depuis la relecture : une panne du cerveau compte comme une mauvaise réponse (colonne « Erreurs »).
- Le 0,5B choisit presque toujours un lieu : il ne permet pas de juger le 8B sur les distances ou les reculs.
