# Où on en est — 11.11.2026

## Fait (étape 1)
- Brique 1 — prise universelle : 10 actions (`briques/b01_prise/PRISE.md`), carte d'identité, ticket du gardien,
  suivi et annulation, arrêt d'urgence, test de conformité.
- Brique 2 — faux robot : 3 cartes (humanoïde, chien, bras), 4 pannes, chien de garde, vue de dessus à l'écran.
- Brique 12 — boîte noire : journal ligne par ligne, fiche de vérité, rejeu.
- Versions minimales pour relier la chaîne : gardien v0 (b07), cerveau « à règles » (b06), écran (b13), phrases en 5 langues + suisse allemand.
- `lancer.py` : une commande. `preparer_mac.sh` : un script pour les Mac (non testé sur Mac).
- Relecture sécurité indépendante, en deux tours : 12 constats puis 8 points de contre-relecture, tous corrigés, un test par point.
- 72 tests, Internet coupé pour le programme : tous passent (3 fois de suite).

## Fait (étape 2) — la voix
- Brique 4 : écoute (faster-whisper ; mlx-whisper et whisper.cpp prêts pour Mac), fin de parole (Silero),
  interruption, mot d'appel, bouton « je parle », langue reconnue, suisse allemand → réponse en allemand,
  confirmation avant action à risque, mode lent, vocabulaire du robot pour les ordres courts.
- Voix : chinois Piper (sherpa-onnx) ; voix du Mac (`say`) pour les autres langues ; sinon sous-titres.
- Banc d'essai : vraies voix FLEURS au calme et avec bruit de foule ; temps fin de phrase → réponse.
- `python3 lancer.py micro` pour parler au faux robot avec le micro du Mac (non testé sur Mac).
- Relecture indépendante de la voix : 12 constats (dont 5 où « stop » pouvait se perdre), tous corrigés, un test par constat.
- 105 tests, Internet coupé : tous passent (3 fois de suite).

## Fait (étape 3) — le cerveau
- Cascade Apertus 8B → 4B → règles, passage automatique, formulaire forcé, filets « cible non nommée » et « chiffres ».
- Banc d'essai : 30 demandes × 6 langues dont 12 pièges. Ici : règles 90–93 %, Apertus 0,5B 43–60 % (test).
- Script du Mac : chaque Apertus mesuré un à la fois ; voix : deux modèles d'écoute, ordres compris ; essai Flix-AI.

## Prochain (étape 4) — la confiance
Gardien complet (règles en phrases, zones, personnes, poids), « je ne suis pas sûr » (brique 8), écran du jury.

## La clinique en boîte (12.11.2026, après la relecture de la tranche 1)
- Tout est dans `briques/clinique/` ; l'état fait foi dans `docs/projet/SUIVI_CLINIQUE.md` ; les limites sont dans `NON_TESTE.md`.
- `python3 lancer.py repetition` joue sept scènes, quatorze étapes, et dit « RÉUSSIE » : **en version simple** (13 étapes SIMULÉ, 1 FAUX ROBOT ; tout est tapé, sans voix, sans modèle, sans vrai robot).
- Les écrans : `python3 lancer.py`, puis `/clinique` (patient, soignant, médecin, accueil, thérapeute, hall, flotte, direction, journal des accès).
- Règles tenues par des essais : rien ne s'écrit au faux dossier (tout va au carnet) ; un robot ne bouge que par le coursier, sous le gardien ; le prototype ne répond à aucune question de santé ; rien ne sort de l'ordinateur pendant la répétition.
- Suite : les preuves (J01 à J06), puis le cerveau, la voix et les yeux (T13 à T20), puis la vraie flotte (R5, T22 à T25).
- Tranche 2, relue au tour 68 (T21) : le vrai Apertus 8B tourne sur l'iMac (`apertus-essai`, `resume-apertus`, `papiers-apertus`, `tirage-apertus`, `chaine-mesure`) ; ses chiffres sont dans la fiche de vérité, lus dans `journal/clinique/mesures_cerveau/`.
- Ce que ces mesures disent : Apertus comprend un ordre (112 sur 120) ; il n'écrit aucune ligne du résumé qui passe le contrôle, et range les papiers moins bien que les règles : dans la séance, ce sont les règles simples qui travaillent (Apertus seulement avec `CLINIQUE_APERTUS=1`).
- La répétition « RÉUSSIE » reste la version simple : elle ne passe ni par la voix, ni par une image, ni par le modèle.
- Un cerveau peut inventer : chaque sortie de modèle est contrôlée contre ses sources par des règles, et retombe sur la version simple. Ces contrôles ont été percés trois fois et renforcés ; ils ne comprennent pas le sens.
- Deux ébauches de vrai robot, « PRÉPARÉES SANS LE ROBOT » : `briques/b03_adaptateurs/robots/unitree_go2` et `roues_ros2` ; la page `docs/projet/PREMIERE_HEURE.md`.

## Points ouverts
Voir `DECISIONS.md` (restent à faire) et `NON_TESTE.md`.
- Tranche 3, relue au tour 81 (T26) : cartes de rôle, répartiteur, panne et reprise, tableau de flotte (`/clinique/tableau-de-flotte`). Robots R2, R3, R4 simulés : rien ne bouge. La carte de R1 va chez le gardien au démarrage. Reste : la carte se contourne par les lieux de l'ossature et les actions hors coursier (H11) ; la place de R1 n'est pas lue (H12) ; la boîte noire (H13).
