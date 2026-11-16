# Brique 8 — Petites tâches

## Fait (étape 4) — testé sur faux robot
- [x] 20 demandes floues d'essai (fr, de, gsw, it, en, zh) : 20 questions, aucune action ; compteur dans `/api/fiche`.
- [x] Filet « deux choix » pour tous les cerveaux (deux lieux, deux objets, deux gestes nommés → question).
- [x] Main levée : deux « pas compris » de suite, deux échecs de suite, verdict « humain » du gardien.
- [x] Phrase « Je lève la main : j'ai besoin d'aide. » dans les 5 langues ; signal `aide_demandee` pour l'écran.
- [x] Aides apprises (« frigo » = cuisine) : fichier, monde, événement `aide_recue` ; comprises au démarrage suivant.
- [x] Options des questions dites dans la langue (« saisir un objet », pas « saisir »).

## Avant samedi
- [ ] Faire relire les phrases (de, it, zh) par quelqu'un qui parle la langue.
- [ ] Écran du jury : une grande main levée quand `aide_demandee` arrive, la phrase pas comprise, un bouton
      « apprendre ce mot » (`/api/aide/apprendre`) et « accepter / refuser » (`/api/aide/repondre`).
- [ ] Sur chaque Mac : `reglages.yaml → interrupteurs → main_levee → actif: true` (l'ancien fichier dit false).
- [ ] Écrire 20 demandes floues par l'équipe (pas par moi) et les essayer avec Apertus (banc d'essai, brique 6).

## Après
- [ ] Comprendre la réponse à une question : « Où dois-je aller ? » → « à la cuisine » (aujourd'hui : pas compris).
- [ ] Apprendre aussi des gestes et des verbes (aujourd'hui : lieux et objets seulement).
- [ ] Une vraie mesure du doute du modèle (probabilités, comme KnowNo) au lieu de compter les choix nommés.
- [ ] Idée 5 : demander de l'aide à la salle (« quelqu'un peut-il m'aider ? ») quand personne de l'équipe ne répond.
