# Mesures de la voix — 11.11.2026

**Où** : ordinateur Linux dans le nuage, 4 cœurs, processeur seul (pas de puce Apple). **Faux robot.** Internet non utilisé.
Les Mac devraient être plus rapides : **à mesurer** avec `python3 lancer.py banc-voix` (lancé par `preparer_mac.sh`).
Fichiers bruts : `mesures/voix_*.json` (hors dépôt, sur la machine qui a mesuré).

## Écoute sur de vraies voix (FLEURS, 6 phrases longues par langue, Whisper « small »)

| Langue | Mots faux au calme | Foule à 10 dB | Foule à 5 dB | Foule de la même langue à 10 dB | Langue reconnue | Langue sur 1,5 s de parole |
|---|---|---|---|---|---|---|
| français | 20,2 % | 24,9 % | 53,8 % | 29,9 % | 100 % | 100 % |
| allemand | 6,0 % | 12,0 % | 49,8 % | 16,1 % | 100 % | 100 % |
| italien | 4,8 % | 5,3 % | 8,6 % | 6,7 % | 100 % | 100 % |
| anglais | 6,6 % | 7,3 % | 25,8 % | 7,6 % | 100 % | 100 % |
| chinois (caractères faux) | 16,2 % | 25,1 % | 36,8 % | 27,3 % | 100 % | 100 % |
| suisse allemand | — | — | — | — | — | aucune vraie voix enregistrée |

- Foule : 8 voix mélangées (d'autres langues, ou de la même langue). 10 dB : la voix est nettement plus forte que
  la foule ; 5 dB : presque aussi forte. Une vraie halle peut être pire.
- Avec une foule forte, l'écoute se trompe beaucoup : **micro proche de la bouche (casque, micro-cravate) ou bouton
  « je parle »**. Le robot fait répéter quand il n'est pas sûr.
- Petit échantillon (6 phrases par langue) : un ordre de grandeur, pas une mesure précise.

## Temps entre la fin de la phrase et le début de la réponse parlée

Ordres courts chinois **SYNTHÉTIQUES** (« 请去厨房 », « 请看桌子 », « 停下 », sons figés), en temps réel, toute la chaîne,
écoute et voix préchauffées, première phrase d'une personne (aucune langue gardée).

| Écoute | Médiane | Bonne action lancée |
|---|---|---|
| Whisper base | **1,6 s** | 3 sur 3 |
| Whisper small | **2,6 s** | 3 sur 3 |
| Whisper small, avant les optimisations | 3,6 s | 3 sur 3 (compris ; lancement non vérifié à l'époque) |

Ce temps comprend 0,6 s de silence pour savoir que la phrase est finie (réglable), l'écoute (environ 1,9 s pour
small, 0,9 s pour base), le cerveau, le gardien et le calcul du premier son.

Mesures ponctuelles (script d'essai, non archivées) : reconnaître seulement la langue prend environ 0,9 s contre 1,9 s
pour un passage complet (small) ; quand la langue de la personne est gardée, l'écoute d'un ordre court prend environ
1,0 s. La chaîne complète dans ce cas n'a pas été mesurée (estimation : environ 1,7 s avec small).

## Ce qui reste à mesurer sur les Mac
Écoute sur puce Apple (mlx-whisper, whisper.cpp), voix du Mac, vrais ordres dits par l'équipe, suisse allemand,
interruption et écho avec le vrai haut-parleur.
