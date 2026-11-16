# Brique 13 — Petites tâches

## Étape 4 (faites, testé sur faux robot)
- [x] Page « jury » séparée (`/jury`), grands caractères, sans défilement, clair et sombre, téléphone accepté.
- [x] Sous-titres dans la langue parlée + une deuxième langue au choix (réponses du robot redites exactement).
- [x] Encadrés « J'ai entendu / J'ai compris / Je vais faire / Je refuse parce que… / Je pose une question / J'ai besoin d'aide ».
- [x] Fiche de vérité en grand (idée 10), mention « testé sur faux / vrai robot » toujours visible.
- [x] Bouton « Internet coupé » (idée 8) : coupe vraiment, montre que tout continue, noté dans la boîte noire.
- [x] Pictogrammes SVG et mode silence (idée 14).
- [x] Flux pour le motion design documenté (`FLUX_POUR_MOTION_DESIGN.md`), flux simple `/api/flux_simple`, `/ws_simple`.
- [x] Tests (TestClient + Chromium) et capture `capture_jury.png`.

## Reste à faire
- [ ] Traduire ce que dit la PERSONNE : brancher Apertus dans `traduction.py` (temps et qualité à mesurer ; marqué
      « traduit par un modèle » à l'écran). Décision de Hiba.
- [ ] Essayer `/jury` sur le vrai grand écran ou projecteur du carnaval (lisible de loin ? à vérifier sur place),
      sur Safari (Mac) et sur iPad.
- [x] Quand la brique 8 sera prête : vérifier les champs de `aide_demandee` et du verdict « humain » (l'écran montre
      l'action et les raisons du gardien), et ajouter une `cle` à leur phrase pour la deuxième langue (fait : lot B).
- [ ] Faire relire par l'équipe les étiquettes traduites de la page (de, it, en, zh) dans `static/jury.js`.
- [ ] Exemples réels de `mot_d_appel` et `interruption` avec le micro du Mac (aujourd'hui : forme relevée dans le code).
- [ ] Avec un vrai robot : refaire la capture (mention « testé sur vrai robot »).
- [ ] Le code d'équipe reste gardé dans le navigateur du grand écran : le redemander pour « Réarmer » (relecture du
      lot B ; voir NON_TESTE.md).
